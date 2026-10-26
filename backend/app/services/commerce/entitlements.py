"""Entitlements: who may download what, and why.

Sources:
- ``purchase``: a provider-verified, paid order item (one per order item);
- ``bundle``: a product included in a purchased bundle, expanded **at the time of
  sale** (later bundle changes never add or remove access already granted);
- ``free``: a free product claimed by a signed-in customer (no order is created);
- ``manual``: granted by staff with ``entitlements.manage`` (support cases).

``grant_key`` is unique, so a repeated webhook, a concurrent verification or a
double-clicked "Get it free" can never create a second entitlement.

The file version policy is documented in ``product_files.py``.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import (
    Customer,
    DownloadEvent,
    Entitlement,
    EntitlementEvent,
    Order,
    OrderItem,
    Product,
    ProductFile,
    User,
)
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import catalogue


class NotEntitledError(APIError):
    status_code = 403
    code = "not_entitled"
    message = "You don't have access to this download."


def _now() -> datetime:
    return datetime.now(UTC)


def purchased_versions(product: Product) -> dict[str, int]:
    return {
        str(f.id): f.current_version_id
        for f in catalogue.deliverable_files(product)
        if f.current_version_id
    }


def _grant(
    *,
    customer: Customer,
    product: Product,
    source: str,
    grant_key: str,
    order: Order | None = None,
    order_item: OrderItem | None = None,
    parent: Entitlement | None = None,
    actor: User | None = None,
    reason: str = "",
    download_limit: int | None = None,
) -> tuple[Entitlement, bool]:
    """Create an entitlement once. Returns (entitlement, created)."""
    existing = db.session.scalar(select(Entitlement).where(Entitlement.grant_key == grant_key))
    if existing is not None:
        return existing, False
    entitlement = Entitlement(
        grant_key=grant_key,
        customer_id=customer.id,
        product_id=product.id,
        source=source,
        order_id=order.id if order else None,
        order_item_id=order_item.id if order_item else None,
        parent_id=parent.id if parent else None,
        purchased_versions=purchased_versions(product) if not product.is_bundle else {},
        download_limit=download_limit,
        granted_by_id=actor.id if actor else None,
    )
    try:
        with db.session.begin_nested():
            db.session.add(entitlement)
            db.session.flush()
    except IntegrityError:
        # Another worker granted it at the same moment: use theirs.
        existing = db.session.scalar(select(Entitlement).where(Entitlement.grant_key == grant_key))
        return existing, False
    db.session.add(
        EntitlementEvent(
            entitlement_id=entitlement.id,
            action="granted",
            reason=reason or source,
            actor_id=actor.id if actor else None,
        )
    )
    return entitlement, True


def grant_for_order(order: Order) -> list[Entitlement]:
    """Entitlements for every item of a paid order (bundles expanded from the snapshot)."""
    from ...payments.config import get_settings

    limit = get_settings().get("payments.download_limit")
    created: list[Entitlement] = []
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product is None:
            continue
        parent, made = _grant(
            customer=order.customer,
            product=product,
            source="purchase",
            grant_key=f"order-item:{item.id}",
            order=order,
            order_item=item,
            reason=f"Order {order.number}",
            download_limit=limit,
        )
        if made:
            created.append(parent)
        for content in item.bundle_contents or []:
            child = db.session.get(Product, content.get("product_id"))
            if child is None:
                continue
            ent, made = _grant(
                customer=order.customer,
                product=child,
                source="bundle",
                grant_key=f"order-item:{item.id}:product:{child.id}",
                order=order,
                order_item=item,
                parent=parent,
                reason=f"Bundle “{item.title}” in order {order.number}",
                download_limit=limit,
            )
            if made:
                created.append(ent)
    return created


def claim_free(customer: Customer, product: Product) -> tuple[Entitlement, bool]:
    if product.pricing_model != "free":
        raise ValidationError(details={"product": ["This product is not free."]})
    state = catalogue.readiness(product)
    if not state["purchasable"]:
        raise ConflictError("This resource isn't available right now.")
    entitlement, created = _grant(
        customer=customer,
        product=product,
        source="free",
        grant_key=f"free:{customer.id}:{product.id}",
        reason="Free resource",
    )
    if not created and entitlement.status == "revoked":
        raise ConflictError("Access to this resource was removed. Contact us if this is a mistake.")
    if created and product.is_bundle:
        for child in catalogue.bundle_products(product):
            _grant(
                customer=customer,
                product=child,
                source="bundle",
                grant_key=f"free:{customer.id}:{product.id}:product:{child.id}",
                parent=entitlement,
                reason=f"Included in free bundle “{product.title}”",
            )
    if created:
        audit_service.record(
            "entitlement.free_claimed", "customer", customer.id, details={"product_id": product.id}
        )
    return entitlement, created


def grant_manual(customer: Customer, product: Product, reason: str, actor: User) -> Entitlement:
    if not reason or len(reason) > 300:
        raise ValidationError(details={"reason": ["Explain why access is granted (max 300)."]})
    entitlement, _ = _grant(
        customer=customer,
        product=product,
        source="manual",
        grant_key=f"manual:{secrets.token_hex(8)}",
        actor=actor,
        reason=reason,
    )
    audit_service.record(
        "entitlement.granted",
        "entitlement",
        entitlement.id,
        actor=actor,
        details={"customer_id": customer.id, "product_id": product.id, "reason": reason},
    )
    return entitlement


def revoke(
    entitlement: Entitlement, reason: str, actor: User | None, *, cascade: bool = True
) -> int:
    """Block new downloads. Returns how many entitlements were revoked."""
    count = 0
    if entitlement.status == "active":
        entitlement.status = "revoked"
        entitlement.revoked_at = _now()
        entitlement.revoked_reason = reason[:300]
        db.session.add(
            EntitlementEvent(
                entitlement_id=entitlement.id,
                action="revoked",
                reason=reason[:300],
                actor_id=actor.id if actor else None,
            )
        )
        count += 1
    if cascade:
        for child in db.session.scalars(
            select(Entitlement).where(Entitlement.parent_id == entitlement.id)
        ):
            count += revoke(child, reason, actor, cascade=True)
    if count:
        audit_service.record(
            "entitlement.revoked",
            "entitlement",
            entitlement.id,
            actor=actor,
            details={"reason": reason[:300], "count": count},
        )
    return count


def restore(entitlement: Entitlement, reason: str, actor: User) -> Entitlement:
    if entitlement.status != "revoked":
        raise ConflictError("This access is not revoked.")
    if entitlement.customer.status not in ("active", "guest"):
        raise ConflictError("The customer account is not active.")
    entitlement.status = "active"
    entitlement.revoked_at = None
    entitlement.revoked_reason = ""
    db.session.add(
        EntitlementEvent(
            entitlement_id=entitlement.id, action="restored", reason=reason[:300], actor_id=actor.id
        )
    )
    audit_service.record(
        "entitlement.restored",
        "entitlement",
        entitlement.id,
        actor=actor,
        details={"reason": reason},
    )
    return entitlement


# ---- what a customer can download ------------------------------------------------------


def accessible_files(entitlement: Entitlement) -> list[dict[str, Any]]:
    """Files (and versions) this entitlement may download, per the version policy."""
    product = entitlement.product
    if product.is_bundle:
        return []
    purchased = entitlement.purchased_versions or {}
    out = []
    for file in product.files:
        bought_id = purchased.get(str(file.id))
        bought = next((v for v in file.versions if v.id == bought_id), None)
        current = file.current_version
        options = []
        if file.status == "active" and current is not None and current.deliverable:
            options.append(("latest", current))
        if bought is not None and bought.deliverable and (not options or bought.id != current.id):
            options.append(("purchased", bought))
        if not options:
            continue
        out.append(
            {
                "file": file,
                "versions": options,
            }
        )
    return out


def account_scope(customer: Customer):
    """Entitlements a signed-in customer sees in their account.

    Purchases made with guest checkout only count once the account's email address is
    confirmed: whoever registered with an address doesn't get what its owner bought
    until they prove they own the mailbox.
    """
    condition = Entitlement.customer_id == customer.id
    if customer.email_verified_at is None:
        condition = condition & (
            Entitlement.order_id.is_(None)
            | Entitlement.order_id.in_(select(Order.id).where(Order.is_guest.is_(False)))
        )
    return condition


def guest_scope(customer: Customer):
    """Entitlements reachable through a guest access link: guest-checkout purchases only."""
    return (Entitlement.customer_id == customer.id) & Entitlement.order_id.in_(
        select(Order.id).where(Order.is_guest.is_(True))
    )


def library(customer: Customer, *, scope=None) -> list[dict[str, Any]]:
    entitlements = db.session.scalars(
        select(Entitlement)
        .where(account_scope(customer) if scope is None else scope)
        .order_by(Entitlement.granted_at.desc())
    ).all()
    seen: set[int] = set()
    items = []
    for ent in entitlements:
        product = ent.product
        snapshot = product.published_snapshot or {}
        files = accessible_files(ent) if ent.status == "active" else []
        if product.is_bundle:
            included = [
                c.product.title
                for c in db.session.scalars(
                    select(Entitlement).where(Entitlement.parent_id == ent.id)
                )
            ]
        else:
            included = []
        duplicate = product.id in seen and ent.status == "active"
        seen.add(product.id)
        items.append(
            {
                "id": ent.id,
                "product": {
                    "id": product.public_id,
                    "title": snapshot.get("title") or product.title,
                    "slug": product.published_slug if product.status == "published" else None,
                    "type": product.product_type,
                    "cover_theme": snapshot.get("cover_theme") or product.cover_theme,
                    "cover": catalogue._Media([snapshot]).image(snapshot.get("cover_media_id"))
                    if snapshot
                    else None,
                },
                "source": ent.source,
                "status": ent.status,
                "revoked_reason": ent.revoked_reason if ent.status == "revoked" else "",
                "granted_at": iso(ent.granted_at),
                "order_number": db.session.get(Order, ent.order_id).number
                if ent.order_id
                else None,
                "download_count": ent.download_count,
                "download_limit": ent.download_limit,
                "includes": included,
                "duplicate": duplicate,
                "files": [
                    {
                        "file_id": f["file"].public_id,
                        "title": f["file"].title,
                        "description": f["file"].description,
                        "versions": [
                            {
                                "kind": kind,
                                "version_id": v.id,
                                "version": v.version,
                                "format": v.file_format.upper(),
                                "size_bytes": v.size_bytes,
                                "updated_at": iso(v.created_at),
                            }
                            for kind, v in f["versions"]
                        ],
                    }
                    for f in files
                ],
            }
        )
    return items


def entitlement_dict(e: Entitlement) -> dict[str, Any]:
    events = db.session.scalars(
        select(EntitlementEvent)
        .where(EntitlementEvent.entitlement_id == e.id)
        .order_by(EntitlementEvent.created_at)
    ).all()
    return {
        "id": e.id,
        "customer": {"id": e.customer_id, "email": e.customer.email},
        "product": {"id": e.product_id, "title": e.product.title},
        "source": e.source,
        "status": e.status,
        "order_id": e.order_id,
        "order_number": db.session.get(Order, e.order_id).number if e.order_id else None,
        "parent_id": e.parent_id,
        "download_count": e.download_count,
        "download_limit": e.download_limit,
        "granted_at": iso(e.granted_at),
        "revoked_at": iso(e.revoked_at),
        "revoked_reason": e.revoked_reason,
        "purchased_versions": e.purchased_versions or {},
        "events": [
            {
                "action": ev.action,
                "reason": ev.reason,
                "actor": ev.actor.display_name if ev.actor else None,
                "at": iso(ev.created_at),
            }
            for ev in events
        ],
    }


def list_entitlements(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Entitlement).join(Customer, Customer.id == Entitlement.customer_id)
    if args.get("q"):
        like = f"%{args['q'].lower()}%"
        stmt = stmt.where(func.lower(Customer.email).like(like))
    if args.get("status"):
        stmt = stmt.where(Entitlement.status == args["status"])
    if args.get("product_id"):
        stmt = stmt.where(Entitlement.product_id == args["product_id"])
    if args.get("customer_id"):
        stmt = stmt.where(Entitlement.customer_id == args["customer_id"])
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery()))
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(Entitlement.granted_at.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return [entitlement_dict(e) for e in rows], total or 0


def get_entitlement(entitlement_id: int) -> Entitlement:
    entitlement = db.session.get(Entitlement, entitlement_id)
    if entitlement is None:
        raise NotFoundError("Access record not found.")
    return entitlement


def downloads_for_order(order: Order) -> int:
    return (
        db.session.scalar(
            select(func.count(DownloadEvent.id))
            .join(Entitlement, Entitlement.id == DownloadEvent.entitlement_id)
            .where(Entitlement.order_id == order.id, DownloadEvent.status == "served")
        )
        or 0
    )


def file_in_product(product: Product, file_public_id: str) -> ProductFile | None:
    return next((f for f in product.files if f.public_id == file_public_id), None)
