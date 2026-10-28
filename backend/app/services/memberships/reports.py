"""Membership reports (Batch 10.4) from real records only.

- Subscribers: ``customer_subscriptions`` statuses. Paid subscribers are memberships that
  were activated by a verified payment (``active``/``past_due``/``grace``); complimentary
  memberships are counted separately and never as paid.
- Revenue: ``payment_transactions`` of kind ``charge`` (written only after Paystack
  verification) on subscription orders. Pending or unverified payments never count.
  Refunds: processed ``refund`` transactions on subscription orders. Amounts are grouped
  by mode and currency and never converted; test-mode money is labelled as such.
- Trends: churn = memberships ended in a month / memberships active at its start, shown
  only when at least one membership was active at the start of the month.

Not the Batch 11 analytics platform: no tracking, cohorts or forecasting.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...commerce.currency import money
from ...extensions import db
from ...models import (
    CourseEnrollment,
    CustomerSubscription,
    Entitlement,
    MembershipGrant,
    Order,
    PaymentTransaction,
    Product,
    SubscriptionPeriod,
    User,
)
from ...utils.errors import ForbiddenError, ValidationError
from ..commerce import entitlements as ent_service
from ..serializers import iso

PAID_LIVE = ("active", "past_due", "grace")
MAX_RANGE_DAYS = 731


def _now() -> datetime:
    return datetime.now(UTC)


def _day(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValidationError(details={field: ["Use YYYY-MM-DD."]}) from None


def _range(args: dict[str, Any]) -> tuple[datetime, datetime, date, date]:
    today = _now().date()
    end_day = _day(args.get("date_to"), "date_to") or today
    start_day = _day(args.get("date_from"), "date_from") or (end_day - timedelta(days=29))
    if start_day > end_day:
        raise ValidationError(details={"date_from": ["The start must be before the end."]})
    if (end_day - start_day).days > MAX_RANGE_DAYS:
        raise ValidationError(details={"date_from": ["Choose at most two years."]})
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=UTC) + timedelta(days=1)
    return start, end, start_day, end_day


def _count(stmt) -> int:
    return int(db.session.scalar(stmt) or 0)


def _money_rows(kind: str, status: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    when = func.coalesce(PaymentTransaction.occurred_at, PaymentTransaction.created_at)
    rows = db.session.execute(
        select(
            PaymentTransaction.mode,
            PaymentTransaction.currency,
            func.count(PaymentTransaction.id),
            func.coalesce(func.sum(PaymentTransaction.amount_minor), 0),
        )
        .join(Order, Order.id == PaymentTransaction.order_id)
        .where(
            Order.kind == "subscription",
            PaymentTransaction.kind == kind,
            PaymentTransaction.status == status,
            when >= start,
            when < end,
        )
        .group_by(PaymentTransaction.mode, PaymentTransaction.currency)
        .order_by(PaymentTransaction.mode, PaymentTransaction.currency)
    ).all()
    return [
        {"mode": mode, "count": int(n), "amount": money(int(total), currency)}
        for mode, currency, n, total in rows
    ]


def _net(revenue: list[dict], refunds: list[dict]) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str], int] = {}
    for row in revenue:
        key = (row["mode"], row["amount"]["currency"])
        totals[key] = totals.get(key, 0) + row["amount"]["amount_minor"]
    for row in refunds:
        key = (row["mode"], row["amount"]["currency"])
        totals[key] = totals.get(key, 0) - row["amount"]["amount_minor"]
    return [{"mode": m, "amount": money(v, c)} for (m, c), v in sorted(totals.items())]


def _renewals_between(start: datetime, end: datetime) -> int:
    return _count(
        select(func.count(SubscriptionPeriod.id))
        .join(Order, Order.id == SubscriptionPeriod.order_id)
        .where(
            SubscriptionPeriod.sequence > 1,
            SubscriptionPeriod.status.in_(("paid", "refunded")),
            Order.paid_at >= start,
            Order.paid_at < end,
        )
    )


def _months(start_day: date, end_day: date) -> list[tuple[datetime, datetime, str]]:
    out = []
    year, month = start_day.year, start_day.month
    while (year, month) <= (end_day.year, end_day.month) and len(out) < 25:
        first = datetime(year, month, 1, tzinfo=UTC)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        out.append((first, datetime(year, month, 1, tzinfo=UTC), first.strftime("%Y-%m")))
    return out


def _trend(start_day: date, end_day: date) -> list[dict[str, Any]]:
    rows = []
    activated = CustomerSubscription.activated_at
    for first, nxt, label in _months(start_day, end_day):
        active_start = _count(
            select(func.count(CustomerSubscription.id)).where(
                activated.is_not(None),
                activated < first,
                or_(
                    CustomerSubscription.ended_at.is_(None), CustomerSubscription.ended_at >= first
                ),
            )
        )
        ended = _count(
            select(func.count(CustomerSubscription.id)).where(
                activated.is_not(None),
                CustomerSubscription.ended_at >= first,
                CustomerSubscription.ended_at < nxt,
            )
        )
        rows.append(
            {
                "month": label,
                "active_at_start": active_start,
                "new": _count(
                    select(func.count(CustomerSubscription.id)).where(
                        activated >= first, activated < nxt
                    )
                ),
                "renewals": _renewals_between(first, nxt),
                "ended": ended,
                # Only meaningful with a base: None means "not enough data".
                "churn_rate": round(ended / active_start, 4) if active_start else None,
            }
        )
    return rows


def _access() -> dict[str, Any]:
    usable = and_(
        Entitlement.source == "membership",
        Entitlement.status == "active",
        ent_service.not_expired(),
    )
    by_kind = db.session.execute(
        select(Product.product_type, func.count(Entitlement.id))
        .join(Product, Product.id == Entitlement.product_id)
        .where(usable)
        .group_by(Product.product_type)
    ).all()
    complimentary = Entitlement.grant_key.like("membership:grant-%")
    return {
        "entitlements": _count(select(func.count(Entitlement.id)).where(usable)),
        "members_with_access": _count(
            select(func.count(func.distinct(Entitlement.customer_id))).where(usable)
        ),
        "complimentary_entitlements": _count(
            select(func.count(Entitlement.id)).where(usable, complimentary)
        ),
        "by_product_type": [
            {"type": t, "count": int(n)} for t, n in sorted(by_kind, key=lambda r: r[0] or "")
        ],
        "course_enrollments": _count(
            select(func.count(CourseEnrollment.id)).where(
                CourseEnrollment.source == "membership", CourseEnrollment.status == "active"
            )
        ),
    }


def report(args: dict[str, Any], actor: User) -> dict[str, Any]:
    if P.MEMBERSHIPS_VIEW_REPORTS.value not in effective_permissions(actor):
        raise ForbiddenError()
    start, end, start_day, end_day = _range(args)
    now = _now()
    sub = CustomerSubscription
    status_counts = dict(
        db.session.execute(select(sub.status, func.count(sub.id)).group_by(sub.status)).all()
    )
    paid_live = sub.status.in_(PAID_LIVE)
    by_interval = dict(
        db.session.execute(
            select(sub.interval, func.count(sub.id)).where(paid_live).group_by(sub.interval)
        ).all()
    )
    ended_rows = db.session.execute(
        select(sub.end_reason, func.count(sub.id))
        .where(sub.activated_at.is_not(None), sub.ended_at >= start, sub.ended_at < end)
        .group_by(sub.end_reason)
    ).all()
    revenue = _money_rows("charge", "success", start, end)
    refunds = _money_rows("refund", "processed", start, end)
    total_subscriptions = sum(status_counts.values())
    return {
        "range": {"from": start_day.isoformat(), "to": end_day.isoformat()},
        "generated_at": iso(now),
        "has_data": total_subscriptions > 0,
        "current": {
            "paid_subscribers": _count(select(func.count(sub.id)).where(paid_live)),
            "active": int(status_counts.get("active", 0)),
            "past_due": int(status_counts.get("past_due", 0)),
            "grace": int(status_counts.get("grace", 0)),
            "pending_checkout": int(status_counts.get("pending", 0)),
            "cancelling": _count(
                select(func.count(sub.id)).where(paid_live, sub.cancel_at_period_end.is_(True))
            ),
            "monthly": int(by_interval.get("month", 0)),
            "yearly": int(by_interval.get("year", 0)),
            "complimentary": _count(
                select(func.count(MembershipGrant.id)).where(
                    MembershipGrant.status == "active",
                    MembershipGrant.starts_at <= now,
                    MembershipGrant.expires_at > now,
                )
            ),
        },
        "period": {
            "new_subscriptions": _count(
                select(func.count(sub.id)).where(sub.activated_at >= start, sub.activated_at < end)
            ),
            "renewals": _renewals_between(start, end),
            "cancellations_requested": _count(
                select(func.count(sub.id)).where(
                    sub.cancel_requested_at >= start, sub.cancel_requested_at < end
                )
            ),
            "ended": {reason or "unknown": int(n) for reason, n in ended_rows},
            "abandoned_checkouts": _count(
                select(func.count(sub.id)).where(
                    sub.status == "incomplete", sub.created_at >= start, sub.created_at < end
                )
            ),
        },
        "revenue": revenue,
        "refunds": refunds,
        "net_revenue": _net(revenue, refunds),
        "trend": _trend(start_day, end_day),
        "access": _access(),
        "notes": [
            "Revenue counts only payments verified with Paystack; pending checkouts are excluded.",
            "Amounts are grouped by currency and mode and never converted.",
            "Test-mode amounts are Paystack test payments, not real money.",
        ],
    }
