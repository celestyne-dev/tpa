"""Membership plans: CMS content, immutable prices and included products (Batch 10.1).

Authorisation is checked here, never only in the admin UI:

- ``memberships.view``: read plans, prices and included products in the admin;
- ``memberships.manage``: create and edit plans, add or retire prices, choose included
  products;
- ``memberships.publish``: publish, unpublish and archive plans.

Rules:
- Prices are append-only. A price is never edited; a new price for the same interval
  replaces it and the old row is retired. A price that has been public (``shown_at``)
  can never be deleted. Amounts are integers in minor units; only USD is offered for now
  and nothing is ever converted.
- Only products marked ``membership_eligible`` (premium resources and course products,
  never bundles, free items or membership products) can be included.
- At most ``MAX_PUBLISHED_PLANS`` plans are published at once (one paid tier initially).
- Billing is not available yet (``billing_status``): no checkout, subscriptions or
  entitlement grants happen in this batch.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...commerce.currency import MAX_AMOUNT_MINOR, money, parse_major
from ...commerce.product_types import type_label
from ...extensions import db
from ...models import MembershipPlan, MembershipPlanAccess, MembershipPlanPrice, Product, User
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..admin.common import resolve_slug
from ..commerce import catalogue
from ..serializers import iso

PLAN_CURRENCIES = ("USD",)
INTERVALS = ("month", "year")
MAX_PUBLISHED_PLANS = 1
MAX_BENEFITS = 12
MIN_AMOUNT_MINOR = 100  # USD 1.00: a sanity floor, not a pricing rule
PLAN_FIELDS = {"name", "slug", "tagline", "description", "benefits", "tier_rank", "lock_version"}


class EditConflictError(ConflictError):
    code = "edit_conflict"
    message = "Someone else changed this plan after you opened it. Reload and try again."


def _now() -> datetime:
    return datetime.now(UTC)


def _require(actor: User, *perms: P) -> None:
    granted = effective_permissions(actor)
    if not all(p.value in granted for p in perms):
        raise ForbiddenError()


def _check_lock(plan: MembershipPlan, data: Any) -> None:
    version = data.get("lock_version") if isinstance(data, dict) else None
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(details={"lock_version": ["Reload before saving (missing version)."]})
    if version != plan.lock_version:
        raise EditConflictError(details={"lock_version": plan.lock_version})


def _touch(plan: MembershipPlan, actor: User) -> None:
    plan.lock_version += 1
    plan.updated_by_id = actor.id


def billing_status() -> dict[str, Any]:
    """Whether membership checkout is open (Batch 10.2: test mode only, see billing)."""
    from .billing import billing_status as status

    return status()


# ---- lookups and serialisation -------------------------------------------------------------


def get_plan(public_id: str) -> MembershipPlan:
    plan = db.session.scalar(select(MembershipPlan).where(MembershipPlan.public_id == public_id))
    if plan is None:
        raise NotFoundError("Membership plan not found.")
    return plan


def price_dict(price: MembershipPlanPrice) -> dict[str, Any]:
    return {
        "id": price.public_id,
        "interval": price.interval,
        "status": price.status,
        "price": money(price.amount_minor, price.currency),
        "created_at": iso(price.created_at),
        "shown_at": iso(price.shown_at),
        "retired_at": iso(price.retired_at),
    }


def eligibility_problem(product: Product) -> str | None:
    """Why a product can't be part of a membership (None when it can)."""
    if product.is_bundle:
        return "Bundles can't be included; include their resources one by one."
    if product.product_type == "membership":
        return "Membership products can't be included in a plan."
    if not product.membership_eligible:
        return "Not marked as included in memberships (Resource access settings)."
    if product.status == "archived":
        return "This product is archived."
    if product.pricing_model == "free":
        return "Free resources are already available to everyone."
    return None


