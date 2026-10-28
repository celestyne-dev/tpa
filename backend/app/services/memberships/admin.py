"""Membership administration (Batch 10.4): subscribers, subscription detail, staff actions
and complimentary memberships.

Permissions (always checked here, not only in the API layer):

- read: ``memberships.manage_subscriptions``, or ``memberships.view`` together with
  ``customers.view`` (read-only roles see everything but cannot act);
- actions (reconcile, cancel, extend grace, complimentary grants):
  ``memberships.manage_subscriptions``.

There is deliberately no way to mark anything as paid: paid periods only come from
provider-verified payments (Batch 10.2/10.3). Refunds stay in the orders screen behind
``refunds.issue``. Every action is validated and audited, and actions on a subscription
require its ``lock_version`` so a double submit can never apply twice.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...commerce.currency import money
from ...extensions import db
from ...models import (
    Customer,
    CustomerSubscription,
    MembershipGrant,
    MembershipPlan,
    Order,
    Receipt,
    Refund,
    SubscriptionEvent,
    SubscriptionPeriod,
    User,
)
from ...models.memberships import SUBSCRIPTION_STATUSES
from ...payments.base import ProviderError
from ...payments.paystack import get_provider
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from . import billing, lifecycle

# Grace may be extended by staff, but never beyond this many days after the paid period.
MAX_GRACE_DAYS = 30
MAX_GRANT_DAYS = 366
_KEY = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _now() -> datetime:
    return datetime.now(UTC)


_aware = billing._aware


# ---- permissions --------------------------------------------------------------------------


def can_view(actor: User) -> bool:
    granted = effective_permissions(actor)
    return (
        P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS.value in granted
        or {
            P.MEMBERSHIPS_VIEW.value,
            P.CUSTOMERS_VIEW.value,
        }
        <= granted
    )


def can_manage(actor: User) -> bool:
    return P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS.value in effective_permissions(actor)


def require_view(actor: User) -> None:
    if not can_view(actor):
        raise ForbiddenError()


def require_manage(actor: User) -> None:
    if not can_manage(actor):
        raise ForbiddenError()


# ---- helpers ------------------------------------------------------------------------------


def _reason(data: dict[str, Any], field: str = "reason") -> str:
    value = data.get(field)
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= 500:
        raise ValidationError(details={field: ["Give a reason (3–500 characters)."]})
    problem = plain_text_problem(value)
    if problem:
        raise ValidationError(details={field: [problem]})
    return value.strip()


def _check_lock(sub: CustomerSubscription, data: dict[str, Any]) -> None:
    version = data.get("lock_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(details={"lock_version": ["Reload the page and try again."]})
    if version != sub.lock_version:
        raise ConflictError(
            "This membership changed since you opened it. Reload to see the latest state.",
            details={"code": "edit_conflict", "lock_version": sub.lock_version},
        )


def _body(data: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    unknown = set(data) - allowed
    if unknown:
        raise ValidationError(
            details={"_unknown": [f"Unknown field(s): {', '.join(sorted(unknown))}."]}
        )
    return data


def get_subscription(public_id: str) -> CustomerSubscription:
    sub = db.session.scalar(
        select(CustomerSubscription).where(CustomerSubscription.public_id == str(public_id)[:24])
    )
    if sub is None:
        raise NotFoundError("Subscription not found.")
    return sub


def _customer_dict(customer: Customer) -> dict[str, Any]:
    return {
        "id": customer.id,
        "public_id": customer.public_id,
        "email": customer.email,
        "name": customer.display_name,
        "status": customer.status,
        "test_account": customer.is_test_account,
    }


def upcoming(sub: CustomerSubscription) -> dict[str, Any] | None:
    """The next date that matters for this membership."""
    if sub.status == "active" and not sub.cancel_at_period_end:
        return {"type": "renewal", "at": iso(sub.current_period_end)}
    if sub.status == "active" and sub.cancel_at_period_end:
        return {"type": "cancellation", "at": iso(sub.access_until)}
    if sub.status in ("past_due", "grace"):
        return {"type": "expiry", "at": iso(sub.access_until)}
    return None


def summary(sub: CustomerSubscription) -> dict[str, Any]:
    customer = db.session.get(Customer, sub.customer_id)
    return {
        "id": sub.public_id,
        "status": sub.status,
        "test_mode": sub.mode == "test",
        "customer": _customer_dict(customer),
        "plan": {"id": sub.plan.public_id, "name": sub.plan.name},
        "interval": sub.interval,
        "price": money(sub.amount_minor, sub.currency),
        "current_period_end": iso(sub.current_period_end),
        "access_until": iso(sub.access_until),
        "cancel_at_period_end": sub.cancel_at_period_end,
        "past_due_since": iso(sub.past_due_since),
        "activated_at": iso(sub.activated_at),
        "ended_at": iso(sub.ended_at),
        "end_reason": sub.end_reason or None,
        "created_at": iso(sub.created_at),
        "next": upcoming(sub),
    }


# ---- list and detail ----------------------------------------------------------------------

FLAGS = ("payment_problem", "cancelling", "renewing_soon", "unlinked")


def list_subscriptions(args: dict[str, Any], actor: User) -> tuple[list[dict[str, Any]], int]:
    require_view(actor)
    stmt = select(CustomerSubscription).join(
        Customer, Customer.id == CustomerSubscription.customer_id
    )
    if q := (args.get("q") or "").strip().lower()[:100]:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                func.lower(Customer.email).like(like),
                func.lower(Customer.display_name).like(like),
                func.lower(CustomerSubscription.public_id).like(like),
                func.lower(CustomerSubscription.provider_subscription_code).like(like),
            )
        )
    status = args.get("status")
    if status:
        if status not in SUBSCRIPTION_STATUSES:
            raise ValidationError(details={"status": ["Unknown status."]})
        stmt = stmt.where(CustomerSubscription.status == status)
    if interval := args.get("interval"):
        if interval not in ("month", "year"):
            raise ValidationError(details={"interval": ["Use month or year."]})
        stmt = stmt.where(CustomerSubscription.interval == interval)
    if plan := args.get("plan"):
        stmt = stmt.join(MembershipPlan, MembershipPlan.id == CustomerSubscription.plan_id).where(
            MembershipPlan.public_id == plan
        )
    flag = args.get("flag")
    if flag:
        if flag not in FLAGS:
            raise ValidationError(details={"flag": [f"Use one of: {', '.join(FLAGS)}."]})
        if flag == "payment_problem":
            stmt = stmt.where(CustomerSubscription.status.in_(("past_due", "grace")))
        elif flag == "cancelling":
            stmt = stmt.where(
                CustomerSubscription.cancel_at_period_end.is_(True),
                CustomerSubscription.status.in_(lifecycle.RENEWABLE),
            )
        elif flag == "renewing_soon":
            stmt = stmt.where(
                CustomerSubscription.status == "active",
                CustomerSubscription.cancel_at_period_end.is_(False),
                CustomerSubscription.current_period_end <= _now() + timedelta(days=7),
            )
        else:
            stmt = stmt.where(
                CustomerSubscription.status.in_(lifecycle.RENEWABLE),
                CustomerSubscription.provider_subscription_code.is_(None),
            )
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(CustomerSubscription.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    # One query each for the page's customers and plans (summary() then finds them in the
    # session instead of loading one per row). Kept referenced until serialised.
    loaded = [
        db.session.scalars(
            select(Customer).where(Customer.id.in_({s.customer_id for s in rows}))
        ).all(),
        db.session.scalars(
            select(MembershipPlan).where(MembershipPlan.id.in_({s.plan_id for s in rows}))
        ).all(),
    ]
    items = [summary(s) for s in rows]
    del loaded
    return items, total


def _order_dict(order: Order) -> dict[str, Any]:
    receipt = db.session.scalar(select(Receipt).where(Receipt.order_id == order.id))
    refunds = db.session.scalars(
        select(Refund).where(Refund.order_id == order.id).order_by(Refund.created_at)
    ).all()
    return {
        "id": order.id,
        "number": order.number,
        "status": order.status,
        "total": money(order.total_minor, order.currency),
        "refunded": money(order.refunded_minor, order.currency),
        "paid_at": iso(order.paid_at),
        "needs_review": order.needs_review,
        "review_reason": order.review_reason or None,
        "receipt_number": receipt.number if receipt else None,
        "refunds": [
            {
                "id": r.id,
                "status": r.status,
                "amount": money(r.amount_minor, r.currency),
                "revoke_access": r.revoke_access,
                "created_at": iso(r.created_at),
                "processed_at": iso(r.processed_at),
            }
            for r in refunds
        ],
    }


def subscription_detail(sub: CustomerSubscription, actor: User) -> dict[str, Any]:
    require_view(actor)
    granted = effective_permissions(actor)
    periods = sorted(sub.periods, key=lambda p: p.sequence)
    order_ids = [p.order_id for p in periods if p.order_id]
    if sub.order_id and sub.order_id not in order_ids:
        order_ids.insert(0, sub.order_id)
    orders = {o.id: o for o in db.session.scalars(select(Order).where(Order.id.in_(order_ids)))}
    events = db.session.scalars(
        select(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == sub.id)
        .order_by(SubscriptionEvent.id)
    ).all()
    manage = P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS.value in granted
    return summary(sub) | {
        "lock_version": sub.lock_version,
        "provider": {
            "name": sub.provider,
            "mode": sub.mode,
            "linked": bool(sub.provider_subscription_code),
            "subscription_code": sub.provider_subscription_code,
            "customer_code": sub.provider_customer_code,
            # The email token is a credential for managing the subscription: never shown.
        },
        "current_period_start": iso(sub.current_period_start),
        "cancel_requested_at": iso(sub.cancel_requested_at),
        "last_reconciled_at": iso(sub.last_reconciled_at),
        "grace": {
            "days": lifecycle.grace_days(),
            "max_extension_until": iso(_max_grace(sub)),
        },
        "periods": [
            {
                "sequence": p.sequence,
                "status": p.status,
                "period_start": iso(p.period_start),
                "period_end": iso(p.period_end),
                "amount": money(p.amount_minor, p.currency),
                "order_number": orders[p.order_id].number if p.order_id in orders else None,
            }
            for p in reversed(periods)
        ],
        "orders": [_order_dict(orders[i]) for i in order_ids if i in orders],
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "source": e.source,
                "details": e.details or {},
                "created_at": iso(e.created_at),
            }
            for e in reversed(events)
        ],
        "grants": [grant_dict(g) for g in _customer_grants(sub.customer_id)],
        "can": {
            "manage": manage,
            "cancel": manage and sub.status in lifecycle.RENEWABLE,
            "extend_grace": manage and sub.status in ("past_due", "grace"),
            "reconcile": manage,
            "refund": P.REFUNDS_ISSUE.value in granted,
        },
    }


# ---- staff actions ------------------------------------------------------------------------


def reconcile_one(sub: CustomerSubscription, data: Any, actor: User) -> dict[str, Any]:
    """Re-check one membership with Paystack using the same rules as the scheduled job
    (it can shorten or end access, never extend it). A pending first payment is verified."""
    require_manage(actor)
    data = _body(data, {"lock_version"})
    _check_lock(sub, data)
    from ..commerce.payments import verify_order

    outcome: dict[str, Any] = {}
    if sub.status == "pending" and sub.order_id:
        outcome["payment"] = verify_order(db.session.get(Order, sub.order_id), "staff")
        db.session.refresh(sub)
    counts = {"grace": 0, "ended": 0, "cancelled_at_provider": 0, "provider_errors": 0}
    if sub.status in lifecycle.RENEWABLE:
        lifecycle._reconcile_one(sub, _now(), True, counts)
    outcome["changes"] = {k: v for k, v in counts.items() if v}
    if sub.provider_subscription_code:
        try:
            remote = get_provider(sub.provider).fetch_subscription(sub.provider_subscription_code)
            outcome["provider"] = {
                "status": remote.status,
                "next_payment_at": iso(remote.next_payment_at),
                "plan_matches": remote.plan_code == sub.provider_plan.plan_code,
                "mode": remote.mode,
            }
        except ProviderError as exc:
            outcome["provider"] = {"error": str(exc)[:200]}
    billing._event(
        sub, "reconciled_by_staff", "admin", details={"by": actor.id, **outcome.get("changes", {})}
    )
    audit_service.record(
        "membership.reconciled", "customer_subscription", sub.id, actor=actor, details=outcome
    )
    return outcome


def cancel(sub: CustomerSubscription, data: Any, actor: User) -> CustomerSubscription:
    """Staff cancellation through the customer's provider-safe path (Paystack first)."""
    require_manage(actor)
    data = _body(data, {"lock_version", "reason", "immediate"})
    _check_lock(sub, data)
    reason = _reason(data)
    immediate = data.get("immediate", False)
    if not isinstance(immediate, bool):
        raise ValidationError(details={"immediate": ["Must be true or false."]})
    sub = lifecycle.cancel_subscription(sub, "admin", immediate=immediate, reason=reason)
    billing._event(
        sub,
        "cancelled_by_staff",
        "admin",
        details={"by": actor.id, "reason": reason, "immediate": immediate},
    )
    audit_service.record(
        "membership.cancelled_by_staff",
        "customer_subscription",
        sub.id,
        actor=actor,
        details={"reason": reason, "immediate": immediate},
    )
    return sub


