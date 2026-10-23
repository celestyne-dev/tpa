"""Payment verification, webhooks, idempotent order fulfilment and refunds.

Fulfilment happens only after the server itself has confirmed the transaction
with the provider (``verify``), never because a browser was redirected back or
claims success. A verified transaction must match the attempt's reference, the
order's exact amount and currency, and the order's mode (test vs live).

Idempotency and concurrency:
- the order moves to ``paid`` with a conditional UPDATE (``WHERE status IN
  (...)``), so exactly one request/webhook performs fulfilment;
- provider transactions are unique per (provider, kind, provider id);
- entitlements are unique per ``grant_key``;
- webhook events are unique per (provider, dedupe key); replays are counted
  and ignored, while events that failed or arrived early are re-processed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from flask import current_app, request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ...commerce.currency import money
from ...extensions import db
from ...models import (
    Order,
    PaymentAttempt,
    PaymentEvent,
    PaymentTransaction,
    Receipt,
    Refund,
    User,
)
from ...payments.base import ProviderError, VerifiedTransaction
from ...payments.config import get_settings
from ...payments.paystack import get_provider, sanitize
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import emails
from . import entitlements as ent_service

PAYABLE_STATUSES = ("pending", "awaiting_payment", "failed", "cancelled")
FAILED_PROVIDER_STATUSES = {"failed", "reversed"}
ABANDONED_PROVIDER_STATUSES = {"abandoned"}


class WebhookRejected(APIError):
    status_code = 401
    code = "invalid_signature"
    message = "Invalid webhook signature."


def _now() -> datetime:
    return datetime.now(UTC)


# ---- verification and fulfilment ------------------------------------------------------


def apply_verified(
    order: Order, attempt: PaymentAttempt, tx: VerifiedTransaction, source: str
) -> str:
    """Apply a provider-verified transaction to an order. Returns an outcome code.

    Commits the database transaction (fulfilment must be durable before emails go out).
    """
    if tx.reference != attempt.reference:
        return _mismatch(order, attempt, f"reference {tx.reference!r} does not match", source)
    if tx.status != "success":
        attempt.provider_status = tx.status[:40]
        attempt.verified_at = _now()
        # Paystack reports "abandoned" for a transaction the customer has not completed
        # *yet* (they may still be on the payment page), so it is not a failure: the
        # order keeps waiting until it is paid, fails, or expires.
        if tx.status in FAILED_PROVIDER_STATUSES:
            first_failure = attempt.status not in ("failed", "abandoned")
            attempt.status = "failed"
            attempt.failure_reason = tx.gateway_response or tx.status
            others_open = any(
                a.status in ("created", "initialized") for a in order.attempts if a.id != attempt.id
            )
            if order.status == "awaiting_payment" and not others_open:
                order.status = "failed"
                order.failed_at = _now()
            audit_service.record(
                "payment.not_completed",
                "order",
                order.id,
                details={"reference": attempt.reference, "status": tx.status, "via": source},
            )
            db.session.commit()
            if first_failure:
                emails.send(
                    "payment_failed",
                    order.email,
                    {"name": order.customer.display_name, "order": order},
                    customer=order.customer,
                    order=order,
                )
                db.session.commit()
            return "failed"
        db.session.commit()
        return "pending"
    problems = []
    if tx.amount_minor != attempt.amount_minor or tx.amount_minor != order.total_minor:
        problems.append(f"amount {tx.amount_minor} does not match the expected {order.total_minor}")
    if tx.currency != order.currency or tx.currency != attempt.currency:
        problems.append(f"currency {tx.currency} does not match {order.currency}")
    if tx.mode != order.mode:
        problems.append(f"{tx.mode} payment for a {order.mode} order")
    if not tx.provider_id:
        problems.append("missing provider transaction id")
    if problems:
        return _mismatch(order, attempt, "; ".join(problems), source)

    transaction = PaymentTransaction(
        order_id=order.id,
        attempt_id=attempt.id,
        provider=order.provider,
        kind="charge",
        provider_id=tx.provider_id,
        reference=tx.reference,
        mode=tx.mode,
        status="success",
        amount_minor=tx.amount_minor,
        currency=tx.currency,
        channel=tx.channel,
        occurred_at=tx.paid_at,
    )
    try:
        with db.session.begin_nested():
            db.session.add(transaction)
            db.session.flush()
    except IntegrityError:
        pass  # already recorded by a concurrent request or an earlier webhook
    attempt.status = "succeeded"
    attempt.provider_status = "success"
    attempt.verified_at = _now()
    previous_status = order.status
    won = db.session.execute(
        update(Order)
        .where(Order.id == order.id, Order.status.in_(PAYABLE_STATUSES))
        .values(status="paid", paid_at=tx.paid_at or _now(), updated_at=_now())
    )
    if won.rowcount != 1:
        db.session.commit()
        db.session.refresh(order)
        _note_extra_payment(order, attempt, tx)
        return "already_paid"
    db.session.refresh(order)
    granted = ent_service.grant_for_order(order)
    receipt = _issue_receipt(order, tx)
    owned_before = _owned_elsewhere(order)
    if previous_status == "cancelled":
        order.needs_review = True
        order.review_reason = "Paid after the order had expired or been cancelled."
    if owned_before:
        order.needs_review = True
        order.review_reason = (
            "Customer already owned: " + ", ".join(owned_before) + " (consider a refund)."
        )
    audit_service.record(
        "order.paid",
        "order",
        order.id,
        details={
            "reference": tx.reference,
            "amount_minor": tx.amount_minor,
            "currency": tx.currency,
            "mode": tx.mode,
            "via": source,
            "entitlements": len(granted),
        },
    )
    db.session.commit()
    _send_paid_emails(order, receipt, tx)
    reprocess_deferred(order)
    return "paid"


def _note_extra_payment(order: Order, attempt: PaymentAttempt, tx: VerifiedTransaction) -> None:
    """A second successful charge for an order that is already paid: flag it for a refund."""
    others = db.session.scalar(
        select(func.count(PaymentTransaction.id)).where(
            PaymentTransaction.order_id == order.id,
            PaymentTransaction.kind == "charge",
            PaymentTransaction.provider_id != tx.provider_id,
        )
    )
    if others:
        order.needs_review = True
        order.review_reason = "More than one successful payment was received for this order."
        audit_service.record(
            "payment.duplicate_charge", "order", order.id, details={"reference": tx.reference}
        )
        db.session.commit()


def _owned_elsewhere(order: Order) -> list[str]:
    from ...models import Entitlement

    titles = []
    for item in order.items:
        other = db.session.scalar(
            select(Entitlement.id).where(
                Entitlement.customer_id == order.customer_id,
                Entitlement.product_id == item.product_id,
                Entitlement.status == "active",
                (Entitlement.order_id.is_(None)) | (Entitlement.order_id != order.id),
            )
        )
        if other:
            titles.append(item.title)
    return titles


def _mismatch(order: Order, attempt: PaymentAttempt, reason: str, source: str) -> str:
    attempt.status = "mismatch"
    attempt.failure_reason = reason[:300]
    attempt.verified_at = _now()
    order.needs_review = True
    order.review_reason = f"Payment did not match the order: {reason}"[:300]
    audit_service.record(
        "payment.mismatch",
        "order",
        order.id,
        details={"reference": attempt.reference, "reason": reason, "via": source},
    )
    db.session.commit()
    current_app.logger.warning("Payment mismatch on order %s: %s", order.number, reason)
    return "mismatch"


def _issue_receipt(order: Order, tx: VerifiedTransaction) -> Receipt:
    existing = db.session.scalar(select(Receipt).where(Receipt.order_id == order.id))
    if existing is not None:
        return existing
    from ..settings_service import get_values

    settings = get_values()
    receipt = Receipt(
        order_id=order.id,
        number=f"R-{order.number[4:]}",
        data={
            "seller": settings.get("site.name") or "Think Positive Always",
            "seller_email": settings.get("contact.email") or "",
            "order_number": order.number,
            "customer_email": order.email,
            "currency": order.currency,
            "items": [{"title": i.title, "amount_minor": i.line_total_minor} for i in order.items],
            "subtotal_minor": order.subtotal_minor,
            "tax_minor": order.tax_minor,
            "total_minor": order.total_minor,
            "provider": "Paystack",
            "reference": tx.reference,
            "channel": tx.channel,
            "paid_at": iso(tx.paid_at or order.paid_at),
            "mode": order.mode,
        },
    )
    db.session.add(receipt)
    db.session.flush()
    return receipt


def receipt_dict(receipt: Receipt | None) -> dict[str, Any] | None:
    if receipt is None:
        return None
    data = dict(receipt.data)
    currency = data["currency"]
    return {
        "number": receipt.number,
        "issued_at": iso(receipt.issued_at),
        **data,
        "items": [
            {"title": i["title"], "amount": money(i["amount_minor"], currency)}
            for i in data.get("items", [])
        ],
        "total": money(data["total_minor"], currency),
        "subtotal": money(data["subtotal_minor"], currency),
        "tax": money(data.get("tax_minor", 0), currency),
    }


def _send_paid_emails(order: Order, receipt: Receipt, tx: VerifiedTransaction) -> None:
    customer = order.customer
    ctx = {
        "name": customer.display_name,
        "order": order,
        "receipt_number": receipt.number,
        "reference": tx.reference,
        "paid_at": iso(order.paid_at),
    }
    emails.send("order_confirmation", order.email, ctx, customer=customer, order=order)
    emails.send("payment_received", order.email, ctx, customer=customer, order=order)
    products = [i.title for i in order.items]
    emails.send(
        "download_instructions",
        order.email,
        {"name": customer.display_name, "products": products},
        customer=customer,
        order=order,
    )
    db.session.commit()


def resend_receipt(order: Order, actor: User) -> str:
    receipt = db.session.scalar(select(Receipt).where(Receipt.order_id == order.id))
    if receipt is None:
        raise ConflictError("Receipts exist only for paid orders.")
    status = emails.send(
        "payment_received",
        order.email,
        {
            "name": order.customer.display_name,
            "order": order,
            "receipt_number": receipt.number,
            "reference": receipt.data.get("reference"),
            "paid_at": receipt.data.get("paid_at"),
        },
        customer=order.customer,
        order=order,
    )
    audit_service.record(
        "order.receipt_resent", "order", order.id, actor=actor, details={"delivery": status}
    )
    return status


def verify_order(order: Order, source: str) -> str:
    """Ask the provider about this order's open attempts (customer return page, staff)."""
    if order.status in ("paid", "partially_refunded", "refunded"):
        return "already_paid"
    provider = get_provider(order.provider)
    outcome = "pending"
    candidates = [
        a
        for a in reversed(order.attempts)
        if a.status in ("initialized", "created", "failed", "abandoned")
    ]
    for attempt in candidates[:5]:
        try:
            tx = provider.verify(attempt.reference)
        except ProviderError as exc:
            current_app.logger.info("Verification unavailable for %s: %s", attempt.reference, exc)
            continue
        result = apply_verified(order, attempt, tx, source)
        if result in ("paid", "already_paid", "mismatch"):
            return result
        if result == "failed":
            outcome = "failed"
    return outcome