def _product_item(product: Product) -> dict[str, Any]:
    course = catalogue.course_link(product)
    return {
        "product_id": product.public_id,
        "title": product.title,
        "type": product.product_type,
        "type_label": type_label(product.product_type),
        "kind": "course" if product.product_type == "course" else "resource",
        "status": product.status,
        "slug": product.published_slug if product.status == "published" else None,
        "course": course,
    }


def plan_summary(plan: MembershipPlan) -> dict[str, Any]:
    active = {p.interval: price_dict(p) for p in plan.active_prices}
    return {
        "id": plan.public_id,
        "slug": plan.slug,
        "name": plan.name,
        "tagline": plan.tagline,
        "tier_rank": plan.tier_rank,
        "status": plan.status,
        "prices": active,
        "included_count": len(plan.access),
        "published_at": iso(plan.published_at),
        "updated_at": iso(plan.updated_at),
        "lock_version": plan.lock_version,
    }


def readiness(plan: MembershipPlan) -> list[str]:
    """What keeps a plan from being published."""
    problems = []
    if not plan.description.strip():
        problems.append("Add a description.")
    if not plan.benefits:
        problems.append("Add at least one benefit.")
    if not plan.active_prices:
        problems.append("Add a monthly or yearly price.")
    published = [
        a
        for a in plan.access
        if a.product.status == "published" and not eligibility_problem(a.product)
    ]
    if not published:
        problems.append("Include at least one published, membership-eligible course or resource.")
    return problems


def plan_detail(plan: MembershipPlan, actor: User) -> dict[str, Any]:
    _require(actor, P.MEMBERSHIPS_VIEW)
    return {
        **plan_summary(plan),
        "description": plan.description,
        "benefits": plan.benefits or [],
        "first_published_at": iso(plan.first_published_at),
        "archived_at": iso(plan.archived_at),
        "price_history": [price_dict(p) for p in reversed(plan.prices)],
        "included": [
            {**_product_item(a.product), "problem": eligibility_problem(a.product)}
            for a in plan.access
        ],
        "readiness": readiness(plan),
        "billing": billing_status(),
        "provider_plans": _provider_plans(plan),
    }


def _provider_plans(plan: MembershipPlan) -> list[dict[str, Any]]:
    from .billing import provider_plans_dict

    return provider_plans_dict(plan)


def list_plans(actor: User) -> list[dict[str, Any]]:
    _require(actor, P.MEMBERSHIPS_VIEW)
    rows = db.session.scalars(select(MembershipPlan).order_by(MembershipPlan.tier_rank))
    return [plan_summary(p) for p in rows]


def eligible_products(actor: User, q: str = "") -> list[dict[str, Any]]:
    """Products an editor can include: membership-eligible courses and resources."""
    _require(actor, P.MEMBERSHIPS_VIEW)
    stmt = (
        select(Product)
        .where(Product.membership_eligible.is_(True), Product.status != "archived")
        .order_by(Product.title)
    )
    q = (q or "").strip()[:100]
    if q:
        stmt = stmt.where(Product.title.ilike(f"%{q}%"))
    return [_product_item(p) for p in db.session.scalars(stmt) if not eligibility_problem(p)]


# ---- plan content -----------------------------------------------------------------------------