def _max_grace(sub: CustomerSubscription) -> datetime | None:
    end = _aware(sub.current_period_end)
    return end + timedelta(days=MAX_GRACE_DAYS) if end else None


def extend_grace(sub: CustomerSubscription, data: Any, actor: User) -> CustomerSubscription:
    """Give a member with a failed renewal more time to pay. Bounded: never more than
    MAX_GRACE_DAYS after the paid period, and only while past due or in grace."""
    require_manage(actor)
    data = _body(data, {"lock_version", "days", "reason"})
    _check_lock(sub, data)
    reason = _reason(data)
    days = data.get("days")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 14:
        raise ValidationError(details={"days": ["Choose 1 to 14 days."]})
    if sub.status not in ("past_due", "grace"):
        raise ConflictError(
            "Only memberships with a failed renewal can get more time.",
            details={"code": "not_past_due"},
        )
    sub = lifecycle._lock(sub)
    current = _aware(sub.access_until) or _now()
    limit = _max_grace(sub)
    until = min(current + timedelta(days=days), limit) if limit else current
    if until <= current:
        raise ConflictError(
            f"Grace can't be extended beyond {MAX_GRACE_DAYS} days after the paid period.",
            details={"code": "grace_limit"},
        )
    sub.access_until = until
    sub.lock_version += 1
    lifecycle._set_entitlement_expiry(sub, until)
    billing._event(
        sub,
        "grace_extended",
        "admin",
        details={"by": actor.id, "reason": reason, "from": iso(current), "to": iso(until)},
    )
    audit_service.record(
        "membership.grace_extended",
        "customer_subscription",
        sub.id,
        actor=actor,
        details={"reason": reason, "from": iso(current), "to": iso(until)},
    )
    return sub