# ---- webhooks ---------------------------------------------------------------------------


def handle_webhook(provider_name: str, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    provider = get_provider(provider_name)
    allowed_ips = current_app.config.get("PAYSTACK_WEBHOOK_IPS") or []
    if allowed_ips and request.remote_addr not in allowed_ips:
        audit_service.record(
            "payment.webhook_rejected", "payments", details={"reason": "source_not_allowed"}
        )
        db.session.commit()
        raise WebhookRejected("Webhook source not allowed.")
    if len(raw_body) > 512 * 1024 or not provider.verify_signature(raw_body, headers):
        audit_service.record(
            "payment.webhook_rejected", "payments", details={"reason": "invalid_signature"}
        )
        db.session.commit()
        raise WebhookRejected()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        assert isinstance(payload, dict)
    except (ValueError, AssertionError, UnicodeDecodeError):
        raise ValidationError("Malformed webhook payload.") from None
    event = provider.parse_event(payload)
    record = db.session.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider == provider.name, PaymentEvent.dedupe_key == event.dedupe_key
        )
    )
    if record is not None:
        record.received_count += 1
        if record.status not in ("error", "deferred", "received"):
            db.session.commit()
            return {"status": "duplicate"}
    else:
        record = PaymentEvent(
            provider=provider.name,
            dedupe_key=event.dedupe_key,
            event_type=event.event_type,
            reference=event.reference,
            mode=event.mode,
            payload=event.data,
        )
        try:
            with db.session.begin_nested():
                db.session.add(record)
                db.session.flush()
        except IntegrityError:  # concurrent delivery of the same event
            db.session.commit()
            return {"status": "duplicate"}
    db.session.commit()
    return process_event(record)


