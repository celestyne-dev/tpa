"""Membership subscription checkout and verified first-payment activation (Batch 10.2).

Reuses the commerce payment infrastructure instead of a second engine:

- Each checkout creates an ``Order`` (``kind="subscription"``) for the first payment, with
  one line for the plan's hidden backing product. ``checkout.start_payment`` opens the
  provider's hosted page with the plan code, and ``payments.apply_verified`` verifies the
  charge (reference, amount, currency, mode, provider id, and here also the plan code)
  before anything is activated. Receipts, refunds and the admin orders screens therefore
  work unchanged.
- The local subscription and its first billing period are committed *before* Paystack is
  called. The subscription becomes ``active`` only from a provider-verified successful
  charge (customer return page or ``charge.success`` webhook, whichever comes first; the
  other is a no-op). ``subscription.create`` webhooks only attach the provider's
  subscription code after re-fetching it from Paystack; they never grant access.
- One live subscription per customer (partial unique index); an abandoned checkout is
  marked ``incomplete`` before a new one starts. Idempotency keys make retries safe.
- Access: on activation, membership-source entitlements are granted for the plan's
  published, eligible products (expiring at the period end) and course enrolments are
  synced. Separately purchased entitlements are separate rows and are never touched.

Renewals, failed payments, grace, cancellation and reconciliation: ``lifecycle`` (10.3).
Live payments remain disabled.
"""

from __future__ import annotations

import calendar
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...auth.permissions import Permission as P
from ...commerce.currency import money
from ...extensions import db
from ...models import (
    Customer,
    CustomerSubscription,
    MembershipPlan,
    MembershipPlanPrice,
    MembershipProviderPlan,
    Order,
    OrderItem,
    PaymentEvent,
    Product,
    SubscriptionEvent,
    SubscriptionPeriod,
    User,
)
from ...models.memberships import LIVE_SUBSCRIPTION_STATUSES
from ...payments.base import ProviderError, VerifiedTransaction
from ...payments.config import checkout_available_for, checkout_currencies, effective_mode
from ...payments.paystack import get_provider
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import plans as plan_service

_KEY = re.compile(r"^[A-Za-z0-9-]{8,64}$")
EVENT_SOURCE = {"webhook": "webhook", "customer": "verification", "staff": "admin"}


class CheckoutUnavailableError(APIError):
    status_code = 409
    code = "membership_checkout_unavailable"
    message = "Membership checkout isn't available right now."


class EmailVerificationRequired(APIError):
    status_code = 403
    code = "email_verification_required"
    message = "Confirm your email address before joining."


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def add_period(start: datetime, interval: str) -> datetime:
    """The end of a billing period starting at ``start`` (month ends are clamped)."""
    months = 1 if interval == "month" else 12
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


# ---- availability -----------------------------------------------------------------------------


def billing_status(customer: Customer | None = None) -> dict[str, Any]:
    """Whether membership checkout is open. Test mode only; live is always refused.

    Requires MEMBERSHIP_BILLING_MODE=test (the deployment's assertion that recurring USD
    plans and charges were verified in the Paystack test dashboard), test-mode checkout in
    force with a test-mode Paystack key, and USD enabled for checkout.
    """
    closed = {
        "available": False,
        "status": "coming_soon",
        "message": "Paid memberships are coming soon. No payments are being taken yet.",
    }
    if current_app.config.get("MEMBERSHIP_BILLING_MODE") != "test":
        return closed
    provider = get_provider()
    if effective_mode() != "test" or provider.mode != "test" or "USD" not in checkout_currencies():
        return closed | {"status": "unavailable"}
    status = {
        "available": True,
        "status": "test",
        "message": "Test mode: memberships use Paystack test payments; no real money is taken.",
    }
    if customer is not None:
        allowed, reason = checkout_available_for(customer)
        if not allowed:
            return {"available": False, "status": "unavailable", "message": reason}
    return status


# ---- provider plans (admin) ---------------------------------------------------------------------


