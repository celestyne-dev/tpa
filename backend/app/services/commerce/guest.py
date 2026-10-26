"""Guest checkout: buying without an account.

A guest order belongs to a *buyer record* for the typed email: an ordinary
``Customer`` row with status ``guest`` (no password, can't sign in) or, if the address
already has an account, that account. Guest checkout never reads the record's
library, profile or status for the response, so it reveals nothing about whether an
address is registered. Pricing, idempotency, Paystack verification and fulfilment are
the same code paths as for signed-in customers (``checkout`` and ``payments``).

Two kinds of access, neither of them a permanent link:

- **Order token.** Returned once when the order is created and kept by the buyer's
  browser (session storage). Only its hash is stored. It opens that one order: status,
  payment retry/cancel and, for a limited time after payment, downloads.
- **Guest access link.** Emailed after payment and on request (``/purchases``). A
  ``guest_access`` customer token (hashed, expiring, replaced by each new link) that
  opens the guest-checkout purchases made with that email address.

Downloads go through the usual short-lived, few-use ``DownloadGrant`` (marked
``guest`` because there is no session to match) and are re-checked when served, so
refunds and revocations apply immediately.

Purchases are claimed by registering with the same email and confirming it: guest
orders and their entitlements appear in an account only when ``email_verified_at`` is
set (see ``entitlements.account_scope`` and ``checkout.customer_orders``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import Customer, CustomerToken, Entitlement, Order
from ...utils.errors import APIError, NotFoundError, ValidationError
from ...utils.validation import is_email, plain_text_problem
from .. import audit_service
from ..serializers import iso
from . import checkout, downloads, emails
from . import entitlements as ent_service
from .customers import InvalidTokenError, _issue_token, normalise_email

GUEST_ACCESS_PURPOSE = "guest_access"
# Records that may hold guest purchases and use guest access links.
ACCESS_STATUSES = ("guest", "active")


class GuestCheckoutUnavailable(APIError):
    status_code = 409
    code = "guest_checkout_unavailable"
    message = "We can't take this order online. Please contact us and we'll help."


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_email(value: Any) -> str:
    email = normalise_email(value if isinstance(value, str) else "")
    if not is_email(email):
        raise ValidationError(details={"email": ["Enter a valid email address."]})
    return email


def _clean_name(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(details={"name": ["Must be text."]})
    value = " ".join(value.split())
    if len(value) > 120:
        raise ValidationError(details={"name": ["Use at most 120 characters."]})
    if value and (problem := plain_text_problem(value)):
        raise ValidationError(details={"name": [problem]})
    return value


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'•' * 3}@{domain}"


def buyer_for_email(email: str, name: str = "") -> Customer:
    """The record that guest purchases for ``email`` belong to (created if needed)."""
    customer = db.session.scalar(select(Customer).where(Customer.email == email))
    if customer is None:
        customer = Customer(
            public_id=secrets.token_hex(8),
            email=email,
            display_name=name,
            password_hash=None,
            status="guest",
        )
        try:
            with db.session.begin_nested():
                db.session.add(customer)
                db.session.flush()
        except IntegrityError:  # a concurrent checkout created it first
            customer = db.session.scalar(select(Customer).where(Customer.email == email))
            if customer is None:
                raise
        else:
            audit_service.record("customer.guest_created", "customer", customer.id)
    if customer.status not in ACCESS_STATUSES:
        # Disabled by an administrator. The message is the one any blocked order gets.
        raise GuestCheckoutUnavailable()
    if customer.status == "guest" and name and not customer.display_name:
        customer.display_name = name
    return customer


# ---- orders -----------------------------------------------------------------------------


def create_order(data: dict[str, Any]) -> tuple[Order, str | None, str]:
    """Create (or resume) a guest order. Returns (order, authorization_url, order_token)."""
    email = _clean_email(data.get("email"))
    name = _clean_name(data.get("name"))
    allowed, reason = checkout.checkout_available_for(None)
    if not allowed:
        raise checkout.CheckoutClosedError(reason)
    buyer = buyer_for_email(email, name)
    token = secrets.token_urlsafe(32)
    order, url = checkout.create_order(buyer, data, guest=True, guest_token_hash=_hash(token))
    if order.guest_token_hash != _hash(token):
        # Resumed with the same checkout key (a refresh or double submit): the browser
        # that holds the key gets a fresh token and the previous one stops working.
        order.guest_token_hash = _hash(token)
        db.session.commit()
    return order, url, token


def guest_order(public_id: str, token: Any) -> Order:
    """The guest order the token opens. Same answer for every kind of mismatch."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise NotFoundError("Order not found.")
    order = db.session.scalar(select(Order).where(Order.public_id == public_id))
    if (
        order is None
        or not order.is_guest
        or not order.guest_token_hash
        or not hmac.compare_digest(order.guest_token_hash, _hash(token))
    ):
        raise NotFoundError("Order not found.")
    hours = current_app.config["GUEST_ORDER_ACCESS_HOURS"]
    if order.created_at + timedelta(hours=hours) <= _now():
        raise NotFoundError("Order not found.")
    return order