def process_event(record: PaymentEvent) -> dict[str, Any]:
    try:
        if record.event_type == "charge.success":
            status, result = _process_charge(record)
        elif record.event_type.startswith("refund."):
            status, result = _process_refund_event(record)
        else:
            status, result = "ignored", "Event type not used by this application."
    except ProviderError as exc:
        status, result = "error", f"Verification unavailable: {exc}"[:300]
    record.status = status
    record.result = result[:300]
    record.processed_at = _now()
    db.session.commit()
    if status == "error":
        # A non-2xx response makes Paystack retry the delivery later.
        raise ProviderUnavailable()
    return {"status": status}


class ProviderUnavailable(APIError):
    status_code = 503
    code = "provider_unavailable"
    message = "Payment provider temporarily unavailable; please retry."


def _attempt_for(reference: str | None) -> PaymentAttempt | None:
    if not reference:
        return None
    return db.session.scalar(select(PaymentAttempt).where(PaymentAttempt.reference == reference))


def _process_charge(record: PaymentEvent) -> tuple[str, str]:
    attempt = _attempt_for(record.reference)
    if attempt is None:
        return "ignored", "No order uses this payment reference."
    order = db.session.get(Order, attempt.order_id)
    record.order_id = order.id
    # Never trust the webhook body alone: confirm with the provider's verify API.
    tx = get_provider(order.provider).verify(attempt.reference)
    outcome = apply_verified(order, attempt, tx, "webhook")
    if outcome == "mismatch":
        return "rejected", "Verified payment did not match the order (flagged for review)."
    if outcome in ("paid", "already_paid"):
        return "processed", f"Order {order.number}: {outcome.replace('_', ' ')}."
    return "processed", f"Payment status: {tx.status}."