def ensure_backing_product(plan: MembershipPlan) -> Product:
    """The hidden product subscription orders point at (type "membership", never sold)."""
    if plan.product_id is not None:
        return db.session.get(Product, plan.product_id)
    product = Product(
        public_id=secrets.token_hex(8),
        slug=f"membership-{plan.public_id.lower().replace('_', '-')}"[:200],
        product_type="membership",
        title=plan.name,
        status="draft",
        sales_status="coming_soon",
        pricing_model="paid",
        membership_eligible=False,
    )
    db.session.add(product)
    db.session.flush()
    plan.product_id = product.id
    return product


def _mode_for_sync() -> str:
    provider = get_provider()
    if not provider.configured():
        raise CheckoutUnavailableError("Add the Paystack test secret key first.")
    if provider.mode != "test":
        raise CheckoutUnavailableError(
            "Membership plans can only be synced with a Paystack test key for now."
        )
    return "test"


def _check_plan(pp: MembershipProviderPlan, price: MembershipPlanPrice) -> list[str]:
    """Compare the provider's plan with the immutable local price."""
    remote = get_provider().fetch_plan(pp.plan_code)
    problems = []
    if remote.amount_minor != price.amount_minor:
        problems.append(f"amount {remote.amount_minor} ≠ {price.amount_minor}")
    if remote.currency != price.currency:
        problems.append(f"currency {remote.currency} ≠ {price.currency}")
    if remote.interval != price.interval:
        problems.append(f"interval {remote.interval or '?'} ≠ {price.interval}")
    if remote.mode and remote.mode != pp.mode:
        problems.append(f"{remote.mode} plan used in {pp.mode} mode")
    return problems


def sync_provider_plans(plan: MembershipPlan, data: Any, actor: User) -> MembershipPlan:
    """Create (or re-verify) the Paystack test plan for each active price."""
    plan_service._require(actor, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE)
    plan_service._editable(plan)
    plan_service._check_lock(plan, data)
    mode = _mode_for_sync()
    provider = get_provider()
    ensure_backing_product(plan)
    results = []
    try:
        for price in plan.active_prices:
            pp = provider_plan_for(price, mode)
            if pp is None:
                remote = provider.create_plan(
                    name=f"{plan.name} — {'monthly' if price.interval == 'month' else 'yearly'}",
                    amount_minor=price.amount_minor,
                    currency=price.currency,
                    interval=price.interval,
                )
                pp = MembershipProviderPlan(
                    price_id=price.id, provider=provider.name, mode=mode, plan_code=remote.plan_code
                )
                db.session.add(pp)
                db.session.flush()
            problems = _check_plan(pp, price)
            if problems:
                raise ConflictError(
                    "The Paystack plan doesn't match this price: " + "; ".join(problems)
                )
            pp.verified_at = _now()
            results.append({"price_id": price.public_id, "plan_code": pp.plan_code})
    except ProviderError as exc:
        db.session.rollback()
        raise CheckoutUnavailableError(f"Paystack: {exc}") from None
    plan_service._touch(plan, actor)
    db.session.flush()
    audit_service.record(
        "membership.provider_plans_synced",
        "membership_plan",
        plan.id,
        actor=actor,
        details={"mode": mode, "plans": results},
    )
    return plan


def provider_plan_for(price: MembershipPlanPrice, mode: str) -> MembershipProviderPlan | None:
    return db.session.scalar(
        select(MembershipProviderPlan).where(
            MembershipProviderPlan.price_id == price.id,
            MembershipProviderPlan.provider == "paystack",
            MembershipProviderPlan.mode == mode,
        )
    )


def provider_plans_dict(plan: MembershipPlan) -> list[dict[str, Any]]:
    out = []
    for price in plan.active_prices:
        for mode in ("test", "live"):
            pp = provider_plan_for(price, mode)
            if pp is not None:
                out.append(
                    {
                        "price_id": price.public_id,
                        "interval": price.interval,
                        "mode": mode,
                        "plan_code": pp.plan_code,
                        "verified_at": iso(pp.verified_at),
                    }
                )
    return out


