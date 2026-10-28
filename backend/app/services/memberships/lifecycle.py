"""Membership subscription lifecycle (Batch 10.3): renewals, failed payments, grace,
cancellation at the end of the paid period, resumption, payment-method links,
reconciliation, and refund/dispute hooks.

Rules that keep access honest:

- Access is only extended by a charge the server itself verified with Paystack
  (``GET /transaction/verify``). A renewal goes through the same commerce path as every
  other payment: a renewal ``Order`` + ``PaymentAttempt`` are created for the verified
  transaction and handed to ``payments.apply_verified`` (amount, currency, mode, plan
  and customer checks, receipts, emails). Webhook bodies are only hints.
- Duplicates: a renewal order is keyed by the provider transaction id (unique order
  idempotency key), payment transactions are unique per provider id, billing periods are
  unique per (subscription, sequence) and per order, and entitlements per grant key.
- Grace is measured from the end of the *paid* period (never from "now"), so retries,
  replays or a failing reconciliation can never stretch unpaid access.
- Membership entitlements carry ``expires_at`` = the subscription's ``access_until``; they
  stop working on time even if no job runs, and are revoked when the membership ends.
- Cancellation stops future charges at Paystack first, then keeps access until the end of
  the period already paid for.

Unknown webhook events are never treated as payments.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...commerce.currency import money
from ...extensions import db
from ...models import (
    Customer,
    CustomerSubscription,
    Entitlement,
    MembershipProviderPlan,
    Order,
    OrderItem,
    PaymentAttempt,
    PaymentEvent,
    PaymentTransaction,
    Product,
    Refund,
    SubscriptionPeriod,
    User,
)
from ...payments.base import ProviderError, VerifiedTransaction
from ...payments.paystack import get_provider
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..commerce import emails
from ..serializers import iso
from . import billing

RENEWABLE = ("active", "past_due", "grace")
# Paystack subscription statuses meaning "no further charges will be attempted".
NOT_RENEWING = {"non-renewing", "cancelled", "complete", "completed", "disabled"}
# Webhook events that may only be processed once the matching membership exists.
MEMBERSHIP_EVENTS = (
    "charge.success",
    "invoice.update",
    "invoice.payment_failed",
    "subscription.not_renew",
    "subscription.disable",
)


class ProviderActionFailed(APIError):
    status_code = 502
    code = "provider_unavailable"
    message = "We couldn't reach Paystack. Nothing was changed; please try again shortly."


def _now() -> datetime:
    return datetime.now(UTC)


_aware = billing._aware


def grace_days() -> int:
    return int(current_app.config.get("MEMBERSHIP_GRACE_DAYS", 3))


def _lock(sub: CustomerSubscription) -> CustomerSubscription:
    """Re-read the subscription with a row lock (PostgreSQL; SQLite serialises writers)."""
    return db.session.scalars(
        select(CustomerSubscription)
        .where(CustomerSubscription.id == sub.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _customer(sub: CustomerSubscription) -> Customer:
    return db.session.get(Customer, sub.customer_id)


def _reference(sub: CustomerSubscription) -> str:
    return f"subscription-{sub.id}"


def _entitlements(sub: CustomerSubscription) -> list[Entitlement]:
    prefix = f"membership:{_reference(sub)}:product:"
    return list(
        db.session.scalars(
            select(Entitlement).where(
                Entitlement.grant_key.startswith(prefix), Entitlement.status == "active"
            )
        )
    )


def _set_entitlement_expiry(sub: CustomerSubscription, until: datetime) -> None:
    """Align membership entitlements with ``access_until`` (both directions)."""
    for ent in _entitlements(sub):
        ent.expires_at = until


def _fmt(value: datetime | None) -> str:
    return _aware(value).strftime("%d %B %Y") if value else ""


def _notify(sub: CustomerSubscription, template: str, **context: Any) -> None:
    customer = _customer(sub)
    emails.send(
        template,
        customer.email,
        {
            "name": customer.display_name,
            "plan_name": sub.plan.name,
            "test": sub.mode == "test",
            **context,
        },
        customer=customer,
    )


def _end(sub: CustomerSubscription, reason: str, source: str, *, notify: bool = True) -> None:
    """End the membership now: membership entitlements are revoked (purchases are not)."""
    from ..commerce import access

    now = _now()
    sub.ended_at = now
    sub.end_reason = reason
    sub.access_until = min(_aware(sub.access_until) or now, now)
    billing._set_status(sub, "ended", "ended", source, reason=reason)
    revoked = access.revoke("membership", _reference(sub), f"Membership ended ({reason})")
    audit_service.record(
        "membership.ended",
        "customer_subscription",
        sub.id,
        details={"reason": reason, "revoked": revoked, "via": source},
    )
    if notify:
        _notify(sub, "membership_ended", reason=reason)


def _stop_provider_charges(sub: CustomerSubscription) -> bool:
    """Best effort for memberships ended here (non-payment, refund): Paystack must not keep
    charging. Returns False when it could not be confirmed (flagged in the history)."""
    if not (sub.provider_subscription_code and sub.provider_email_token):
        billing._event(sub, "provider_disable_needed", "system", details={"why": "not linked"})
        return False
    try:
        get_provider(sub.provider).disable_subscription(
            sub.provider_subscription_code, sub.provider_email_token
        )
    except ProviderError as exc:
        current_app.logger.warning("Could not disable %s: %s", sub.public_id, exc)
        billing._event(sub, "provider_disable_needed", "system", details={"why": str(exc)[:200]})
        return False
    return True


# ---- renewals -----------------------------------------------------------------------------


def _live_for(pp: MembershipProviderPlan, customer_code: str) -> CustomerSubscription | None:
    if not customer_code:
        return None
    return db.session.scalar(
        select(CustomerSubscription)
        .where(
            CustomerSubscription.provider_plan_id == pp.id,
            CustomerSubscription.provider_customer_code == customer_code,
            CustomerSubscription.status.in_(("pending", *RENEWABLE)),
        )
        .order_by(CustomerSubscription.id.desc())
    )


def process_unmatched_charge(record: PaymentEvent) -> tuple[str, str]:
    """A successful charge (or paid invoice) whose reference is not one of our checkout
    attempts: possibly a membership renewal. Verified with Paystack before anything else."""
    payload = record.payload or {}
    if not record.reference or not (payload.get("plan_code") or payload.get("subscription_code")):
        return "ignored", "No order uses this payment reference."
    tx = get_provider().verify(record.reference)
    if tx.status != "success":
        return "processed", f"Payment status: {tx.status}."
    pp = db.session.scalar(
        select(MembershipProviderPlan).where(
            MembershipProviderPlan.provider == "paystack",
            MembershipProviderPlan.plan_code == tx.plan_code,
        )
    )
    if pp is None:
        return "ignored", "Not a membership plan of this site."
    sub = _live_for(pp, tx.customer_code)
    if sub is None and tx.customer_code:
        # Charged after the membership ended here: recorded as a paid order flagged for a
        # refund (apply_renewal never reactivates an ended membership).
        sub = db.session.scalar(
            select(CustomerSubscription)
            .where(
                CustomerSubscription.provider_plan_id == pp.id,
                CustomerSubscription.provider_customer_code == tx.customer_code,
                CustomerSubscription.status == "ended",
            )
            .order_by(CustomerSubscription.id.desc())
        )
    if sub is None and payload.get("subscription_code"):
        sub = db.session.scalar(
            select(CustomerSubscription).where(
                CustomerSubscription.provider_subscription_code == payload["subscription_code"]
            )
        )
    if sub is None:
        audit_service.record(
            "membership.unmatched_renewal",
            "payments",
            details={"reference": tx.reference, "plan": tx.plan_code},
        )
        return "rejected", "Verified membership charge with no matching membership (review)."
    if sub.status == "pending":
        # The first payment isn't confirmed yet (out of order): try again later.
        return "deferred", "The first membership payment has not been confirmed yet."
    return renew(sub, tx, record)


def renew(
    sub: CustomerSubscription, tx: VerifiedTransaction, record: PaymentEvent | None = None
) -> tuple[str, str]:
    """Record a verified renewal charge as its own order and billing period, then run it
    through the shared fulfilment path (``apply_verified`` -> ``apply_renewal``)."""
    from ..commerce.checkout import _new_number
    from ..commerce.payments import apply_verified

    if not tx.provider_id:
        return "rejected", "Verified charge without a provider id."
    seen = db.session.scalar(
        select(PaymentTransaction.order_id).where(
            PaymentTransaction.provider == sub.provider,
            PaymentTransaction.kind == "charge",
            PaymentTransaction.provider_id == tx.provider_id,
        )
    )
    if seen is not None:
        return "processed", "Renewal already recorded."
    existing_attempt = db.session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.reference == tx.reference)
    )
    if existing_attempt is not None:  # created by a concurrent delivery; finish it
        order = db.session.get(Order, existing_attempt.order_id)
        outcome = apply_verified(order, existing_attempt, tx, "webhook")
        return _renewal_result(order, outcome)

    first = db.session.get(Order, sub.order_id) if sub.order_id else None
    product_id = sub.plan.product_id
    sequence = (
        db.session.scalar(
            select(func.max(SubscriptionPeriod.sequence)).where(
                SubscriptionPeriod.subscription_id == sub.id
            )
        )
        or 0
    ) + 1
    label = (
        f"{sub.plan.name} membership renewal ({'monthly' if sub.interval == 'month' else 'yearly'})"
    )
    order = Order(
        number=_new_number(),
        public_id=secrets.token_hex(16),
        customer_id=sub.customer_id,
        email=_customer(sub).email,
        status="awaiting_payment",
        kind="subscription",
        currency=sub.currency,
        subtotal_minor=sub.amount_minor,
        tax_minor=0,
        discount_minor=0,
        # The amount agreed at checkout: apply_verified rejects any other charged amount.
        total_minor=sub.amount_minor,
        provider=sub.provider,
        mode=sub.mode,
        idempotency_key=f"renewal-{tx.provider_id}"[:64],
        terms_version=first.terms_version if first else "",
        terms_accepted_at=first.terms_accepted_at if first else None,
    )
    if product_id is not None:
        product = db.session.get(Product, product_id)
        order.items.append(
            OrderItem(
                product_id=product_id,
                product_public_id=product.public_id,
                title=label[:200],
                product_type="membership",
                slug=product.slug,
                currency=sub.currency,
                unit_amount_minor=sub.amount_minor,
                quantity=1,
                line_total_minor=sub.amount_minor,
            )
        )
    try:
        with db.session.begin_nested():
            db.session.add(order)
            db.session.flush()
            attempt = PaymentAttempt(
                order_id=order.id,
                provider=sub.provider,
                mode=sub.mode,
                reference=tx.reference[:100],
                status="initialized",
                amount_minor=sub.amount_minor,
                currency=sub.currency,
            )
            db.session.add(attempt)
            db.session.add(
                SubscriptionPeriod(
                    subscription_id=sub.id,
                    sequence=sequence,
                    status="pending",
                    order_id=order.id,
                    amount_minor=sub.amount_minor,
                    currency=sub.currency,
                    provider_invoice_code=((record.payload or {}).get("invoice_code") or None)
                    if record is not None
                    else None,
                )
            )
            db.session.flush()
    except IntegrityError:
        # Same charge delivered concurrently (order key / reference / period unique).
        db.session.rollback()
        return "processed", "Renewal already being recorded."
    db.session.commit()
    outcome = apply_verified(order, attempt, tx, "webhook")
    return _renewal_result(order, outcome)


def _renewal_result(order: Order, outcome: str) -> tuple[str, str]:
    if outcome == "mismatch":
        return "rejected", "Verified renewal did not match the membership (flagged for review)."
    return "processed", f"Renewal order {order.number}: {outcome.replace('_', ' ')}."


def period_for_order(order: Order) -> SubscriptionPeriod | None:
    return db.session.scalar(
        select(SubscriptionPeriod).where(SubscriptionPeriod.order_id == order.id)
    )


def renewal_problems(sub: CustomerSubscription, tx: VerifiedTransaction) -> list[str]:
    """Extra checks for a renewal charge: same Paystack customer as the membership."""
    if sub.provider_customer_code and tx.customer_code != sub.provider_customer_code:
        return [f"customer {tx.customer_code or 'none'} does not match the membership"]
    return []


def apply_renewal(
    order: Order, period: SubscriptionPeriod, tx: VerifiedTransaction, source: str
) -> int:
    """Extend a membership by one paid period (called once, after the order was marked
    paid). Returns the number of entitlements granted or renewed."""
    from ..courses.learning import sync

    sub = _lock(period.subscription)
    if period.status == "paid":
        return 0
    if sub.status not in RENEWABLE:
        order.needs_review = True
        order.review_reason = "Renewal payment for a membership that has ended (consider a refund)."
        billing._event(sub, "renewal_after_end", "webhook", details={"order": order.number})
        audit_service.record(
            "membership.renewal_after_end",
            "customer_subscription",
            sub.id,
            details={"order": order.number},
        )
        return 0
    paid_at = _aware(tx.paid_at) or _now()
    # Periods are contiguous: a late (grace) payment does not move the anniversary forward.
    start = _aware(sub.current_period_end) or paid_at
    end = billing.add_period(start, sub.interval)
    period.status = "paid"
    period.period_start, period.period_end = start, end
    previous = sub.status
    sub.status = "active"
    sub.current_period_start = start
    sub.current_period_end = end
    sub.access_until = end
    sub.past_due_since = None
    sub.lock_version += 1
    if sub.cancel_at_period_end:
        # Paystack charged after a cancellation: the period is paid, so it is honoured.
        order.needs_review = True
        order.review_reason = "Renewal charged after the member cancelled; check Paystack."
    granted = billing.grant_plan_access(sub, end)
    billing._event(
        sub,
        "renewed",
        billing.EVENT_SOURCE.get(source, "system"),
        from_status=previous,
        to_status="active",
        details={"order": order.number, "reference": tx.reference, "period": period.sequence},
    )
    sync(_customer(sub))
    audit_service.record(
        "membership.renewed",
        "customer_subscription",
        sub.id,
        details={"order": order.number, "period": period.sequence, "via": source},
    )
    return granted


# ---- failed payments and provider-side cancellation ----------------------------------------


def _by_code(code: str | None) -> CustomerSubscription | None:
    if not code:
        return None
    return db.session.scalar(
        select(CustomerSubscription).where(CustomerSubscription.provider_subscription_code == code)
    )


def process_payment_failed(record: PaymentEvent) -> tuple[str, str]:
    """``invoice.payment_failed``: confirmed by re-fetching the subscription. It can only
    *start* the grace period (bounded by the paid period's end), never extend paid access."""
    code = (record.payload or {}).get("subscription_code")
    if not code:
        return "ignored", "No subscription code."
    sub = _by_code(code)
    if sub is None:
        return "deferred", "Subscription not linked yet; will retry."
    remote = get_provider(sub.provider).fetch_subscription(code)
    if remote.mode and remote.mode != sub.mode:
        return "rejected", f"{remote.mode} subscription for a {sub.mode} membership."
    sub = _lock(sub)
    if sub.status != "active" or sub.cancel_at_period_end:
        return "processed", f"No change ({sub.status})."
    end = _aware(sub.current_period_end)
    if end is not None and _now() < end - timedelta(days=3):
        # Out of order: this failure belongs to a cycle that has since been paid.
        return "processed", "Stale failure: the current period is paid."
    start_grace(sub, "webhook", payment_event_id=record.id)
    db.session.commit()
    return "processed", f"Membership {sub.public_id} is past due."


def start_grace(
    sub: CustomerSubscription, source: str, *, payment_event_id: int | None = None
) -> None:
    """An unpaid renewal: keep access until ``current_period_end + grace`` (fixed), then
    end. Idempotent for a subscription that is already past due or in grace."""
    if sub.status not in ("active",):
        return
    now = _now()
    end = _aware(sub.current_period_end) or now
    until = end + timedelta(days=grace_days())
    previous = sub.status
    sub.status = "past_due" if now < end else "grace"
    sub.past_due_since = now
    sub.access_until = until
    sub.lock_version += 1
    billing._event(
        sub,
        "payment_failed",
        source,
        from_status=previous,
        to_status=sub.status,
        details={"access_until": iso(until)},
        payment_event_id=payment_event_id,
    )
    if now >= until:
        _end(sub, "payment_failed", source, notify=False)
        _stop_provider_charges(sub)
        _notify(sub, "membership_ended", reason="payment_failed")
        return
    _set_entitlement_expiry(sub, until)
    audit_service.record(
        "membership.past_due", "customer_subscription", sub.id, details={"access_until": iso(until)}
    )
    _notify(sub, "membership_payment_failed", access_until=_fmt(until))


def process_subscription_disabled(record: PaymentEvent) -> tuple[str, str]:
    """``subscription.not_renew`` / ``subscription.disable`` (e.g. cancelled from the
    Paystack-hosted page): re-fetched, then treated as a cancellation at period end."""
    code = (record.payload or {}).get("subscription_code")
    sub = _by_code(code)
    if sub is None:
        return (
            ("deferred", "Subscription not linked yet; will retry.")
            if code
            else (
                "ignored",
                "No subscription code.",
            )
        )
    remote = get_provider(sub.provider).fetch_subscription(code)
    if remote.status not in NOT_RENEWING:
        return "processed", f"Paystack reports {remote.status or 'unknown'}; no change."
    sub = _lock(sub)
    if sub.status not in RENEWABLE or sub.cancel_at_period_end:
        return "processed", "Already cancelled or ended."
    _schedule_cancellation(sub, "webhook", requested_here=False)
    db.session.commit()
    return "processed", f"Membership {sub.public_id} will end at the period end."


# ---- customer actions ---------------------------------------------------------------------


def _owned(customer: Customer, subscription_id: Any) -> CustomerSubscription:
    if not isinstance(subscription_id, str):
        raise ValidationError(details={"subscription_id": ["Send the subscription id."]})
    sub = db.session.scalar(
        select(CustomerSubscription).where(
            CustomerSubscription.public_id == subscription_id,
            CustomerSubscription.customer_id == customer.id,
        )
    )
    if sub is None:
        raise NotFoundError("Membership not found.")
    return sub


def _require_linked(sub: CustomerSubscription) -> None:
    if not (sub.provider_subscription_code and sub.provider_email_token):
        raise ConflictError(
            "Your membership is still being set up with Paystack. Please try again in a few "
            "minutes.",
            details={"code": "subscription_not_linked"},
        )


def _schedule_cancellation(sub: CustomerSubscription, source: str, *, requested_here: bool) -> None:
    now = _now()
    paid_until = _aware(sub.current_period_end) or now
    sub.cancel_at_period_end = True
    sub.cancel_requested_at = now
    # Already-paid time is kept; unpaid grace time is not.
    sub.access_until = paid_until
    sub.lock_version += 1
    billing._event(
        sub,
        "cancellation_scheduled",
        source,
        details={"access_until": iso(paid_until), "requested_here": requested_here},
    )
    audit_service.record(
        "membership.cancellation_scheduled",
        "customer_subscription",
        sub.id,
        details={"access_until": iso(paid_until), "via": source},
    )
    if now >= paid_until:
        _end(sub, "cancelled", source)
        return
    _set_entitlement_expiry(sub, paid_until)
    _notify(sub, "membership_cancelled", access_until=_fmt(paid_until))


def cancel(customer: Customer, data: Any) -> dict[str, Any]:
    """Cancel at the end of the paid period. Paystack is told first: if it can't confirm,
    nothing changes locally (otherwise the member could be charged after cancelling)."""
    sub = _owned(customer, (data or {}).get("subscription_id") if isinstance(data, dict) else None)
    cancel_subscription(sub, "customer")
    db.session.commit()
    return billing.customer_view(customer)


def cancel_subscription(
    sub: CustomerSubscription, source: str, *, immediate: bool = False, reason: str = ""
) -> CustomerSubscription:
    """The provider-safe cancellation shared by customers and staff (Batch 10.4).

    Paystack must confirm first. ``immediate`` (staff only) ends access now instead of at
    the end of the paid period; refunds stay a separate, permission-checked action."""
    if sub.status not in RENEWABLE:
        raise ConflictError("This membership can't be cancelled.", details={"code": "not_active"})
    if sub.cancel_at_period_end and not immediate:
        return sub
    if not sub.cancel_at_period_end:
        _require_linked(sub)
        try:
            get_provider(sub.provider).disable_subscription(
                sub.provider_subscription_code, sub.provider_email_token
            )
        except ProviderError:
            raise ProviderActionFailed() from None
    sub = _lock(sub)
    if sub.status not in RENEWABLE:
        return sub
    if not sub.cancel_at_period_end:
        _schedule_cancellation(sub, source, requested_here=True)
    if immediate and sub.status in RENEWABLE:
        _end(sub, "cancelled", source)
        if reason:
            billing._event(sub, "ended_by_staff", source, details={"reason": reason[:300]})
    return sub


def resume(customer: Customer, data: Any) -> dict[str, Any]:
    """Undo a scheduled cancellation while paid time remains (Paystack must re-enable the
    subscription; if it refuses, the member can join again after the period ends)."""
    sub = _owned(customer, (data or {}).get("subscription_id") if isinstance(data, dict) else None)
    now = _now()
    if (
        sub.status != "active"
        or not sub.cancel_at_period_end
        or not sub.access_until
        or _aware(sub.access_until) <= now
    ):
        raise ConflictError(
            "Only a membership that is set to end can be resumed.",
            details={"code": "not_resumable"},
        )
    _require_linked(sub)
    try:
        get_provider(sub.provider).enable_subscription(
            sub.provider_subscription_code, sub.provider_email_token
        )
    except ProviderError as exc:
        raise ConflictError(
            "Paystack couldn't resume this membership. You can join again once it ends.",
            details={"code": "resume_unavailable", "provider": str(exc)[:200]},
        ) from None
    sub = _lock(sub)
    if sub.cancel_at_period_end and sub.status == "active":
        sub.cancel_at_period_end = False
        sub.cancel_requested_at = None
        sub.lock_version += 1
        billing._event(sub, "resumed", "customer")
        audit_service.record("membership.resumed", "customer_subscription", sub.id)
    db.session.commit()
    return billing.customer_view(customer)


def payment_method_link(customer: Customer, subscription_id: Any) -> dict[str, Any]:
    """A Paystack-hosted page for changing the card. Nothing about the card is stored."""
    sub = _owned(customer, subscription_id)
    if sub.status not in RENEWABLE:
        raise ConflictError(
            "This membership has no active billing.", details={"code": "not_active"}
        )
    if not sub.provider_subscription_code:
        _require_linked(sub)
    try:
        url = get_provider(sub.provider).manage_link(sub.provider_subscription_code)
    except ProviderError:
        raise ProviderActionFailed() from None
    billing._event(sub, "payment_method_link", "customer")
    db.session.commit()
    return {"url": url}


# ---- reconciliation (flask memberships reconcile) ------------------------------------------


def reconcile(now: datetime | None = None, *, check_provider: bool = True) -> dict[str, int]:
    """Bring statuses in line with time and Paystack. Safe to run repeatedly and
    concurrently with webhooks. It can end or shorten access, never extend paid access:
    grace always counts from the end of the paid period."""
    now = now or _now()
    counts = {
        "abandoned": 0,
        "grace": 0,
        "ended": 0,
        "cancelled_at_provider": 0,
        "provider_errors": 0,
        "events_retried": 0,
    }
    for sub in db.session.scalars(
        select(CustomerSubscription).where(CustomerSubscription.status == "pending")
    ).all():
        if billing._expired_unpaid(sub):
            billing._set_status(sub, "incomplete", "checkout_abandoned", "job")
            counts["abandoned"] += 1
    db.session.commit()

    ids = db.session.scalars(
        select(CustomerSubscription.id).where(CustomerSubscription.status.in_(RENEWABLE))
    ).all()
    for sub_id in ids:
        try:
            _reconcile_one(
                db.session.get(CustomerSubscription, sub_id), now, check_provider, counts
            )
            db.session.commit()
        except Exception:  # one bad row must not stop the others; nothing was extended
            db.session.rollback()
            current_app.logger.exception("Reconciling subscription %s failed", sub_id)
            counts["provider_errors"] += 1

    counts["events_retried"] = _retry_deferred_events()
    return counts


def _reconcile_one(sub: CustomerSubscription, now: datetime, check_provider: bool, counts) -> None:
    sub = _lock(sub)
    if sub.status not in RENEWABLE:
        return
    sub.last_reconciled_at = now
    period_end = _aware(sub.current_period_end)
    access_until = _aware(sub.access_until)
    if sub.cancel_at_period_end:
        if access_until is None or now >= access_until:
            _end(sub, "cancelled", "job")
            counts["ended"] += 1
        return
    if sub.status in ("past_due", "grace"):
        if access_until is None or now >= access_until:
            _end(sub, "payment_failed", "job")
            _stop_provider_charges(sub)
            counts["ended"] += 1
        elif sub.status == "past_due" and period_end and now >= period_end:
            billing._set_status(sub, "grace", "grace_started", "job")
        return
    if period_end is None or now < period_end:
        return
    # Active, but the paid period is over and no verified renewal was recorded.
    if check_provider and sub.provider_subscription_code:
        try:
            remote = get_provider(sub.provider).fetch_subscription(sub.provider_subscription_code)
            if remote.status in NOT_RENEWING:
                _schedule_cancellation(sub, "job", requested_here=False)
                counts["cancelled_at_provider"] += 1
                if sub.status == "ended":
                    counts["ended"] += 1
                return
        except ProviderError:
            counts["provider_errors"] += 1  # fall through: grace still starts on time
    start_grace(sub, "job")
    counts["grace" if sub.status != "ended" else "ended"] += 1


def _retry_deferred_events() -> int:
    """Membership webhooks that arrived before the subscription they refer to existed."""
    from ..commerce.payments import process_event

    events = db.session.scalars(
        select(PaymentEvent)
        .where(
            PaymentEvent.status == "deferred",
            PaymentEvent.event_type.in_(MEMBERSHIP_EVENTS),
            PaymentEvent.order_id.is_(None),
        )
        .order_by(PaymentEvent.id)
        .limit(100)
    ).all()
    retried = 0
    for event in events:
        try:
            process_event(event)
            retried += 1
        except APIError:
            db.session.rollback()
    return retried


# ---- refunds and disputes (called from commerce.payments) ---------------------------------


def on_refund(order: Order, refund: Refund, actor: User | None) -> None:
    """A processed refund of a membership payment. When staff chose to revoke access, the
    membership ends now and Paystack is told to stop charging; otherwise it is recorded."""
    period = period_for_order(order)
    sub = period.subscription if period is not None else billing.subscription_for_order(order)
    if sub is None:
        return
    sub = _lock(sub)
    if period is not None and order.status == "refunded":
        period.status = "refunded"
    billing._event(
        sub,
        "refunded",
        "admin" if actor else "webhook",
        details={
            "order": order.number,
            "amount_minor": refund.amount_minor,
            "revoke": refund.revoke_access,
        },
    )
    if refund.revoke_access and sub.status in (*RENEWABLE, "pending"):
        _end(sub, "refunded", "admin" if actor else "webhook")
        _stop_provider_charges(sub)


def on_dispute(order: Order, record: PaymentEvent) -> None:
    """Disputes are recorded for staff; access is decided by them (refund/revoke)."""
    period = period_for_order(order)
    sub = period.subscription if period is not None else billing.subscription_for_order(order)
    if sub is None:
        return
    billing._event(
        sub,
        "payment_disputed",
        "webhook",
        details={"order": order.number, "status": (record.payload or {}).get("raw_status", "")},
        payment_event_id=record.id,
    )


# ---- views ---------------------------------------------------------------------------------


def periods_view(sub: CustomerSubscription) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(sub.periods, key=lambda p: p.sequence, reverse=True)[:24]:
        order = db.session.get(Order, p.order_id) if p.order_id else None
        rows.append(
            {
                "sequence": p.sequence,
                "status": p.status,
                "period_start": iso(p.period_start),
                "period_end": iso(p.period_end),
                "amount": money(p.amount_minor, p.currency),
                "order": order.public_id
                if order is not None and order.status in ("paid", "partially_refunded", "refunded")
                else None,
            }
        )
    return rows


def actions(sub: CustomerSubscription) -> dict[str, bool]:
    linked = bool(sub.provider_subscription_code and sub.provider_email_token)
    now = _now()
    return {
        "can_cancel": sub.status in RENEWABLE and not sub.cancel_at_period_end,
        "can_resume": (
            sub.status == "active"
            and sub.cancel_at_period_end
            and linked
            and bool(sub.access_until)
            and _aware(sub.access_until) > now
        ),
        "can_update_payment_method": sub.status in RENEWABLE
        and bool(sub.provider_subscription_code),
        "linked": linked,
    }