def downloads_open(order: Order) -> bool:
    """Downloads straight from the order page are available for a while after payment;
    after that the emailed access link (or an account) is the way in."""
    if order.status not in ("paid", "partially_refunded") or order.paid_at is None:
        return False
    hours = current_app.config["GUEST_ORDER_DOWNLOAD_HOURS"]
    return order.paid_at + timedelta(hours=hours) > _now()


def order_dict(order: Order) -> dict[str, Any]:
    data = checkout.order_public_dict(order)
    data["guest"] = True
    data["email_hint"] = mask_email(order.email)
    data["downloads_available"] = downloads_open(order)
    data["library"] = order_library(order) if downloads_open(order) else []
    return data


def order_library(order: Order) -> list[dict[str, Any]]:
    customer = db.session.get(Customer, order.customer_id)
    return ent_service.library(customer, scope=Entitlement.order_id == order.id)


def authorize_order_download(order: Order, entitlement_id: int, version_id: int) -> dict:
    entitlement = db.session.get(Entitlement, entitlement_id)
    if not downloads_open(order) or entitlement is None or entitlement.order_id != order.id:
        raise NotFoundError("This item is not in your library.")
    customer = db.session.get(Customer, order.customer_id)
    return downloads.authorize_guest(customer, entitlement_id, version_id)


# ---- access links -----------------------------------------------------------------------


def _has_guest_purchases(customer: Customer) -> bool:
    return (
        db.session.scalar(
            select(Order.id)
            .where(
                Order.customer_id == customer.id,
                Order.is_guest.is_(True),
                Order.status.in_(("paid", "partially_refunded", "refunded")),
            )
            .limit(1)
        )
        is not None
    )


def issue_access_link(customer: Customer, *, reason: str) -> tuple[str, int]:
    """A new access link; earlier ones stop working. Returns (url, lifetime in hours)."""
    hours = current_app.config["GUEST_ACCESS_TTL_HOURS"]
    token = _issue_token(customer, GUEST_ACCESS_PURPOSE, timedelta(hours=hours))
    audit_service.record(
        "customer.guest_access_issued", "customer", customer.id, details={"reason": reason}
    )
    return f"{current_app.config['SITE_URL']}/purchases#token={token}", hours


def send_access_link(customer: Customer, *, reason: str) -> str:
    link, hours = issue_access_link(customer, reason=reason)
    return emails.send(
        "guest_access",
        customer.email,
        {"name": customer.display_name, "access_link": link, "hours": hours},
        customer=customer,
    )


def request_access(email: Any) -> None:
    """Recovery: email a fresh access link if this address has guest purchases.

    Silent otherwise; the API answers the same way for every address.
    """
    address = normalise_email(email if isinstance(email, str) else "")
    if not is_email(address):
        raise ValidationError(details={"email": ["Enter a valid email address."]})
    customer = db.session.scalar(select(Customer).where(Customer.email == address))
    if customer is None or customer.status not in ACCESS_STATUSES:
        return
    if _has_guest_purchases(customer):
        send_access_link(customer, reason="requested")


def access_customer(token: Any) -> Customer:
    """The buyer an access link belongs to. The link stays usable until it expires or a
    newer one is issued."""
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise InvalidTokenError()
    record = db.session.scalar(
        select(CustomerToken).where(CustomerToken.token_hash == _hash(token))
    )
    if (
        record is None
        or record.purpose != GUEST_ACCESS_PURPOSE
        or record.used_at is not None
        or record.expires_at <= _now()
    ):
        raise InvalidTokenError()
    customer = db.session.get(Customer, record.customer_id)
    if customer is None or customer.status not in ACCESS_STATUSES:
        raise InvalidTokenError()
    return customer


def purchases(customer: Customer) -> dict[str, Any]:
    orders = db.session.scalars(
        select(Order)
        .where(
            Order.customer_id == customer.id,
            Order.is_guest.is_(True),
            Order.status.in_(("paid", "partially_refunded", "refunded")),
        )
        .order_by(Order.created_at.desc())
    ).all()
    return {
        "email_hint": mask_email(customer.email),
        "orders": [
            {
                "number": o.number,
                "status": o.status,
                "total": checkout.order_public_dict(o)["total"],
                "paid_at": iso(o.paid_at),
                "items": [i.title for i in o.items],
            }
            for o in orders
        ],
        "library": ent_service.library(customer, scope=ent_service.guest_scope(customer)),
    }