# ---- history ----------------------------------------------------------------------------------


def _event(
    sub: CustomerSubscription,
    type_: str,
    source: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    details: dict | None = None,
    payment_event_id: int | None = None,
) -> None:
    db.session.add(
        SubscriptionEvent(
            subscription_id=sub.id,
            type=type_,
            from_status=from_status,
            to_status=to_status,
            source=source,
            payment_event_id=payment_event_id,
            details=details or {},
        )
    )


def _set_status(sub: CustomerSubscription, status: str, type_: str, source: str, **details):
    previous = sub.status
    sub.status = status
    sub.lock_version += 1
    _event(sub, type_, source, from_status=previous, to_status=status, details=details)


# ---- checkout ---------------------------------------------------------------------------------


def _live_subscription(customer: Customer) -> CustomerSubscription | None:
    return db.session.scalar(
        select(CustomerSubscription).where(
            CustomerSubscription.customer_id == customer.id,
            CustomerSubscription.status.in_(LIVE_SUBSCRIPTION_STATUSES),
        )
    )


def _return_url(sub: CustomerSubscription) -> str:
    return f"{current_app.config['SITE_URL']}/account/membership?subscription={sub.public_id}"


def _resume(sub: CustomerSubscription) -> str | None:
    """The checkout address for a pending subscription, or None when it can't continue
    (then it is marked incomplete)."""
    from ..commerce import checkout

    order = db.session.get(Order, sub.order_id) if sub.order_id else None
    expired = order is None or (order.expires_at and _aware(order.expires_at) <= _now())
    if order is not None and order.status == "paid":
        return None  # paid: activation happens through verification, nothing to resume
    if expired or order.status not in ("awaiting_payment", "failed"):
        _set_status(sub, "incomplete", "checkout_abandoned", "customer")
        db.session.commit()
        return None
    latest = order.attempts[-1] if order.attempts else None
    if latest is not None and latest.status == "initialized":
        return latest.authorization_url
    return checkout.start_payment(
        order, plan_code=sub.provider_plan.plan_code, return_url=_return_url(sub)
    )


