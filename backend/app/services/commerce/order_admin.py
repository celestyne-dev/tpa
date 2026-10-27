"""Order administration, customer administration and revenue reporting."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...commerce.currency import money
from ...extensions import db
from ...models import (
    AuditLog,
    Customer,
    DownloadEvent,
    EmailDelivery,
    Entitlement,
    Order,
    OrderItem,
    PaymentAttempt,
    PaymentEvent,
    PaymentTransaction,
    Receipt,
    Refund,
    User,
)
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import entitlements as ent_service
from .payments import event_dict, receipt_dict, refund_dict, refundable_minor


def _parse_date(value: str | None, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
    except ValueError:
        raise ValidationError(details={"date": ["Use YYYY-MM-DD."]}) from None
    return day + timedelta(days=1) if end else day


def order_summary(o: Order) -> dict[str, Any]:
    return {
        "id": o.id,
        "number": o.number,
        "status": o.status,
        "mode": o.mode,
        "email": o.email,
        "customer_id": o.customer_id,
        "currency": o.currency,
        "total": money(o.total_minor, o.currency),
        "refunded": money(o.refunded_minor, o.currency),
        "item_count": len(o.items),
        "needs_review": o.needs_review,
        "created_at": iso(o.created_at),
        "paid_at": iso(o.paid_at),
    }


def list_orders(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Order)
    if args.get("q"):
        q = args["q"].strip().lower()
        refs = select(PaymentAttempt.order_id).where(
            func.lower(PaymentAttempt.reference).like(f"%{q}%")
        )
        stmt = stmt.where(
            or_(
                func.lower(Order.number).like(f"%{q}%"),
                func.lower(Order.email).like(f"%{q}%"),
                Order.id.in_(refs),
            )
        )
    if args.get("status"):
        stmt = stmt.where(Order.status == args["status"])
    if args.get("mode"):
        stmt = stmt.where(Order.mode == args["mode"])
    if args.get("currency"):
        stmt = stmt.where(Order.currency == args["currency"].upper())
    if args.get("needs_review"):
        stmt = stmt.where(Order.needs_review.is_(True))
    if start := _parse_date(args.get("date_from")):
        stmt = stmt.where(Order.created_at >= start)
    if end := _parse_date(args.get("date_to"), end=True):
        stmt = stmt.where(Order.created_at < end)
    if args.get("customer_id"):
        stmt = stmt.where(Order.customer_id == args["customer_id"])
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    return [order_summary(o) for o in rows], total


def get_order(order_id: int) -> Order:
    order = db.session.get(Order, order_id)
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def order_detail(order: Order, actor: User) -> dict[str, Any]:
    granted = effective_permissions(actor)
    data = order_summary(order) | {
        "public_id": order.public_id,
        "subtotal": money(order.subtotal_minor, order.currency),
        "tax": money(order.tax_minor, order.currency),
        "discount": money(order.discount_minor, order.currency),
        "refundable": money(refundable_minor(order), order.currency),
        "review_reason": order.review_reason,
        "terms_version": order.terms_version,
        "terms_accepted_at": iso(order.terms_accepted_at),
        "expires_at": iso(order.expires_at),
        "cancelled_at": iso(order.cancelled_at),
        "failed_at": iso(order.failed_at),
        "notes": order.notes,
        "guest_checkout": order.is_guest,
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "title": i.title,
                "type": i.product_type,
                "amount": money(i.line_total_minor, i.currency),
                "compare_at": money(i.compare_at_minor, i.currency) if i.compare_at_minor else None,
                "includes": i.bundle_contents or [],
            }
            for i in order.items
        ],
        "customer": {
            "id": order.customer.id,
            "email": order.customer.email,
            "display_name": order.customer.display_name,
            "status": order.customer.status,
        },
        "attempts": [
            {
                "id": a.id,
                "reference": a.reference,
                "status": a.status,
                "mode": a.mode,
                "amount": money(a.amount_minor, a.currency),
                "provider_status": a.provider_status,
                "failure_reason": a.failure_reason,
                "created_at": iso(a.created_at),
                "verified_at": iso(a.verified_at),
            }
            for a in order.attempts
        ],
        "transactions": [
            {
                "kind": t.kind,
                "provider_id": t.provider_id,
                "reference": t.reference,
                "status": t.status,
                "mode": t.mode,
                "amount": money(t.amount_minor, t.currency),
                "channel": t.channel,
                "occurred_at": iso(t.occurred_at),
            }
            for t in db.session.scalars(
                select(PaymentTransaction).where(PaymentTransaction.order_id == order.id)
            )
        ],
        "refunds": [
            refund_dict(r)
            for r in db.session.scalars(
                select(Refund).where(Refund.order_id == order.id).order_by(Refund.created_at)
            )
        ],
        "receipt": receipt_dict(
            db.session.scalar(select(Receipt).where(Receipt.order_id == order.id))
        ),
        "emails": [
            {"template": e.template, "status": e.status, "at": iso(e.created_at)}
            for e in db.session.scalars(
                select(EmailDelivery)
                .where(EmailDelivery.order_id == order.id)
                .order_by(EmailDelivery.created_at)
            )
        ],
        "downloads": ent_service.downloads_for_order(order),
        "can": {
            "manage": P.ORDERS_MANAGE.value in granted,
            "refund": P.REFUNDS_ISSUE.value in granted,
            "entitlements": P.ENTITLEMENTS_MANAGE.value in granted,
        },
    }
    if P.ENTITLEMENTS_VIEW.value in granted:
        data["entitlements"] = [
            ent_service.entitlement_dict(e)
            for e in db.session.scalars(select(Entitlement).where(Entitlement.order_id == order.id))
        ]
    if P.PAYMENTS_VIEW_EVENTS.value in granted:
        references = [a.reference for a in order.attempts]
        data["events"] = [
            event_dict(e)
            for e in db.session.scalars(
                select(PaymentEvent)
                .where(
                    or_(
                        PaymentEvent.order_id == order.id,
                        PaymentEvent.reference.in_(references or [""]),
                    )
                )
                .order_by(PaymentEvent.received_at)
            )
        ]
    if P.AUDIT_VIEW.value in granted or P.ORDERS_VIEW.value in granted:
        data["audit"] = [
            {
                "action": a.action,
                "actor": a.actor.display_name if a.actor else "System",
                "details": a.details,
                "at": iso(a.created_at),
            }
            for a in db.session.scalars(
                select(AuditLog)
                .where(AuditLog.resource_type == "order", AuditLog.resource_id == str(order.id))
                .order_by(AuditLog.created_at)
            )
        ]
    return data


def add_note(order: Order, note: Any, actor: User) -> Order:
    if not isinstance(note, str) or not note.strip() or len(note) > 500:
        raise ValidationError(details={"note": ["Write a note of up to 500 characters."]})
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    order.notes = (
        f"{order.notes}\n" if order.notes else ""
    ) + f"[{stamp} {actor.display_name}] {note.strip()}"
    order.notes = order.notes[-2000:]
    audit_service.record("order.note_added", "order", order.id, actor=actor)
    return order


def export_orders_csv(args: dict[str, Any]) -> str:
    args = {**args, "page": 1, "page_size": 10000}
    rows, _ = list_orders(args)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "number",
            "created_at",
            "paid_at",
            "status",
            "mode",
            "email",
            "currency",
            "total",
            "refunded",
            "items",
        ]
    )
    for r in rows:
        order = db.session.get(Order, r["id"])
        writer.writerow(
            [
                r["number"],
                r["created_at"],
                r["paid_at"] or "",
                r["status"],
                r["mode"],
                r["email"],
                r["currency"],
                r["total"]["amount"],
                r["refunded"]["amount"],
                "; ".join(i.title for i in order.items),
            ]
        )
    return out.getvalue()


# ---- customers --------------------------------------------------------------------------


def customer_summary(c: Customer) -> dict[str, Any]:
    paid = db.session.scalar(
        select(func.count(Order.id)).where(
            Order.customer_id == c.id, Order.status.in_(("paid", "partially_refunded", "refunded"))
        )
    )
    return {
        "id": c.id,
        "email": c.email,
        "display_name": c.display_name,
        "status": c.status,
        "email_verified": c.email_verified_at is not None,
        "is_test_account": c.is_test_account,
        "paid_orders": paid or 0,
        "created_at": iso(c.created_at),
        "last_login_at": iso(c.last_login_at),
    }


def list_customers(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    stmt = select(Customer)
    if args.get("q"):
        like = f"%{args['q'].strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Customer.email).like(like), func.lower(Customer.display_name).like(like))
        )
    if args.get("status"):
        stmt = stmt.where(Customer.status == args["status"])
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(Customer.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    return [customer_summary(c) for c in rows], total


def get_customer(customer_id: int) -> Customer:
    customer = db.session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def customer_detail(c: Customer, actor: User) -> dict[str, Any]:
    granted = effective_permissions(actor)
    data = customer_summary(c) | {
        "support_notes": c.support_notes,
        "deletion_requested_at": iso(c.deletion_requested_at),
        "orders": [
            order_summary(o)
            for o in db.session.scalars(
                select(Order).where(Order.customer_id == c.id).order_by(Order.created_at.desc())
            )
        ]
        if P.ORDERS_VIEW.value in granted
        else None,
        "emails": [
            {"template": e.template, "status": e.status, "at": iso(e.created_at)}
            for e in db.session.scalars(
                select(EmailDelivery)
                .where(EmailDelivery.customer_id == c.id)
                .order_by(EmailDelivery.created_at.desc())
                .limit(20)
            )
        ],
        "can": {
            "support": P.CUSTOMERS_SUPPORT.value in granted,
            "manage": P.CUSTOMERS_MANAGE.value in granted,
            "entitlements": P.ENTITLEMENTS_MANAGE.value in granted,
        },
    }
    if P.ENTITLEMENTS_VIEW.value in granted:
        data["entitlements"] = [
            ent_service.entitlement_dict(e)
            for e in db.session.scalars(
                select(Entitlement)
                .where(Entitlement.customer_id == c.id)
                .order_by(Entitlement.granted_at.desc())
            )
        ]
    if P.DOWNLOADS_AUDIT.value in granted:
        data["downloads"] = [
            download_dict(d)
            for d in db.session.scalars(
                select(DownloadEvent)
                .where(DownloadEvent.customer_id == c.id)
                .order_by(DownloadEvent.created_at.desc())
                .limit(50)
            )
        ]
    return data


def download_dict(d: DownloadEvent) -> dict[str, Any]:
    from ...models import Product, ProductFileVersion

    product = db.session.get(Product, d.product_id) if d.product_id else None
    version = db.session.get(ProductFileVersion, d.file_version_id) if d.file_version_id else None
    return {
        "id": d.id,
        "status": d.status,
        "reason": d.reason,
        "product": product.title if product else None,
        "file": f"{version.file.title} v{version.version}" if version else None,
        "customer_id": d.customer_id,
        "ip_address": d.ip_address,
        "at": iso(d.created_at),
    }


def list_downloads(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    stmt = select(DownloadEvent)
    if args.get("status"):
        stmt = stmt.where(DownloadEvent.status == args["status"])
    if str(args.get("product_id") or "").isdigit():
        stmt = stmt.where(DownloadEvent.product_id == int(args["product_id"]))
    if args.get("reason"):
        stmt = stmt.where(DownloadEvent.reason == args["reason"])
    if args.get("customer_id"):
        stmt = stmt.where(DownloadEvent.customer_id == args["customer_id"])
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 50)
    rows = db.session.scalars(
        stmt.order_by(DownloadEvent.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    return [download_dict(d) for d in rows], total


def download_summary(days: int = 30) -> dict[str, Any]:
    """Download activity for the last ``days`` days: daily counts, top resources and why
    requests were refused (revoked, expired, limit reached, expired links …)."""
    from datetime import UTC, datetime, timedelta

    from ...models import Product

    since = datetime.now(UTC) - timedelta(days=days)
    recent = DownloadEvent.created_at >= since
    by_status = dict(
        db.session.execute(
            select(DownloadEvent.status, func.count(DownloadEvent.id))
            .where(recent)
            .group_by(DownloadEvent.status)
        ).all()
    )
    day = func.date(DownloadEvent.created_at)
    daily: dict[str, dict[str, int]] = {}
    for d, status, count in db.session.execute(
        select(day, DownloadEvent.status, func.count(DownloadEvent.id))
        .where(recent)
        .group_by(day, DownloadEvent.status)
    ).all():
        daily.setdefault(str(d), {"served": 0, "denied": 0, "authorized": 0})[status] = count
    top = db.session.execute(
        select(Product.id, Product.title, func.count(DownloadEvent.id).label("n"))
        .join(Product, Product.id == DownloadEvent.product_id)
        .where(recent, DownloadEvent.status == "served")
        .group_by(Product.id, Product.title)
        .order_by(func.count(DownloadEvent.id).desc())
        .limit(10)
    ).all()
    reasons = db.session.execute(
        select(DownloadEvent.reason, func.count(DownloadEvent.id))
        .where(recent, DownloadEvent.status == "denied")
        .group_by(DownloadEvent.reason)
        .order_by(func.count(DownloadEvent.id).desc())
    ).all()
    return {
        "days": days,
        "served": by_status.get("served", 0),
        "authorized": by_status.get("authorized", 0),
        "denied": by_status.get("denied", 0),
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "top_resources": [{"product_id": i, "title": t, "downloads": n} for i, t, n in top],
        "denial_reasons": [{"reason": r or "unknown", "count": n} for r, n in reasons],
    }


def update_customer(c: Customer, data: dict[str, Any], actor: User) -> Customer:
    granted = effective_permissions(actor)
    allowed = {"status", "is_test_account", "support_notes"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValidationError(details={"_unknown": ["Unknown field(s)."]})
    from ...utils.errors import ForbiddenError

    if ("status" in data or "is_test_account" in data) and P.CUSTOMERS_MANAGE.value not in granted:
        raise ForbiddenError()
    if "support_notes" in data and not (
        {P.CUSTOMERS_SUPPORT.value, P.CUSTOMERS_MANAGE.value} & granted
    ):
        raise ForbiddenError()
    if c.status == "deleted":
        raise ConflictError("This account has been deleted and anonymised.")
    changes = {}
    if "status" in data:
        if data["status"] not in ("active", "disabled"):
            raise ValidationError(details={"status": ["Use active or disabled."]})
        if data["status"] == "active" and c.password_hash is None:
            # A guest-checkout buyer record (never registered) goes back to being one.
            data = {**data, "status": "guest"}
        if data["status"] != c.status:
            changes["status"] = data["status"]
            c.status = data["status"]
            if c.status == "disabled":
                from ...auth.customer_session import revoke_all

                revoke_all(c)
    if "is_test_account" in data:
        if not isinstance(data["is_test_account"], bool):
            raise ValidationError(details={"is_test_account": ["Must be true or false."]})
        changes["is_test_account"] = data["is_test_account"]
        c.is_test_account = data["is_test_account"]
    if "support_notes" in data:
        note = data["support_notes"]
        if not isinstance(note, str) or len(note) > 2000:
            raise ValidationError(details={"support_notes": ["Up to 2000 characters."]})
        c.support_notes = note.strip()
        changes["support_notes"] = "changed"
    audit_service.record("customer.updated", "customer", c.id, actor=actor, details=changes)
    return c


# ---- reporting --------------------------------------------------------------------------


def revenue_report(args: dict[str, Any]) -> dict[str, Any]:
    """Per-currency totals; currencies are never added together (no conversion policy)."""
    mode = args.get("mode") or "live"
    if mode not in ("live", "test"):
        raise ValidationError(details={"mode": ["Use live or test."]})
    start = _parse_date(args.get("date_from"))
    end = _parse_date(args.get("date_to"), end=True)

    def window(column):
        conds = []
        if start:
            conds.append(column >= start)
        if end:
            conds.append(column < end)
        return conds

    orders_created = db.session.execute(
        select(Order.currency, Order.status, func.count(Order.id))
        .where(Order.mode == mode, *window(Order.created_at))
        .group_by(Order.currency, Order.status)
    ).all()
    charges = db.session.execute(
        select(
            PaymentTransaction.currency,
            func.count(PaymentTransaction.id),
            func.sum(PaymentTransaction.amount_minor),
        )
        .where(
            PaymentTransaction.kind == "charge",
            PaymentTransaction.mode == mode,
            *window(PaymentTransaction.created_at),
        )
        .group_by(PaymentTransaction.currency)
    ).all()
    refunds = db.session.execute(
        select(
            PaymentTransaction.currency,
            func.count(PaymentTransaction.id),
            func.sum(PaymentTransaction.amount_minor),
        )
        .where(
            PaymentTransaction.kind == "refund",
            PaymentTransaction.mode == mode,
            *window(PaymentTransaction.created_at),
        )
        .group_by(PaymentTransaction.currency)
    ).all()
    currencies: dict[str, dict[str, Any]] = {}

    def bucket(code):
        return currencies.setdefault(
            code,
            {
                "currency": code,
                "orders": 0,
                "paid_orders": 0,
                "failed_orders": 0,
                "gross_minor": 0,
                "refunds_minor": 0,
                "refund_count": 0,
                "charge_count": 0,
            },
        )

    for code, status, count in orders_created:
        b = bucket(code)
        b["orders"] += count
        if status in ("paid", "partially_refunded", "refunded"):
            b["paid_orders"] += count
        if status == "failed":
            b["failed_orders"] += count
    for code, count, total in charges:
        b = bucket(code)
        b["charge_count"], b["gross_minor"] = count, int(total or 0)
    for code, count, total in refunds:
        b = bucket(code)
        b["refund_count"], b["refunds_minor"] = count, int(total or 0)
    for b in currencies.values():
        b["net_minor"] = b["gross_minor"] - b["refunds_minor"]
        for key in ("gross", "refunds", "net"):
            b[key] = money(b[f"{key}_minor"], b["currency"])
    failed_attempts = db.session.scalar(
        select(func.count(PaymentAttempt.id)).where(
            PaymentAttempt.mode == mode,
            PaymentAttempt.status.in_(("failed", "abandoned", "mismatch")),
            *window(PaymentAttempt.created_at),
        )
    )
    by_product_rows = db.session.execute(
        select(
            OrderItem.product_id,
            OrderItem.title,
            OrderItem.currency,
            func.count(OrderItem.id),
            func.sum(OrderItem.line_total_minor),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.mode == mode,
            Order.status.in_(("paid", "partially_refunded", "refunded")),
            *window(Order.paid_at),
        )
        .group_by(OrderItem.product_id, OrderItem.title, OrderItem.currency)
    ).all()
    by_product = [
        {
            "product_id": pid,
            "title": title,
            "currency": cur,
            "units": units,
            "revenue": money(int(total or 0), cur),
        }
        for pid, title, cur, units, total in by_product_rows
    ]
    by_product.sort(key=lambda r: (-r["units"], r["title"]))
    downloads = db.session.execute(
        select(DownloadEvent.product_id, func.count(DownloadEvent.id))
        .where(DownloadEvent.status == "served", *window(DownloadEvent.created_at))
        .group_by(DownloadEvent.product_id)
    ).all()
    from ...models import Product

    download_rows = [
        {
            "product_id": pid,
            "title": (db.session.get(Product, pid).title if pid else "—"),
            "downloads": n,
        }
        for pid, n in downloads
    ]
    download_rows.sort(key=lambda r: -r["downloads"])
    free_claims = db.session.scalar(
        select(func.count(Entitlement.id)).where(
            Entitlement.source == "free", *window(Entitlement.granted_at)
        )
    )
    return {
        "mode": mode,
        "date_from": args.get("date_from"),
        "date_to": args.get("date_to"),
        "currencies": sorted(currencies.values(), key=lambda b: b["currency"]),
        "failed_payment_attempts": failed_attempts or 0,
        "by_product": by_product,
        "downloads": download_rows,
        "total_downloads": sum(r["downloads"] for r in download_rows),
        "free_claims": free_claims or 0,
        "notes": [
            "Gross = provider-verified charges. Refunds = refunds confirmed by the provider or "
            "recorded with a provider reference. Net = gross minus refunds, before provider fees.",
            "Each currency is reported separately; amounts in different currencies are never "
            "added together because no conversion policy is configured.",
            "Test-mode transactions are excluded from live figures (switch the mode to see them).",
        ],
    }


def export_revenue_csv(args: dict[str, Any]) -> str:
    report = revenue_report(args)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["mode", report["mode"], "from", report["date_from"] or "", "to", report["date_to"] or ""]
    )
    writer.writerow(
        ["currency", "orders", "paid_orders", "failed_orders", "gross", "refunds", "net"]
    )
    for b in report["currencies"]:
        writer.writerow(
            [
                b["currency"],
                b["orders"],
                b["paid_orders"],
                b["failed_orders"],
                b["gross"]["amount"],
                b["refunds"]["amount"],
                b["net"]["amount"],
            ]
        )
    writer.writerow([])
    writer.writerow(["product", "currency", "units", "revenue"])
    for r in report["by_product"]:
        writer.writerow([r["title"], r["currency"], r["units"], r["revenue"]["amount"]])
    return out.getvalue()