# ---- complimentary memberships ------------------------------------------------------------


def _grant_reference(grant: MembershipGrant) -> str:
    return f"grant-{grant.id}"


def grant_status(grant: MembershipGrant) -> str:
    if grant.status == "revoked":
        return "revoked"
    now = _now()
    return "expired" if _aware(grant.expires_at) <= now else "active"


def grant_dict(grant: MembershipGrant) -> dict[str, Any]:
    customer = db.session.get(Customer, grant.customer_id)
    granted_by = db.session.get(User, grant.granted_by_id) if grant.granted_by_id else None
    revoked_by = db.session.get(User, grant.revoked_by_id) if grant.revoked_by_id else None
    return {
        "id": grant.public_id,
        "status": grant_status(grant),
        "customer": _customer_dict(customer),
        "plan": {"id": grant.plan.public_id, "name": grant.plan.name},
        "starts_at": iso(grant.starts_at),
        "expires_at": iso(grant.expires_at),
        "reason": grant.reason,
        "granted_by": granted_by.display_name if granted_by else None,
        "created_at": iso(grant.created_at),
        "revoked_at": iso(grant.revoked_at),
        "revoked_by": revoked_by.display_name if revoked_by else None,
        "revoke_reason": grant.revoke_reason or None,
    }


def _customer_grants(customer_id: int) -> list[MembershipGrant]:
    return list(
        db.session.scalars(
            select(MembershipGrant)
            .where(MembershipGrant.customer_id == customer_id)
            .order_by(MembershipGrant.id.desc())
        )
    )