def _clean(data: Any, plan: MembershipPlan | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - PLAN_FIELDS
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean: dict[str, Any] = {}
    for field, limit, required in (
        ("name", 120, plan is None),
        ("tagline", 240, False),
        ("description", 6000, False),
    ):
        if field in data or required:
            value = data.get(field)
            if not isinstance(value, str) or (required and not value.strip()):
                errors[field] = ["This field is required." if required else "Must be text."]
            elif len(value.strip()) > limit:
                errors[field] = [f"At most {limit} characters."]
            elif problem := plain_text_problem(value):
                errors[field] = [problem]
            else:
                clean[field] = value.strip()
    if "benefits" in data:
        value = data["benefits"]
        if not isinstance(value, list) or len(value) > MAX_BENEFITS:
            errors["benefits"] = [f"Use a list of at most {MAX_BENEFITS} benefits."]
        else:
            items = []
            for item in value:
                if not isinstance(item, str) or not item.strip() or len(item.strip()) > 200:
                    errors["benefits"] = ["Each benefit is plain text of 1 to 200 characters."]
                    break
                if problem := plain_text_problem(item):
                    errors["benefits"] = [problem]
                    break
                items.append(item.strip())
            clean["benefits"] = items
    if "tier_rank" in data:
        rank = data["tier_rank"]
        if not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= 100:
            errors["tier_rank"] = ["Use a tier rank from 1 to 100."]
        else:
            taken = select(MembershipPlan.id).where(MembershipPlan.tier_rank == rank)
            if plan is not None:
                taken = taken.where(MembershipPlan.id != plan.id)
            if db.session.scalar(taken) is not None:
                errors["tier_rank"] = ["Another plan already uses this tier rank."]
            clean["tier_rank"] = rank
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return clean


def create_plan(data: Any, actor: User) -> MembershipPlan:
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    clean = _clean(data, None)
    clean["slug"] = resolve_slug(MembershipPlan, data.get("slug"), clean["name"])
    if "tier_rank" not in clean:
        top = db.session.scalar(select(func.max(MembershipPlan.tier_rank))) or 0
        clean["tier_rank"] = top + 1
    clean.setdefault("benefits", [])
    plan = MembershipPlan(
        public_id=secrets.token_urlsafe(12),
        status="draft",
        created_by_id=actor.id,
        updated_by_id=actor.id,
        **clean,
    )
    db.session.add(plan)
    db.session.flush()
    audit_service.record(
        "membership.plan_created",
        "membership_plan",
        plan.id,
        actor=actor,
        details={"name": plan.name, "slug": plan.slug},
    )
    return plan


def _editable(plan: MembershipPlan) -> None:
    if plan.status == "archived":
        raise ConflictError("Restore this plan to a draft before changing it.")


def update_plan(plan: MembershipPlan, data: Any, actor: User) -> MembershipPlan:
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    _editable(plan)
    clean = _clean(data, plan)
    _check_lock(plan, data)
    if "slug" in data and data["slug"] != plan.slug:
        if plan.first_published_at is not None:
            raise ValidationError(details={"slug": ["Published plans keep their address."]})
        clean["slug"] = resolve_slug(MembershipPlan, data["slug"], plan.name, exclude_id=plan.id)
    if plan.status == "published" and "benefits" in clean and not clean["benefits"]:
        raise ValidationError(details={"benefits": ["A published plan needs a benefit."]})
    if plan.status == "published" and "description" in clean and not clean["description"]:
        raise ValidationError(details={"description": ["A published plan needs a description."]})
    changed = sorted(k for k, v in clean.items() if getattr(plan, k) != v)
    for key, value in clean.items():
        setattr(plan, key, value)
    _touch(plan, actor)
    db.session.flush()
    audit_service.record(
        "membership.plan_updated",
        "membership_plan",
        plan.id,
        actor=actor,
        details={"fields": changed},
    )
    return plan


def set_status(plan: MembershipPlan, status: Any, data: Any, actor: User) -> MembershipPlan:
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_PUBLISH)
    if status not in ("draft", "published", "archived"):
        raise ValidationError(details={"status": ["Use draft, published or archived."]})
    _check_lock(plan, data)
    if status == plan.status:
        return plan
    now = _now()
    if status == "published":
        problems = readiness(plan)
        if problems:
            raise ValidationError("This plan isn't ready.", details={"readiness": problems})
        published = db.session.scalar(
            select(func.count(MembershipPlan.id)).where(
                MembershipPlan.status == "published", MembershipPlan.id != plan.id
            )
        )
        if published >= MAX_PUBLISHED_PLANS:
            raise ConflictError(
                "Only one membership tier can be published for now. Unpublish the other plan first."
            )
        plan.published_at = now
        plan.first_published_at = plan.first_published_at or now
        plan.archived_at = None
        for price in plan.active_prices:
            price.shown_at = price.shown_at or now
    elif status == "archived":
        plan.archived_at = now
    previous = plan.status
    plan.status = status
    _touch(plan, actor)
    db.session.flush()
    audit_service.record(
        f"membership.plan_{status}",
        "membership_plan",
        plan.id,
        actor=actor,
        details={"from": previous},
    )
    return plan