def _process_refund_event(record: PaymentEvent) -> tuple[str, str]:
    attempt = _attempt_for(record.reference)
    if attempt is None:
        return "ignored", "No order uses this payment reference."
    order = db.session.get(Order, attempt.order_id)
    record.order_id = order.id
    if order.status not in ("paid", "partially_refunded", "refunded"):
        return "deferred", "The payment has not been confirmed yet; will retry after it is."
    data = record.payload or {}
    provider_refund_id = str(data.get("id") or "")
    refund = None
    if provider_refund_id:
        refund = db.session.scalar(
            select(Refund).where(
                Refund.provider == order.provider, Refund.provider_refund_id == provider_refund_id
            )
        )
    if refund is None:
        refund = db.session.scalar(
            select(Refund)
            .where(Refund.order_id == order.id, Refund.status == "pending_provider")
            .order_by(Refund.created_at)
        )
    status = str(data.get("raw_status") or record.event_type.split(".", 1)[1]).lower()
    if refund is None:
        order.needs_review = True
        order.review_reason = "A refund was reported by Paystack that was not started here."
        audit_service.record(
            "refund.external",
            "order",
            order.id,
            details={"status": status, "id": provider_refund_id},
        )
        return "processed", "Refund not started from this admin; order flagged for review."
    if provider_refund_id and not refund.provider_refund_id:
        refund.provider_refund_id = provider_refund_id
    if record.event_type == "refund.processed" or status == "processed":
        _complete_refund(refund, None, "webhook")
        return "processed", f"Refund {refund.id} processed."
    if record.event_type == "refund.failed" or status == "failed":
        _fail_refund(refund, "Paystack reported the refund failed.", None)
        return "processed", f"Refund {refund.id} failed."
    return "processed", f"Refund {refund.id}: {status}."


def reprocess_deferred(order: Order) -> int:
    references = [a.reference for a in order.attempts]
    events = db.session.scalars(
        select(PaymentEvent).where(
            PaymentEvent.reference.in_(references), PaymentEvent.status == "deferred"
        )
    ).all()
    for event in events:
        try:
            process_event(event)
        except APIError:
            db.session.rollback()
    return len(events)


# ---- refunds ----------------------------------------------------------------------------


def refund_dict(refund: Refund) -> dict[str, Any]:
    return {
        "id": refund.id,
        "amount": money(refund.amount_minor, refund.currency),
        "status": refund.status,
        "method": refund.method,
        "provider_refund_id": refund.provider_refund_id,
        "reason": refund.reason,
        "revoke_access": refund.revoke_access,
        "failure_reason": refund.failure_reason,
        "downloads_at_request": refund.downloads_at_request,
        "requested_by": refund.requested_by.display_name if refund.requested_by else None,
        "created_at": iso(refund.created_at),
        "processed_at": iso(refund.processed_at),
    }