def _clean_checkout(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - {
        "price_id",
        "idempotency_key",
        "expected_amount_minor",
        "currency",
        "accept_terms",
    }
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    if not isinstance(data.get("price_id"), str):
        errors["price_id"] = ["Choose a plan price."]
    if not isinstance(data.get("idempotency_key"), str) or not _KEY.match(data["idempotency_key"]):
        errors["idempotency_key"] = ["Send a unique request key."]
    amount = data.get("expected_amount_minor")
    if not isinstance(amount, int) or isinstance(amount, bool):
        errors["expected_amount_minor"] = ["Send the amount you were shown."]
    if data.get("currency") != "USD":
        errors["currency"] = ["Memberships are billed in USD."]
    if data.get("accept_terms") is not True:
        errors["accept_terms"] = ["Accept the membership terms to continue."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return data


def start_checkout(customer: Customer, data: Any) -> dict[str, Any]:
    """Create (or resume) the customer's pending subscription and return the hosted
    checkout address. Nothing is activated here."""
    from ..commerce import checkout
    from ..commerce.checkout import _new_number

    if customer.status != "active" or customer.email_verified_at is None:
        raise EmailVerificationRequired()
    data = _clean_checkout(data)
    status = billing_status(customer)
    if not status["available"]:
        raise CheckoutUnavailableError(status["message"])
    price = db.session.scalar(
        select(MembershipPlanPrice).where(MembershipPlanPrice.public_id == data["price_id"])
    )
    if (
        price is None
        or price.status != "active"
        or price.plan.status != "published"
        or price.currency != "USD"
    ):
        raise NotFoundError("This membership price isn't available.")
    plan = price.plan
    if data["expected_amount_minor"] != price.amount_minor:
        raise ConflictError(
            "The price has changed. Please review it before joining.",
            details={"code": "price_changed", "price": money(price.amount_minor, price.currency)},
        )
    key = data["idempotency_key"]

    same = db.session.scalar(
        select(CustomerSubscription).where(
            CustomerSubscription.customer_id == customer.id,
            CustomerSubscription.idempotency_key == key,
        )
    )
    if same is not None:  # a retry of the same request
        url = _resume(same) if same.status == "pending" else None
        return {"subscription": subscription_dict(same), "checkout_url": url, "resumed": True}

    live = _live_subscription(customer)
    if live is not None and live.status != "pending":
        raise ConflictError("You already have a membership.", details={"code": "already_member"})
    if live is not None:
        if live.price_id == price.id:
            url = _resume(live)
            if url:
                return {
                    "subscription": subscription_dict(live),
                    "checkout_url": url,
                    "resumed": True,
                }
        else:
            paid = live.order_id and db.session.get(Order, live.order_id).status == "paid"
            if not paid:  # a different price: the earlier checkout is superseded
                _set_status(live, "incomplete", "checkout_superseded", "customer")
                db.session.commit()
        if live.status == "pending":  # paid but not verified yet
            raise ConflictError(
                "Your payment is being confirmed. Refresh in a moment.",
                details={"code": "subscription_pending"},
            )

    mode = effective_mode()
    pp = provider_plan_for(price, mode)
    if pp is None or pp.verified_at is None:
        raise CheckoutUnavailableError("This plan isn't ready for checkout yet.")
    try:
        problems = _check_plan(pp, price)
    except ProviderError:
        raise CheckoutUnavailableError(
            "We couldn't reach Paystack. Please try again shortly."
        ) from None
    if problems:
        current_app.logger.warning("Paystack plan %s mismatch: %s", pp.plan_code, problems)
        raise CheckoutUnavailableError("This plan isn't ready for checkout yet.")

    from ...payments.config import get_settings

    settings = get_settings()
    product = ensure_backing_product(plan)
    order = Order(
        number=_new_number(),
        public_id=secrets.token_hex(16),
        customer_id=customer.id,
        email=customer.email,
        status="awaiting_payment",
        kind="subscription",
        currency=price.currency,
        subtotal_minor=price.amount_minor,
        tax_minor=0,
        discount_minor=0,
        total_minor=price.amount_minor,
        provider="paystack",
        mode=mode,
        idempotency_key=f"m-{key}"[:64],
        terms_version=settings["payments.terms_version"] or "",
        terms_accepted_at=_now(),
        expires_at=_now() + timedelta(minutes=settings["payments.order_expiry_minutes"]),
    )
    label = f"{plan.name} membership ({'monthly' if price.interval == 'month' else 'yearly'})"
    order.items.append(
        OrderItem(
            product_id=product.id,
            product_public_id=product.public_id,
            title=label[:200],
            product_type="membership",
            slug=product.slug,
            currency=price.currency,
            unit_amount_minor=price.amount_minor,
            quantity=1,
            line_total_minor=price.amount_minor,
        )
    )
    sub = CustomerSubscription(
        public_id=secrets.token_urlsafe(12),
        customer_id=customer.id,
        plan_id=plan.id,
        price_id=price.id,
        provider_plan_id=pp.id,
        status="pending",
        provider="paystack",
        mode=mode,
        interval=price.interval,
        currency=price.currency,
        amount_minor=price.amount_minor,
        idempotency_key=key,
        end_reason="",
    )
    try:
        with db.session.begin_nested():
            db.session.add(order)
            db.session.flush()
            sub.order_id = order.id
            db.session.add(sub)
            db.session.flush()
            db.session.add(
                SubscriptionPeriod(
                    subscription_id=sub.id,
                    sequence=1,
                    status="pending",
                    order_id=order.id,
                    amount_minor=price.amount_minor,
                    currency=price.currency,
                )
            )
            _event(
                sub,
                "checkout_started",
                "customer",
                to_status="pending",
                details={"order": order.number, "price_id": price.public_id},
            )
            db.session.flush()
    except IntegrityError:
        # A concurrent request created a subscription first (same key or another live one).
        db.session.rollback()
        raise ConflictError(
            "A membership checkout is already in progress. Refresh the page.",
            details={"code": "subscription_pending"},
        ) from None
    audit_service.record(
        "membership.checkout_started",
        "customer_subscription",
        sub.id,
        details={"customer_id": customer.id, "order": order.number, "mode": mode},
    )
    db.session.commit()
    url = checkout.start_payment(order, plan_code=pp.plan_code, return_url=_return_url(sub))
    return {"subscription": subscription_dict(sub), "checkout_url": url, "resumed": False}


# ---- verification hooks (called from payments.apply_verified) ---------------------------------


def subscription_for_order(order: Order) -> CustomerSubscription | None:
    """The subscription an order pays for: its first order, or a renewal period's order."""
    sub = db.session.scalar(
        select(CustomerSubscription).where(CustomerSubscription.order_id == order.id)
    )
    if sub is None:
        period = db.session.scalar(
            select(SubscriptionPeriod).where(SubscriptionPeriod.order_id == order.id)
        )
        sub = period.subscription if period is not None else None
    return sub


def _renewal_period(order: Order) -> SubscriptionPeriod | None:
    period = db.session.scalar(
        select(SubscriptionPeriod).where(SubscriptionPeriod.order_id == order.id)
    )
    return period if period is not None and period.sequence > 1 else None


def charge_problems(order: Order, tx: VerifiedTransaction) -> list[str]:
    """Extra checks for a subscription charge: it must be for the expected plan (and, for a
    renewal, the membership's Paystack customer)."""
    from .lifecycle import renewal_problems

    sub = subscription_for_order(order)
    if sub is None:
        return ["no subscription for this order"]
    expected = sub.provider_plan.plan_code
    if tx.plan_code != expected:
        return [f"plan {tx.plan_code or 'none'} does not match {expected}"]
    if sub.mode != tx.mode:
        return [f"{tx.mode} payment for a {sub.mode} subscription"]
    if _renewal_period(order) is not None:
        return renewal_problems(sub, tx)
    return []


def grant_plan_access(sub: CustomerSubscription, until: datetime) -> int:
    """Grant (or extend to ``until``) the plan's published, eligible products."""
    from ..commerce import access

    customer = db.session.get(Customer, sub.customer_id)
    plan = db.session.get(MembershipPlan, sub.plan_id)
    granted = 0
    for item in plan.access:
        product = item.product
        if product.status != "published" or plan_service.eligibility_problem(product):
            continue
        access.grant(
            customer,
            product,
            source="membership",
            reference=f"subscription-{sub.id}",
            expires_at=until,
            reason=f"Membership {plan.name}",
        )
        granted += 1
    return granted


def activate_from_order(order: Order, tx: VerifiedTransaction, source: str) -> int:
    """Activate the subscription paid by ``order`` (after verification). Returns the number
    of entitlements granted. Idempotent: a second call does nothing. Renewal orders extend
    the membership instead (``lifecycle.apply_renewal``)."""
    from ..courses.learning import sync

    renewal = _renewal_period(order)
    if renewal is not None:
        from .lifecycle import apply_renewal

        return apply_renewal(order, renewal, tx, source)
    sub = subscription_for_order(order)
    if sub is None or sub.status == "active" and sub.activated_at is not None:
        return 0
    customer = db.session.get(Customer, sub.customer_id)
    event_source = EVENT_SOURCE.get(source, "system")
    other = _live_subscription(customer)
    if other is not None and other.id != sub.id:
        # Paid for an abandoned checkout while another membership is live: never two.
        order.needs_review = True
        order.review_reason = "Duplicate membership payment (another membership is live); refund."
        _event(sub, "duplicate_payment", event_source, details={"order": order.number})
        audit_service.record(
            "membership.duplicate_payment",
            "customer_subscription",
            sub.id,
            details={"order": order.number, "live": other.public_id},
        )
        return 0
    start = _aware(tx.paid_at) or _now()
    end = add_period(start, sub.interval)
    previous = sub.status
    sub.status = "active"
    sub.activated_at = _now()
    sub.current_period_start = start
    sub.current_period_end = end
    sub.access_until = end
    sub.provider_customer_code = sub.provider_customer_code or (tx.customer_code or None)
    sub.lock_version += 1
    period = next((p for p in sub.periods if p.sequence == 1), None)
    if period is not None:
        period.status = "paid"
        period.period_start, period.period_end = start, end
    granted = grant_plan_access(sub, end)
    _event(
        sub,
        "activated",
        event_source,
        from_status=previous,
        to_status="active",
        details={"order": order.number, "reference": tx.reference, "entitlements": granted},
    )
    sync(customer)  # membership course access (enrolments with source "membership")
    audit_service.record(
        "membership.activated",
        "customer_subscription",
        sub.id,
        details={"customer_id": customer.id, "entitlements": granted, "via": source},
    )
    return granted


def membership_email(order: Order) -> tuple[str, dict[str, Any]] | None:
    """The membership email for a paid subscription order: welcome or renewal."""
    sub = subscription_for_order(order)
    if sub is None or sub.status != "active":
        return None
    period = _renewal_period(order)
    if period is not None and period.status != "paid":
        return None  # the payment did not extend the membership (flagged for review)
    context = {
        "plan_name": sub.plan.name,
        "period_end": sub.current_period_end.strftime("%d %B %Y") if sub.current_period_end else "",
        "test": sub.mode == "test",
    }
    return ("membership_renewed" if period is not None else "membership_activated"), context


# ---- webhooks ---------------------------------------------------------------------------------


def process_subscription_created(record: PaymentEvent) -> tuple[str, str]:
    """Attach Paystack's subscription code to the local subscription. The event is only a
    hint: the subscription is re-fetched from Paystack, and nothing is activated here."""
    payload = record.payload or {}
    code = payload.get("subscription_code")
    if not code:
        return "ignored", "No subscription code."
    existing = db.session.scalar(
        select(CustomerSubscription).where(CustomerSubscription.provider_subscription_code == code)
    )
    if existing is not None:
        return "processed", f"Subscription {existing.public_id} already linked."
    remote = get_provider().fetch_subscription(code)
    pp = db.session.scalar(
        select(MembershipProviderPlan).where(
            MembershipProviderPlan.provider == "paystack",
            MembershipProviderPlan.plan_code == remote.plan_code,
        )
    )
    if pp is None:
        return "ignored", "Not a membership plan of this site."
    if remote.mode and remote.mode != pp.mode:
        return "rejected", f"{remote.mode} subscription for a {pp.mode} plan."
    candidates = db.session.scalars(
        select(CustomerSubscription)
        .join(Customer, Customer.id == CustomerSubscription.customer_id)
        .where(
            CustomerSubscription.provider_plan_id == pp.id,
            CustomerSubscription.provider_subscription_code.is_(None),
            CustomerSubscription.status.in_(("pending", "active", "incomplete")),
        )
        .order_by(CustomerSubscription.id.desc())
    ).all()
    match = next(
        (
            s
            for s in candidates
            if (remote.customer_code and s.provider_customer_code == remote.customer_code)
            or (remote.customer_email and _customer_email(s) == remote.customer_email)
        ),
        None,
    )
    if match is None:
        return "ignored", "No matching membership checkout."
    match.provider_subscription_code = remote.subscription_code or code
    match.provider_email_token = remote.email_token or None
    match.provider_customer_code = match.provider_customer_code or (remote.customer_code or None)
    _event(
        match,
        "provider_subscription_linked",
        "webhook",
        details={"status": remote.status},
        payment_event_id=record.id,
    )
    return "processed", f"Linked to subscription {match.public_id}."


def _customer_email(sub: CustomerSubscription) -> str:
    customer = db.session.get(Customer, sub.customer_id)
    return (customer.email or "").strip().lower() if customer else ""


# ---- customer views ---------------------------------------------------------------------------


def subscription_dict(sub: CustomerSubscription) -> dict[str, Any]:
    plan = sub.plan
    order = db.session.get(Order, sub.order_id) if sub.order_id else None
    latest = order.attempts[-1] if order is not None and order.attempts else None
    checkout_url = None
    if (
        sub.status == "pending"
        and order is not None
        and order.status == "awaiting_payment"
        and latest is not None
        and latest.status == "initialized"
        and not (order.expires_at and _aware(order.expires_at) <= _now())
    ):
        checkout_url = latest.authorization_url
    return {
        "id": sub.public_id,
        "status": sub.status,
        "test_mode": sub.mode == "test",
        "plan": {"name": plan.name, "slug": plan.slug},
        "interval": sub.interval,
        "price": money(sub.amount_minor, sub.currency),
        "current_period_start": iso(sub.current_period_start),
        "current_period_end": iso(sub.current_period_end),
        "access_until": iso(sub.access_until),
        "activated_at": iso(sub.activated_at),
        "created_at": iso(sub.created_at),
        "checkout_url": checkout_url,
        "receipt_order": order.public_id if order is not None and order.status == "paid" else None,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "cancel_requested_at": iso(sub.cancel_requested_at),
        "past_due_since": iso(sub.past_due_since),
        "ended_at": iso(sub.ended_at),
        "end_reason": sub.end_reason or None,
        **lifecycle_actions(sub),
    }


def lifecycle_actions(sub: CustomerSubscription) -> dict[str, bool]:
    from .lifecycle import actions

    return actions(sub)


def customer_view(customer: Customer) -> dict[str, Any]:
    rows = db.session.scalars(
        select(CustomerSubscription)
        .where(CustomerSubscription.customer_id == customer.id)
        .order_by(CustomerSubscription.id.desc())
    ).all()
    current = next((s for s in rows if s.status in LIVE_SUBSCRIPTION_STATUSES), None)
    if current is not None and current.status == "pending" and _expired_unpaid(current):
        _set_status(current, "incomplete", "checkout_abandoned", "system")
        current = None
    included: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    if current is not None:
        from .lifecycle import periods_view

        periods = periods_view(current)
        if current.status in ("active", "past_due", "grace"):
            included = plan_service.public_plan(current.plan)["included"]
        events = [
            {"type": e.type, "created_at": iso(e.created_at)}
            for e in db.session.scalars(
                select(SubscriptionEvent)
                .where(SubscriptionEvent.subscription_id == current.id)
                .order_by(SubscriptionEvent.id)
            )
        ]
    return {
        "subscription": subscription_dict(current) if current else None,
        "included": included,
        "events": events,
        "periods": periods,
        "history": [subscription_dict(s) for s in rows if s is not current][:20],
        "billing": billing_status(customer),
    }


def _expired_unpaid(sub: CustomerSubscription) -> bool:
    order = db.session.get(Order, sub.order_id) if sub.order_id else None
    if order is None:
        return True
    if order.status in ("paid", "partially_refunded", "refunded"):
        return False
    return bool(order.expires_at and _aware(order.expires_at) <= _now())


def verify_for_customer(customer: Customer, subscription_id: Any) -> dict[str, Any]:
    """The return page asks the server to verify the payment with Paystack (the browser's
    redirect itself proves nothing)."""
    from ..commerce.payments import verify_order

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
    outcome = "already_active" if sub.status == "active" else "pending"
    if sub.status == "pending" and sub.order_id:
        order = db.session.get(Order, sub.order_id)
        outcome = verify_order(order, "customer")
        db.session.refresh(sub)
    return {"outcome": outcome, **customer_view(customer)}
