"""Membership analytics (Batch 11.4).

Builds on the Batch 10.4 membership report (``memberships.reports.report``: subscriber
counts, new subscriptions, renewals, cancellations, endings, churn trend, verified
revenue and refunds by mode and currency, membership access) and adds:

- active paid memberships by plan and billing interval;
- realised revenue and refunds by plan (verified payment transactions joined through
  billing periods, so each payment is attributed to the plan it paid for);
- recurring-revenue *estimates*: MRR = sum over ``active`` subscriptions that are not
  cancelling of the price agreed at checkout, normalised to a month (yearly ÷ 12);
  ARR = MRR × 12. Shown per mode and currency, never converted or mixed with realised
  revenue. Past-due, grace and cancelling memberships are listed separately as
  "at risk" rather than included.

Complimentary memberships are never counted as paid or as revenue. No lifecycle or
payment logic lives here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from ...commerce.currency import money
from ...extensions import db
from ...models import (
    CustomerSubscription,
    MembershipGrant,
    MembershipPlan,
    Order,
    PaymentTransaction,
    SubscriptionPeriod,
    User,
)
from ...utils.errors import NotFoundError
from ..memberships import reports as membership_reports

S = CustomerSubscription
PAID_LIVE = membership_reports.PAID_LIVE


def _plan(args: dict[str, Any]) -> MembershipPlan | None:
    if not args.get("plan"):
        return None
    plan = db.session.scalar(
        select(MembershipPlan).where(MembershipPlan.public_id == str(args["plan"])[:40])
    )
    if plan is None:
        raise NotFoundError("Membership plan not found.")
    return plan


def membership_analytics(args: dict[str, Any], actor: User) -> dict[str, Any]:
    if args.get("range") and not (args.get("date_from") or args.get("date_to")):
        from .reports import resolve_range

        first, last, _g = resolve_range({"range": args["range"]})
        args = {**args, "date_from": first.isoformat(), "date_to": last.isoformat()}
    base = membership_reports.report(args, actor)  # permission + range validation
    plan = _plan(args)
    start, end, _sd, _ed = membership_reports._range(args)
    scope = [S.plan_id == plan.id] if plan else []

    by_plan = db.session.execute(
        select(MembershipPlan.public_id, MembershipPlan.name, S.interval, S.mode, func.count(S.id))
        .join(MembershipPlan, MembershipPlan.id == S.plan_id)
        .where(S.status.in_(PAID_LIVE), *scope)
        .group_by(MembershipPlan.public_id, MembershipPlan.name, S.interval, S.mode)
        .order_by(MembershipPlan.name, S.interval)
    ).all()

    recurring: dict[tuple[str, str], int] = defaultdict(int)
    counted: dict[tuple[str, str], int] = defaultdict(int)
    at_risk: dict[tuple[str, str], int] = defaultdict(int)
    for status, cancelling, interval, mode, currency, amount in db.session.execute(
        select(
            S.status, S.cancel_at_period_end, S.interval, S.mode, S.currency, S.amount_minor
        ).where(S.status.in_(PAID_LIVE), *scope)
    ):
        monthly = amount if interval == "month" else amount / 12
        if status == "active" and not cancelling:
            recurring[(mode, currency)] += monthly
            counted[(mode, currency)] += 1
        else:
            at_risk[(mode, currency)] += monthly

    when = func.coalesce(PaymentTransaction.occurred_at, PaymentTransaction.created_at)
    plan_money = db.session.execute(
        select(
            MembershipPlan.name,
            PaymentTransaction.kind,
            PaymentTransaction.mode,
            PaymentTransaction.currency,
            func.count(PaymentTransaction.id),
            func.coalesce(func.sum(PaymentTransaction.amount_minor), 0),
        )
        .join(Order, Order.id == PaymentTransaction.order_id)
        .join(SubscriptionPeriod, SubscriptionPeriod.order_id == Order.id)
        .join(S, S.id == SubscriptionPeriod.subscription_id)
        .join(MembershipPlan, MembershipPlan.id == S.plan_id)
        .where(
            Order.kind == "subscription",
            ((PaymentTransaction.kind == "charge") & (PaymentTransaction.status == "success"))
            | ((PaymentTransaction.kind == "refund") & (PaymentTransaction.status == "processed")),
            when >= start,
            when < end,
            *scope,
        )
        .group_by(
            MembershipPlan.name,
            PaymentTransaction.kind,
            PaymentTransaction.mode,
            PaymentTransaction.currency,
        )
    ).all()
    revenue_by_plan: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"charges": 0, "gross": 0, "refunds": 0}
    )
    for name, kind, mode, currency, n, total in plan_money:
        row = revenue_by_plan[(name, mode, currency)]
        if kind == "charge":
            row["charges"] += int(n)
            row["gross"] += int(total)
        else:
            row["refunds"] += int(total)

    complimentary_by_plan = db.session.execute(
        select(MembershipPlan.name, func.count(MembershipGrant.id))
        .join(MembershipPlan, MembershipPlan.id == MembershipGrant.plan_id)
        .where(
            MembershipGrant.status == "active",
            MembershipGrant.starts_at <= membership_reports._now(),
            MembershipGrant.expires_at > membership_reports._now(),
            *([MembershipGrant.plan_id == plan.id] if plan else []),
        )
        .group_by(MembershipPlan.name)
    ).all()

    return base | {
        "plan": {"id": plan.public_id, "name": plan.name} if plan else None,
        "plan_options": [
            {"id": p.public_id, "name": p.name, "status": p.status}
            for p in db.session.scalars(
                select(MembershipPlan)
                .where(MembershipPlan.status != "draft")
                .order_by(MembershipPlan.name)
            )
        ],
        "by_plan": [
            {
                "plan_id": pid,
                "plan": name,
                "interval": interval,
                "mode": mode,
                "paid_members": int(n),
            }
            for pid, name, interval, mode, n in by_plan
        ],
        "revenue_by_plan": [
            {
                "plan": name,
                "mode": mode,
                "payments": v["charges"],
                "gross": money(v["gross"], currency),
                "refunds": money(v["refunds"], currency),
                "net": money(v["gross"] - v["refunds"], currency),
            }
            for (name, mode, currency), v in sorted(revenue_by_plan.items())
        ],
        "recurring_estimate": [
            {
                "mode": mode,
                "subscriptions": counted[(mode, currency)],
                "mrr": money(round(total), currency),
                "arr": money(round(total * 12), currency),
            }
            for (mode, currency), total in sorted(recurring.items())
        ],
        "recurring_at_risk": [
            {"mode": mode, "monthly": money(round(total), currency)}
            for (mode, currency), total in sorted(at_risk.items())
        ],
        "complimentary_by_plan": [
            {"plan": name, "members": int(n)} for name, n in complimentary_by_plan
        ],
        "definitions": {
            "paid_members": "Memberships activated by a verified payment and still active, past "
            "due or in grace. Complimentary memberships are counted separately.",
            "realised_revenue": "Verified Paystack charges on membership orders in the range "
            "(refunds: processed refunds). Grouped by mode and currency, never converted.",
            "mrr": "Estimate, not revenue: active, non-cancelling subscriptions at the price "
            "agreed at checkout, yearly prices divided by 12. ARR = MRR × 12.",
            "at_risk": "Monthly value of past-due, grace or cancelling memberships, excluded "
            "from MRR.",
            "churn": "Memberships ended in a month ÷ memberships active at its start (shown "
            "only when there was at least one).",
            "plan_filter": "The plan filter applies to plan, recurring, revenue-by-plan and "
            "complimentary tables; the overview figures cover all plans.",
            "test_mode": "Test-mode payments are Paystack test transactions, not real money.",
        },
    }
