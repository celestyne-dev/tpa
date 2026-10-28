"""Membership data in account export and deletion (Batch 10.4).

Deletion (customer self-service or staff anonymisation) first makes sure nobody is
charged afterwards:

1. A live, Paystack-linked membership is disabled at Paystack *before* anything changes
   locally. If Paystack can't confirm, deletion is refused and nothing is changed.
2. A live membership that isn't linked to Paystack yet blocks deletion (we couldn't stop
   its renewals); the customer is asked to try again shortly.
3. Then the membership ends (``account_deleted``, membership entitlements revoked),
   complimentary memberships are revoked, and the Paystack email token (a management
   credential) is erased.

Retained for legal/accounting duties: subscriptions, billing periods, amounts, orders,
receipts, refunds and the event history (no personal data is stored in them; the
customer row itself is anonymised by ``customers.anonymise``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ...extensions import db
from ...models import Customer, CustomerSubscription, MembershipGrant, SubscriptionEvent
from ...payments.base import ProviderError
from ...payments.paystack import get_provider
from ...utils.errors import ConflictError
from .. import audit_service
from ..serializers import iso
from . import admin, billing, lifecycle


def _now() -> datetime:
    return datetime.now(UTC)


def _subscriptions(customer: Customer) -> list[CustomerSubscription]:
    return list(
        db.session.scalars(
            select(CustomerSubscription)
            .where(CustomerSubscription.customer_id == customer.id)
            .order_by(CustomerSubscription.id)
        )
    )


def prepare_deletion(customer: Customer, actor=None) -> dict[str, int]:
    """Stop billing and end membership access before an account is anonymised. Raises
    (with nothing changed) when billing cannot safely be stopped."""
    subs = _subscriptions(customer)
    live = [s for s in subs if s.status in lifecycle.RENEWABLE]
    for sub in live:
        if sub.cancel_at_period_end:
            continue  # Paystack already confirmed the cancellation
        if not (sub.provider_subscription_code and sub.provider_email_token):
            raise ConflictError(
                "Your membership is still being set up with our payment provider, so we "
                "can't stop its renewals yet. Please try again in a few minutes.",
                details={"code": "membership_not_linked"},
            )
    for sub in live:
        if sub.cancel_at_period_end:
            continue
        try:
            get_provider(sub.provider).disable_subscription(
                sub.provider_subscription_code, sub.provider_email_token
            )
        except ProviderError:
            raise ConflictError(
                "We couldn't confirm the membership cancellation with our payment provider, "
                "so your account was not deleted. Please try again shortly.",
                details={"code": "membership_cancellation_failed"},
            ) from None
    ended = 0
    for sub in subs:
        if sub.status in lifecycle.RENEWABLE:
            sub = lifecycle._lock(sub)
            lifecycle._end(sub, "account_deleted", "admin" if actor else "customer", notify=False)
            ended += 1
        elif sub.status == "pending":
            billing._set_status(sub, "incomplete", "account_deleted", "customer")
        sub.provider_email_token = None
    revoked = 0
    for grant in db.session.scalars(
        select(MembershipGrant).where(
            MembershipGrant.customer_id == customer.id, MembershipGrant.status == "active"
        )
    ):
        grant.status = "revoked"
        grant.revoked_at = _now()
        grant.revoked_by_id = actor.id if actor else None
        grant.revoke_reason = "Account deleted"
        revoked += 1
    if subs or revoked:
        audit_service.record(
            "membership.account_deleted",
            "customer",
            customer.id,
            actor=actor,
            details={"memberships_ended": ended, "complimentary_revoked": revoked},
        )
    return {"ended": ended, "complimentary_revoked": revoked}


def export(customer: Customer) -> dict[str, Any]:
    """The customer's membership records for a data-portability export."""
    subs = _subscriptions(customer)
    out = []
    for sub in subs:
        events = db.session.scalars(
            select(SubscriptionEvent)
            .where(SubscriptionEvent.subscription_id == sub.id)
            .order_by(SubscriptionEvent.id)
        ).all()
        out.append(
            {
                "id": sub.public_id,
                "plan": sub.plan.name,
                "status": sub.status,
                "interval": sub.interval,
                "currency": sub.currency,
                "amount_minor": sub.amount_minor,
                "mode": sub.mode,
                "created_at": iso(sub.created_at),
                "activated_at": iso(sub.activated_at),
                "current_period_start": iso(sub.current_period_start),
                "current_period_end": iso(sub.current_period_end),
                "access_until": iso(sub.access_until),
                "cancel_at_period_end": sub.cancel_at_period_end,
                "cancel_requested_at": iso(sub.cancel_requested_at),
                "ended_at": iso(sub.ended_at),
                "end_reason": sub.end_reason or None,
                "paystack_subscription_code": sub.provider_subscription_code,
                "billing_periods": [
                    {
                        "sequence": p.sequence,
                        "status": p.status,
                        "period_start": iso(p.period_start),
                        "period_end": iso(p.period_end),
                        "amount_minor": p.amount_minor,
                        "currency": p.currency,
                    }
                    for p in sorted(sub.periods, key=lambda p: p.sequence)
                ],
                "history": [{"type": e.type, "at": iso(e.created_at)} for e in events],
            }
        )
    return {"subscriptions": out, "complimentary": admin.customer_grants_view(customer)}
