"""Cart validation and checkout (order creation + hosted payment initialisation).

The client is never the authority for prices: every quote and every order is
computed on the server from ``product_prices``. A checkout request also carries
the total the shopper saw; if it differs from the server's total (price change
or tampering) the order is refused with the fresh quote, so customers are only
ever charged the amount and currency they were shown.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...commerce.currency import CURRENCIES, money
from ...extensions import db
from ...models import Customer, Entitlement, Order, OrderItem, PaymentAttempt, Product
from ...payments.base import ProviderError
from ...payments.config import (
    checkout_available_for,
    checkout_currencies,
    effective_mode,
    get_settings,
    public_status,
)
from ...payments.paystack import get_provider
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import catalogue
from . import entitlements as ent_service

MAX_CART_ITEMS = 20
_KEY = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class CheckoutClosedError(APIError):
    status_code = 409
    code = "checkout_closed"
    message = "Checkout is not open yet. No payments are being taken."


class PaymentUnavailableError(APIError):
    status_code = 502
    code = "payment_unavailable"
    message = "We couldn't start the payment. You have not been charged. Please try again."


def _now() -> datetime:
    return datetime.now(UTC)


def owned_product_ids(customer: Customer | None) -> set[int]:
    if customer is None:
        return set()
    return set(
        db.session.scalars(
            select(Entitlement.product_id).where(
                ent_service.account_scope(customer),
                Entitlement.status == "active",
                ent_service.not_expired(),
            )
        )
    )


def _parse_items(raw: Any) -> list[str]:
    if not isinstance(raw, list) or len(raw) > MAX_CART_ITEMS:
        raise ValidationError(details={"items": [f"Send up to {MAX_CART_ITEMS} products."]})
    ids = []
    for item in raw:
        value = item.get("product_id") if isinstance(item, dict) else item
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{16}", value):
            raise ValidationError(details={"items": ["Unknown product in the cart."]})
        ids.append(value)
    return list(dict.fromkeys(ids))  # duplicates collapse into one licence


def quote(raw_items: Any, currency: Any, customer: Customer | None) -> dict[str, Any]:
    ids = _parse_items(raw_items)
    currency = str(currency or "").upper()
    if currency not in CURRENCIES:
        raise ValidationError(details={"currency": ["Choose a supported currency."]})
    products = (
        {
            p.public_id: p
            for p in db.session.scalars(select(Product).where(Product.public_id.in_(ids)))
        }
        if ids
        else {}
    )
    owned = owned_product_ids(customer)
    bundle_children: dict[int, str] = {}
    for public_id in ids:
        product = products.get(public_id)
        if product is not None and product.is_bundle:
            for child in catalogue.bundle_products(product):
                bundle_children[child.id] = product.title
    lines, warnings = [], []
    subtotal = 0
    checkout_ok = currency in checkout_currencies()
    for public_id in ids:
        product = products.get(public_id)
        doc = (product.published_snapshot or {}) if product else {}
        line: dict[str, Any] = {
            "product_id": public_id,
            "title": doc.get("title") or (product.title if product else "Unavailable product"),
            "slug": product.published_slug if product and product.status == "published" else None,
            "type": product.product_type if product else None,
            "cover_theme": doc.get("cover_theme") or "sage",
            "unit": None,
            "compare_at": None,
            "available": False,
            "problem": None,
        }
        lines.append(line)
        if product is None or product.status != "published" or not doc:
            line["problem"] = "This product is no longer available."
            continue
        state = catalogue.readiness(product)
        if not state["purchasable"]:
            line["problem"] = (
                "Coming soon — not available to buy yet."
                if product.sales_status == "coming_soon"
                else "This product can't be bought right now."
            )
            continue
        if product.pricing_model == "free":
            line["problem"] = "This resource is free — get it from its page instead."
            continue
        if product.id in owned:
            line["problem"] = "Already in your library."
            continue
        if product.id in bundle_children:
            line["problem"] = f"Included in “{bundle_children[product.id]}” in your cart."
            continue
        price = state["prices"].get(currency)
        if price is None:
            line["problem"] = f"Not sold in {currency}."
            continue
        line["unit"] = money(price["amount_minor"], currency)
        line["compare_at"] = (
            money(price["compare_at_minor"], currency) if price["compare_at_minor"] else None
        )
        line["price_id"] = price["price_id"]
        line["available"] = True
        subtotal += price["amount_minor"]
        if product.is_bundle and product.id not in owned:
            already = [c.title for c in catalogue.bundle_products(product) if c.id in owned]
            if already:
                warnings.append(
                    f"You already own {', '.join(already)}, which is included in “{line['title']}”."
                )
    if not checkout_ok:
        warnings.append(f"Payment in {currency} is not available.")
    available_lines = [line for line in lines if line["available"]]
    return {
        "currency": currency,
        "lines": lines,
        "subtotal": money(subtotal, currency),
        "tax": None,
        "total": money(subtotal, currency),
        "tax_note": "Prices include any applicable taxes; no tax is added at checkout.",
        "can_checkout": bool(available_lines)
        and len(available_lines) == len(lines)
        and checkout_ok,
        "warnings": warnings,
        "checkout": public_status(customer),
    }


def _cart_hash(product_ids: list[str], currency: str) -> str:
    return hashlib.sha256(json.dumps([sorted(product_ids), currency]).encode()).hexdigest()


def _new_number() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return f"TPA-{_now():%y%m%d}-" + "".join(secrets.choice(alphabet) for _ in range(6))


def order_public_dict(order: Order) -> dict[str, Any]:
    latest = order.attempts[-1] if order.attempts else None
    return {
        "id": order.public_id,
        "number": order.number,
        "status": order.status,
        "currency": order.currency,
        "subtotal": money(order.subtotal_minor, order.currency),
        "tax": money(order.tax_minor, order.currency),
        "total": money(order.total_minor, order.currency),
        "refunded": money(order.refunded_minor, order.currency),
        "test_mode": order.mode == "test",
        "created_at": iso(order.created_at),
        "paid_at": iso(order.paid_at),
        "expires_at": iso(order.expires_at),
        "items": [
            {
                "product_id": i.product_public_id,
                "title": i.title,
                "type": i.product_type,
                "slug": i.slug,
                "amount": money(i.line_total_minor, i.currency),
                "includes": [c.get("title") for c in i.bundle_contents or []],
            }
            for i in order.items
        ],
        "payment": {
            "provider": "Paystack",
            "status": latest.status if latest else None,
            "reference": latest.reference if latest else None,
            "failure_reason": latest.failure_reason if latest else "",
        },
        "can_retry": order.status in ("awaiting_payment", "failed")
        and (order.expires_at is None or order.expires_at > _now()),
    }


def create_order(
    customer: Customer,
    data: dict[str, Any],
    *,
    guest: bool = False,
    guest_token_hash: str | None = None,
) -> tuple[Order, str | None]:
    """Validate the cart on the server, create the order, then start the hosted payment.

    Guest checkout (``guest=True``) uses the buyer record for the typed email. It never looks
    at that record's library or status, so it can't reveal anything about an existing account.
    """
    allowed, reason = checkout_available_for(None if guest else customer)
    if not allowed:
        raise CheckoutClosedError(reason)
    if not guest and customer.email_verified_at is None:
        raise ConflictError(
            "Please confirm your email address before paying, so your receipt and downloads "
            "reach you.",
            details={"code": "email_unverified"},
        )
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not _KEY.match(key):
        raise ValidationError(
            details={"idempotency_key": ["Missing checkout key; refresh the page."]}
        )
    if data.get("accept_terms") is not True:
        raise ValidationError(details={"accept_terms": ["Please accept the terms to continue."]})
    product_ids = _parse_items(data.get("items"))
    currency = str(data.get("currency") or "").upper()
    if currency not in checkout_currencies():
        raise ValidationError(
            details={"currency": [f"Payment in {currency or 'this currency'} is not available."]}
        )
    cart_hash = _cart_hash(product_ids, currency)

    existing = db.session.scalar(
        select(Order).where(Order.customer_id == customer.id, Order.idempotency_key == key)
    )
    if existing is not None:
        if existing.is_guest != guest:
            raise ConflictError(
                "This checkout was already used. Refresh the page.",
                details={"code": "idempotency_conflict"},
            )
        return _resume(existing, cart_hash)

    q = quote(product_ids, currency, None if guest else customer)
    if not q["can_checkout"]:
        raise ConflictError(
            "Your cart has changed. Please review it before paying.",
            details={"code": "cart_changed", "quote": q},
        )
    expected = data.get("expected_total_minor")
    if (
        not isinstance(expected, int)
        or isinstance(expected, bool)
        or expected != q["total"]["amount_minor"]
    ):
        raise ConflictError(
            "The price has changed since you opened your cart. Please review the new total.",
            details={"code": "price_changed", "quote": q},
        )
    settings = get_settings()
    mode = effective_mode()
    products = {
        p.public_id: p
        for p in db.session.scalars(select(Product).where(Product.public_id.in_(product_ids)))
    }
    order = Order(
        number=_new_number(),
        public_id=secrets.token_hex(16),
        customer_id=customer.id,
        email=customer.email,
        status="awaiting_payment",
        currency=currency,
        subtotal_minor=q["subtotal"]["amount_minor"],
        tax_minor=0,
        discount_minor=0,
        total_minor=q["total"]["amount_minor"],
        provider="paystack",
        mode=mode,
        idempotency_key=key,
        cart_hash=cart_hash,
        terms_version=settings["payments.terms_version"] or "",
        terms_accepted_at=_now(),
        expires_at=_now() + timedelta(minutes=settings["payments.order_expiry_minutes"]),
        ip_address=request.remote_addr,
        is_guest=guest,
        guest_token_hash=guest_token_hash,
    )
    for line in q["lines"]:
        product = products[line["product_id"]]
        order.items.append(
            OrderItem(
                product_id=product.id,
                product_public_id=product.public_id,
                title=line["title"],
                product_type=product.product_type,
                slug=product.published_slug or product.slug,
                currency=currency,
                unit_amount_minor=line["unit"]["amount_minor"],
                compare_at_minor=line["compare_at"]["amount_minor"] if line["compare_at"] else None,
                quantity=1,
                line_total_minor=line["unit"]["amount_minor"],
                price_id=line.get("price_id"),
                bundle_contents=[
                    {
                        "product_id": c.id,
                        "title": (c.published_snapshot or {}).get("title") or c.title,
                    }
                    for c in catalogue.bundle_products(product)
                ]
                if product.is_bundle
                else [],
            )
        )
    for _ in range(5):
        try:
            with db.session.begin_nested():
                db.session.add(order)
                db.session.flush()
            break
        except IntegrityError:
            dup = db.session.scalar(
                select(Order).where(Order.customer_id == customer.id, Order.idempotency_key == key)
            )
            if dup is not None:  # a concurrent identical request won
                return _resume(dup, cart_hash)
            order.number = _new_number()
    else:  # pragma: no cover - astronomically unlikely
        raise ConflictError("Please try again.")
    audit_service.record(
        "order.created",
        "order",
        order.id,
        details={
            "number": order.number,
            "total_minor": order.total_minor,
            "currency": currency,
            "mode": mode,
            "customer_id": customer.id,
            "guest": guest,
        },
    )
    db.session.commit()
    url = start_payment(order)
    return order, url


def _resume(order: Order, cart_hash: str) -> tuple[Order, str | None]:
    if order.cart_hash != cart_hash:
        raise ConflictError(
            "This checkout was already used for a different cart. Refresh the page.",
            details={"code": "idempotency_conflict"},
        )
    latest = order.attempts[-1] if order.attempts else None
    if order.status == "awaiting_payment" and latest is not None and latest.status == "initialized":
        return order, latest.authorization_url
    if order.status == "awaiting_payment" and (latest is None or latest.status == "failed"):
        return order, start_payment(order)
    return order, None


def start_payment(order: Order) -> str:
    """Create a payment attempt and the provider's hosted checkout session."""
    if order.status not in ("awaiting_payment", "failed"):
        raise ConflictError("This order can no longer be paid.")
    if order.expires_at and order.expires_at <= _now():
        raise ConflictError("This order has expired. Please start a new checkout.")
    if effective_mode() != order.mode:
        raise CheckoutClosedError()
    settings = get_settings()
    attempt = PaymentAttempt(
        order_id=order.id,
        provider=order.provider,
        mode=order.mode,
        reference=f"{order.number}-{len(order.attempts) + 1}-{secrets.token_hex(3)}",
        status="created",
        amount_minor=order.total_minor,
        currency=order.currency,
    )
    db.session.add(attempt)
    order.status = "awaiting_payment"
    db.session.commit()
    site = current_app.config["SITE_URL"]
    # Guest orders come back to the same page, which then uses the browser's order token.
    back = f"{site}/checkout/complete?order={order.public_id}"
    if order.is_guest:
        back += "&guest=1"
    try:
        session = get_provider(order.provider).initialize(
            email=order.email,
            amount_minor=order.total_minor,
            currency=order.currency,
            reference=attempt.reference,
            callback_url=back,
            channels=list(settings["payments.channels"] or []),
            metadata={
                "order_number": order.number,
                "cancel_action": f"{back}&cancelled=1",
            },
        )
    except ProviderError as exc:
        attempt.status = "failed"
        attempt.failure_reason = str(exc)[:300]
        audit_service.record(
            "payment.init_failed", "order", order.id, details={"reason": str(exc)[:200]}
        )
        db.session.commit()
        raise PaymentUnavailableError(details={"order": order.public_id}) from None
    attempt.status = "initialized"
    attempt.authorization_url = session.authorization_url
    attempt.access_code = session.access_code
    audit_service.record(
        "payment.initialized", "order", order.id, details={"reference": attempt.reference}
    )
    db.session.commit()
    return session.authorization_url


def guest_visible(customer: Customer) -> bool:
    """Guest-checkout purchases show in an account only once its email is confirmed (so
    nobody can register someone else's address and see what they bought)."""
    return customer.email_verified_at is not None


def customer_order(customer: Customer, public_id: str) -> Order:
    order = db.session.scalar(select(Order).where(Order.public_id == public_id))
    if order is None or order.customer_id != customer.id:
        raise NotFoundError("Order not found.")
    if order.is_guest and not guest_visible(customer):
        raise NotFoundError("Order not found.")
    return order


def customer_orders(customer: Customer) -> list[Order]:
    query = select(Order).where(Order.customer_id == customer.id)
    if not guest_visible(customer):
        query = query.where(Order.is_guest.is_(False))
    return list(db.session.scalars(query.order_by(Order.created_at.desc())))


def cancel_unpaid(order: Order, actor_label: str, actor=None) -> Order:
    if order.status not in ("pending", "awaiting_payment", "failed"):
        raise ConflictError("Only unpaid orders can be cancelled.")
    order.status = "cancelled"
    order.cancelled_at = _now()
    audit_service.record(
        "order.cancelled", "order", order.id, actor=actor, details={"by": actor_label}
    )
    return order