def refundable_minor(order: Order) -> int:
    pending = db.session.scalar(
        select(func.coalesce(func.sum(Refund.amount_minor), 0)).where(
            Refund.order_id == order.id, Refund.status.in_(("manual_review", "pending_provider"))
        )
    )
    return max(0, order.total_minor - order.refunded_minor - int(pending or 0))


def request_refund(order: Order, data: dict[str, Any], actor: User) -> Refund:
    allowed = {"amount_minor", "reason", "revoke_access", "idempotency_key"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValidationError(details={"_unknown": ["Unknown field(s)."]})
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not 16 <= len(key) <= 64:
        raise ValidationError(
            details={"idempotency_key": ["Missing request key; reload the page."]}
        )
    existing = db.session.scalar(
        select(Refund).where(Refund.order_id == order.id, Refund.idempotency_key == key)
    )
    if existing is not None:
        return existing
    if order.status not in ("paid", "partially_refunded"):
        raise ConflictError("Only paid orders can be refunded.")
    available = refundable_minor(order)
    amount = data.get("amount_minor", available)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ValidationError(details={"amount_minor": ["Enter an amount above zero."]})
    if amount > available:
        raise ValidationError(
            details={
                "amount_minor": [
                    f"At most {money(available, order.currency)['formatted']} "
                    "can still be refunded."
                ]
            }
        )
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValidationError(details={"reason": ["Give a reason (max 500 characters)."]})
    revoke = data.get("revoke_access", amount == available and order.refunded_minor == 0)
    if not isinstance(revoke, bool):
        raise ValidationError(details={"revoke_access": ["Must be true or false."]})
    settings = get_settings()
    provider = get_provider(order.provider)
    use_provider = bool(settings["payments.refunds_via_provider"]) and provider.mode == order.mode
    refund = Refund(
        order_id=order.id,
        amount_minor=amount,
        currency=order.currency,
        status="manual_review",
        method="provider" if use_provider else "manual",
        provider=order.provider,
        reason=reason.strip(),
        revoke_access=revoke,
        idempotency_key=key,
        downloads_at_request=ent_service.downloads_for_order(order),
        requested_by_id=actor.id,
    )
    db.session.add(refund)
    db.session.flush()
    audit_service.record(
        "refund.requested",
        "order",
        order.id,
        actor=actor,
        details={"refund_id": refund.id, "amount_minor": amount, "method": refund.method},
    )
    if use_provider:
        charge = db.session.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.order_id == order.id, PaymentTransaction.kind == "charge"
            )
        )
        if charge is None:
            refund.method = "manual"
            refund.failure_reason = "No verified charge on record; use the manual workflow."
            return refund
        db.session.commit()
        try:
            result = provider.refund(
                transaction_id=charge.provider_id,
                amount_minor=amount,
                currency=order.currency,
                note=f"Order {order.number}: {reason.strip()}"[:200],
            )
        except ProviderError as exc:
            _fail_refund(refund, str(exc), actor)
            db.session.commit()
            return refund
        refund.status = "pending_provider"
        refund.provider_refund_id = result.provider_refund_id or None
        if result.status == "processed":
            _complete_refund(refund, actor, "provider")
        elif result.status == "failed":
            _fail_refund(refund, "Paystack refused the refund.", actor)
    return refund


def complete_manual_refund(refund: Refund, data: dict[str, Any], actor: User) -> Refund:
    """Record that staff completed the refund in the provider dashboard (explicit confirmation)."""
    if refund.status != "manual_review":
        raise ConflictError("Only refunds awaiting manual processing can be recorded as completed.")
    reference = data.get("provider_reference")
    if not isinstance(reference, str) or not 3 <= len(reference.strip()) <= 100:
        raise ValidationError(
            details={
                "provider_reference": ["Enter the refund reference from the Paystack dashboard."]
            }
        )
    if data.get("confirm") is not True:
        raise ValidationError(
            details={
                "confirm": ["Confirm that the refund was completed in the Paystack dashboard."]
            }
        )
    refund.provider_refund_id = reference.strip()
    _complete_refund(refund, actor, "manual")
    return refund