def list_grants(args: dict[str, Any], actor: User) -> tuple[list[dict[str, Any]], int]:
    require_view(actor)
    stmt = select(MembershipGrant).join(Customer, Customer.id == MembershipGrant.customer_id)
    if q := (args.get("q") or "").strip().lower()[:100]:
        stmt = stmt.where(
            or_(
                func.lower(Customer.email).like(f"%{q}%"),
                func.lower(Customer.display_name).like(f"%{q}%"),
            )
        )
    state = args.get("status")
    now = _now()
    if state == "active":
        stmt = stmt.where(
            MembershipGrant.status == "active",
            MembershipGrant.starts_at <= now,
            MembershipGrant.expires_at > now,
        )
    elif state == "expired":
        stmt = stmt.where(MembershipGrant.status == "active", MembershipGrant.expires_at <= now)
    elif state == "revoked":
        stmt = stmt.where(MembershipGrant.status == "revoked")
    elif state:
        raise ValidationError(details={"status": ["Use active, expired or revoked."]})
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(MembershipGrant.id.desc()).offset((page - 1) * size).limit(size)
    )
    return [grant_dict(g) for g in rows], total


def _parse_when(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(details={field: ["Use a date such as 2026-12-31."]})
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(details={field: ["Use a date such as 2026-12-31."]}) from None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def create_grant(data: Any, actor: User) -> MembershipGrant:
    """Complimentary access to a published plan's included products, with an expiry."""
    from ..courses.learning import sync

    require_manage(actor)
    data = _body(data, {"customer_id", "plan_id", "expires_at", "reason", "idempotency_key"})
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not _KEY.match(key):
        raise ValidationError(
            details={"idempotency_key": ["Missing request key; reload the page."]}
        )
    customer = db.session.scalar(
        select(Customer).where(Customer.public_id == str(data.get("customer_id") or "")[:40])
    )
    if customer is None or customer.status != "active":
        raise ValidationError(details={"customer_id": ["Choose an active customer account."]})
    existing = db.session.scalar(
        select(MembershipGrant).where(
            MembershipGrant.customer_id == customer.id, MembershipGrant.idempotency_key == key
        )
    )
    if existing is not None:
        return existing  # the same request repeated
    plan = db.session.scalar(
        select(MembershipPlan).where(
            MembershipPlan.public_id == str(data.get("plan_id") or "")[:40]
        )
    )
    if plan is None or plan.status != "published":
        raise ValidationError(details={"plan_id": ["Choose a published plan."]})
    reason = _reason(data)
    now = _now()
    # Access starts now (entitlements are granted at once); only the expiry is chosen.
    starts = now
    expires = _parse_when(data.get("expires_at"), "expires_at")
    if expires <= now:
        raise ValidationError(details={"expires_at": ["Choose an expiry date in the future."]})
    if expires - starts > timedelta(days=MAX_GRANT_DAYS):
        raise ValidationError(details={"expires_at": [f"At most {MAX_GRANT_DAYS} days."]})
    overlapping = db.session.scalar(
        select(MembershipGrant.id).where(
            MembershipGrant.customer_id == customer.id,
            MembershipGrant.plan_id == plan.id,
            MembershipGrant.status == "active",
            MembershipGrant.expires_at > now,
        )
    )
    if overlapping:
        raise ConflictError(
            "This customer already has complimentary access to this plan. Revoke it first.",
            details={"code": "grant_exists"},
        )
    grant = MembershipGrant(
        public_id=secrets.token_urlsafe(12),
        customer_id=customer.id,
        plan_id=plan.id,
        status="active",
        starts_at=starts,
        expires_at=expires,
        reason=reason,
        idempotency_key=key,
        granted_by_id=actor.id,
        revoke_reason="",
    )
    db.session.add(grant)
    db.session.flush()
    granted = _grant_products(grant, customer, plan)
    sync(customer)
    audit_service.record(
        "membership.complimentary_granted",
        "membership_grant",
        grant.id,
        actor=actor,
        details={
            "customer_id": customer.id,
            "plan_id": plan.id,
            "expires_at": iso(expires),
            "reason": reason,
            "entitlements": granted,
        },
    )
    return grant


def _grant_products(grant: MembershipGrant, customer: Customer, plan: MembershipPlan) -> int:
    from ..commerce import access
    from .plans import eligibility_problem

    count = 0
    for item in plan.access:
        product = item.product
        if product.status != "published" or eligibility_problem(product):
            continue
        access.grant(
            customer,
            product,
            source="membership",
            reference=_grant_reference(grant),
            expires_at=grant.expires_at,
            reason=f"Complimentary {plan.name}"[:300],
        )
        count += 1
    return count


def get_grant(public_id: str) -> MembershipGrant:
    grant = db.session.scalar(
        select(MembershipGrant).where(MembershipGrant.public_id == str(public_id)[:24])
    )
    if grant is None:
        raise NotFoundError("Complimentary membership not found.")
    return grant


def revoke_grant(grant: MembershipGrant, data: Any, actor: User) -> MembershipGrant:
    from ..commerce import access

    require_manage(actor)
    data = _body(data, {"reason"})
    reason = _reason(data)
    if grant.status == "revoked":
        return grant  # idempotent
    grant.status = "revoked"
    grant.revoked_at = _now()
    grant.revoked_by_id = actor.id
    grant.revoke_reason = reason
    revoked = access.revoke(
        "membership", _grant_reference(grant), f"Complimentary access revoked: {reason}"[:300]
    )
    audit_service.record(
        "membership.complimentary_revoked",
        "membership_grant",
        grant.id,
        actor=actor,
        details={"reason": reason, "entitlements": revoked},
    )
    return grant


def customer_grants_view(customer: Customer) -> list[dict[str, Any]]:
    """What the member sees about their complimentary access (no staff names or notes)."""
    return [
        {
            "plan": g.plan.name,
            "status": grant_status(g),
            "starts_at": iso(g.starts_at),
            "expires_at": iso(g.expires_at),
        }
        for g in _customer_grants(customer.id)
    ]


def overview(actor: User) -> dict[str, Any]:
    """Billing configuration and availability for the CMS (no secrets)."""
    if not (can_view(actor) or P.MEMBERSHIPS_VIEW.value in effective_permissions(actor)):
        raise ForbiddenError()
    from flask import current_app

    return {
        "billing": billing.billing_status(),
        "billing_mode": current_app.config.get("MEMBERSHIP_BILLING_MODE"),
        "grace_days": lifecycle.grace_days(),
        "max_grace_extension_days": MAX_GRACE_DAYS,
        "live_billing": False,
        "provider_mode": get_provider().mode,
        "counts": {
            status: db.session.scalar(
                select(func.count(CustomerSubscription.id)).where(
                    CustomerSubscription.status == status
                )
            )
            or 0
            for status in ("active", "past_due", "grace", "pending")
        },
        "period_count": db.session.scalar(select(func.count(SubscriptionPeriod.id))) or 0,
    }