# ---- prices -----------------------------------------------------------------------------------


def _amount(data: dict, errors: dict) -> tuple[int | None, str]:
    currency = str(data.get("currency") or "USD").upper()
    if currency not in PLAN_CURRENCIES:
        errors["currency"] = [f"Membership prices are offered in {', '.join(PLAN_CURRENCIES)}."]
        return None, currency
    if "amount_minor" in data:
        amount = data["amount_minor"]
        if not isinstance(amount, int) or isinstance(amount, bool):
            errors["amount"] = ["Send the amount in cents as a whole number."]
            return None, currency
    else:
        try:
            amount = parse_major(str(data.get("amount", "")), currency)
        except (ValueError, ArithmeticError):
            errors["amount"] = ["Enter an amount such as 9.99."]
            return None, currency
    if not MIN_AMOUNT_MINOR <= amount <= MAX_AMOUNT_MINOR:
        errors["amount"] = ["Use an amount of at least 1.00."]
        return None, currency
    return amount, currency


def add_price(plan: MembershipPlan, data: Any, actor: User) -> MembershipPlanPrice:
    """Add the price for an interval, retiring the current one (prices are never edited)."""
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    _editable(plan)
    if not isinstance(data, dict) or set(data) - {
        "interval",
        "amount",
        "amount_minor",
        "currency",
        "lock_version",
    }:
        raise ValidationError("Send interval, amount, currency and lock_version.")
    _check_lock(plan, data)
    errors: dict[str, Any] = {}
    interval = data.get("interval")
    if interval not in INTERVALS:
        errors["interval"] = ["Choose monthly or yearly."]
    amount, currency = _amount(data, errors)
    if errors:
        raise ValidationError("The price needs attention.", details=errors)
    now = _now()
    current = next(
        (p for p in plan.active_prices if p.interval == interval and p.currency == currency), None
    )
    if current is not None:
        if current.amount_minor == amount:
            raise ConflictError("That is already the current price.")
        current.status = "retired"
        current.retired_at = now
        db.session.flush()  # free the "one active price" slot before inserting
    price = MembershipPlanPrice(
        public_id=secrets.token_urlsafe(12),
        plan_id=plan.id,
        interval=interval,
        currency=currency,
        amount_minor=amount,
        status="active",
        created_by_id=actor.id,
        shown_at=now if plan.status == "published" else None,
    )
    db.session.add(price)
    _touch(plan, actor)
    db.session.flush()
    db.session.expire(plan, ["prices"])
    audit_service.record(
        "membership.price_added",
        "membership_plan",
        plan.id,
        actor=actor,
        details={
            "price_id": price.public_id,
            "interval": interval,
            "amount_minor": amount,
            "currency": currency,
            "replaced": current.public_id if current else None,
        },
    )
    return price


def _get_price(plan: MembershipPlan, price_id: str) -> MembershipPlanPrice:
    price = next((p for p in plan.prices if p.public_id == price_id), None)
    if price is None:
        raise NotFoundError("Price not found.")
    return price