def check_refund(refund: Refund, actor: User) -> Refund:
    if refund.status != "pending_provider" or not refund.provider_refund_id:
        raise ConflictError("This refund is not waiting for the provider.")
    order = db.session.get(Order, refund.order_id)
    result = get_provider(order.provider).fetch_refund(refund.provider_refund_id)
    if result.status == "processed":
        _complete_refund(refund, actor, "status_check")
    elif result.status == "failed":
        _fail_refund(refund, "Paystack reported the refund failed.", actor)
    return refund


def reject_refund(refund: Refund, reason: str, actor: User) -> Refund:
    if refund.status != "manual_review":
        raise ConflictError("Only refunds awaiting manual processing can be cancelled.")
    refund.status = "rejected"
    refund.failure_reason = (reason or "Cancelled by staff")[:300]
    refund.completed_by_id = actor.id
    audit_service.record(
        "refund.cancelled", "order", refund.order_id, actor=actor, details={"refund_id": refund.id}
    )
    return refund


def _fail_refund(refund: Refund, reason: str, actor: User | None) -> None:
    refund.status = "failed"
    refund.failure_reason = reason[:300]
    refund.processed_at = _now()
    audit_service.record(
        "refund.failed",
        "order",
        refund.order_id,
        actor=actor,
        details={"refund_id": refund.id, "reason": reason[:200]},
    )


def _complete_refund(refund: Refund, actor: User | None, via: str) -> None:
    won = db.session.execute(
        update(Refund)
        .where(Refund.id == refund.id, Refund.status.in_(("manual_review", "pending_provider")))
        .values(
            status="processed", processed_at=_now(), completed_by_id=actor.id if actor else None
        )
    )
    if won.rowcount != 1:
        return
    db.session.refresh(refund)
    order = db.session.get(Order, refund.order_id)
    new_total = min(order.total_minor, order.refunded_minor + refund.amount_minor)
    order.refunded_minor = new_total
    order.status = "refunded" if new_total >= order.total_minor else "partially_refunded"
    try:
        with db.session.begin_nested():
            db.session.add(
                PaymentTransaction(
                    order_id=order.id,
                    provider=order.provider,
                    kind="refund",
                    provider_id=refund.provider_refund_id or f"manual-{refund.id}",
                    reference=refund.provider_refund_id or f"manual-{refund.id}",
                    mode=order.mode,
                    status="processed",
                    amount_minor=refund.amount_minor,
                    currency=refund.currency,
                    occurred_at=_now(),
                )
            )
            db.session.flush()
    except IntegrityError:
        pass
    revoked = 0
    if refund.revoke_access:
        from ...models import Entitlement

        for ent in db.session.scalars(
            select(Entitlement).where(
                Entitlement.order_id == order.id, Entitlement.parent_id.is_(None)
            )
        ):
            revoked += ent_service.revoke(ent, f"Refunded (refund #{refund.id})", actor)
    audit_service.record(
        "refund.processed",
        "order",
        order.id,
        actor=actor,
        details={
            "refund_id": refund.id,
            "amount_minor": refund.amount_minor,
            "via": via,
            "revoked": revoked,
        },
    )
    db.session.commit()
    emails.send(
        "refund_confirmation",
        order.email,
        {
            "name": order.customer.display_name,
            "order": order,
            "amount_minor": refund.amount_minor,
            "revoked": bool(revoked),
        },
        customer=order.customer,
        order=order,
    )
    db.session.commit()


def get_refund(order: Order, refund_id: int) -> Refund:
    refund = db.session.get(Refund, refund_id)
    if refund is None or refund.order_id != order.id:
        raise NotFoundError("Refund not found.")
    return refund


# ---- maintenance ------------------------------------------------------------------------


def expire_orders(now: datetime | None = None) -> int:
    now = now or _now()
    rows = db.session.execute(
        update(Order)
        .where(
            Order.status == "awaiting_payment",
            Order.expires_at.is_not(None),
            Order.expires_at <= now,
        )
        .values(status="cancelled", cancelled_at=now, updated_at=now)
    )
    return rows.rowcount or 0


def event_dict(e: PaymentEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "provider": e.provider,
        "event_type": e.event_type,
        "reference": e.reference,
        "order_id": e.order_id,
        "mode": e.mode,
        "status": e.status,
        "result": e.result,
        "received_count": e.received_count,
        "received_at": iso(e.received_at),
        "processed_at": iso(e.processed_at),
        "payload": sanitize(e.payload) | {"raw_status": (e.payload or {}).get("raw_status")},
    }