def remove_price(plan: MembershipPlan, price_id: str, data: Any, actor: User) -> None:
    """Retire a price, or delete one that was never public. A published plan keeps at
    least one active price."""
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    _editable(plan)
    _check_lock(plan, data)
    price = _get_price(plan, price_id)
    if price.status == "active" and plan.status == "published" and len(plan.active_prices) == 1:
        raise ConflictError("A published plan needs a price. Add the new price first.")
    if price.shown_at is None:
        db.session.delete(price)
        action = "membership.price_deleted"
    elif price.status == "active":
        price.status = "retired"
        price.retired_at = _now()
        action = "membership.price_retired"
    else:
        raise ConflictError("This price is already retired and kept for the record.")
    _touch(plan, actor)
    db.session.flush()
    db.session.expire(plan, ["prices"])
    audit_service.record(
        action, "membership_plan", plan.id, actor=actor, details={"price_id": price_id}
    )


# ---- included products ------------------------------------------------------------------------


def set_access(plan: MembershipPlan, data: Any, actor: User) -> MembershipPlan:
    """Replace the plan's included products (public product ids)."""
    _require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    _editable(plan)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    _check_lock(plan, data)
    wanted = data.get("product_ids")
    if (
        not isinstance(wanted, list)
        or not all(isinstance(i, str) for i in wanted)
        or len(wanted) > 500
    ):
        raise ValidationError(details={"product_ids": ["Send a list of product ids."]})
    wanted = list(dict.fromkeys(wanted))
    products = {
        p.public_id: p
        for p in db.session.scalars(select(Product).where(Product.public_id.in_(wanted or [""])))
    }
    current = {a.product.public_id: a for a in plan.access}
    problems = []
    for pid in wanted:
        product = products.get(pid)
        if product is None:
            problems.append(f"Product {pid} doesn't exist.")
        elif pid not in current and (problem := eligibility_problem(product)):
            problems.append(f"“{product.title}”: {problem}")
    if problems:
        raise ValidationError("Some products can't be included.", details={"product_ids": problems})
    if plan.status == "published" and not any(
        products[pid].status == "published" and not eligibility_problem(products[pid])
        for pid in wanted
    ):
        raise ConflictError("A published plan must include at least one published item.")
    removed = [pid for pid in current if pid not in wanted]
    added = [pid for pid in wanted if pid not in current]
    for pid in removed:
        db.session.delete(current[pid])
    for pid in added:
        db.session.add(
            MembershipPlanAccess(plan_id=plan.id, product_id=products[pid].id, added_by_id=actor.id)
        )
    _touch(plan, actor)
    db.session.flush()
    db.session.expire(plan, ["access"])
    audit_service.record(
        "membership.access_changed",
        "membership_plan",
        plan.id,
        actor=actor,
        details={"added": added, "removed": removed},
    )
    return plan


# ---- public -----------------------------------------------------------------------------------


def public_plan(plan: MembershipPlan) -> dict[str, Any]:
    included = [
        _product_item(a.product)
        for a in plan.access
        if a.product.status == "published" and not eligibility_problem(a.product)
    ]
    return {
        "slug": plan.slug,
        "name": plan.name,
        "tagline": plan.tagline,
        "description": plan.description,
        "benefits": plan.benefits or [],
        "tier_rank": plan.tier_rank,
        "prices": [
            {"id": p.public_id, "interval": p.interval, "price": money(p.amount_minor, p.currency)}
            for p in sorted(plan.active_prices, key=lambda p: INTERVALS.index(p.interval))
        ],
        "included": [
            {k: v for k, v in item.items() if k not in ("status", "product_id")}
            for item in included
        ],
    }


def published_plans() -> dict[str, Any]:
    rows = db.session.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.status == "published")
        .order_by(MembershipPlan.tier_rank)
    )
    return {"plans": [public_plan(p) for p in rows], "billing": billing_status()}


def published_plan(slug: str) -> dict[str, Any]:
    plan = db.session.scalar(
        select(MembershipPlan).where(
            MembershipPlan.slug == slug, MembershipPlan.status == "published"
        )
    )
    if plan is None:
        raise NotFoundError("Membership plan not found.")
    return {"plan": public_plan(plan), "billing": billing_status()}
