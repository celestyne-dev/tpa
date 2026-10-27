"""Customer accounts: registration, sign-in, email verification, password reset,
profile, data export and deletion requests.

Customers can never become administrators: they live in their own table and
registration never touches roles. Messages for unknown emails are generic so
the API does not reveal who has an account.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import select, update

from ...auth.customer_session import revoke_all
from ...auth.passwords import hash_password, password_problems, verify_password
from ...extensions import db
from ...models import (
    Customer,
    CustomerToken,
    DownloadEvent,
    Entitlement,
    Order,
)
from ...utils.errors import APIError, AuthenticationError, ConflictError, ValidationError
from ...utils.validation import is_email, plain_text_problem
from .. import audit_service
from ..serializers import iso
from . import emails

GENERIC_LOGIN_ERROR = "The email or password is incorrect."


class InvalidTokenError(APIError):
    status_code = 400
    code = "link_invalid"
    message = "This link is invalid, has already been used, or has expired."


def _now() -> datetime:
    return datetime.now(UTC)


def normalise_email(value: str) -> str:
    return (value or "").strip().lower()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def profile(customer: Customer) -> dict[str, Any]:
    return {
        "id": customer.public_id,
        "email": customer.email,
        "display_name": customer.display_name,
        "email_verified": customer.email_verified_at is not None,
        "created_at": iso(customer.created_at),
        "status": customer.status,
        "deletion_requested_at": iso(customer.deletion_requested_at),
    }


def _clean_name(value: Any, errors: dict, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors["display_name"] = ["Must be text."]
        return ""
    value = " ".join(value.split())
    if required and not value:
        errors["display_name"] = ["Enter your name."]
    elif len(value) > 120:
        errors["display_name"] = ["Use at most 120 characters."]
    elif value and (problem := plain_text_problem(value)):
        errors["display_name"] = [problem]
    return value


def register(data: dict[str, Any]) -> tuple[Customer | None, bool]:
    """Create an account. Returns (customer, created).

    If the email is already registered nothing is changed and the existing owner
    is told by email (no account enumeration through this endpoint).

    If the email only has guest-checkout purchases, that buyer record becomes the
    account, exactly as a new sign-up would look (signed in, unverified). Its guest
    purchases appear in the account only after the address is confirmed, so registering
    someone else's email never reveals or hands over what they bought.
    """
    errors: dict[str, Any] = {}
    email = normalise_email(data.get("email") if isinstance(data.get("email"), str) else "")
    if not is_email(email):
        errors["email"] = ["Enter a valid email address."]
    password = data.get("password")
    if not isinstance(password, str):
        errors["password"] = ["Choose a password."]
        password = ""
    else:
        problems = password_problems(password, email=email)
        if problems:
            errors["password"] = problems
    confirm = data.get("password_confirm")
    if confirm is not None and confirm != password:
        errors["password_confirm"] = ["The passwords don't match."]
    name = _clean_name(data.get("display_name"), errors, required=True)
    opt_in = data.get("newsletter_opt_in", False)
    if not isinstance(opt_in, bool):
        errors["newsletter_opt_in"] = ["Must be true or false."]
    if data.get("accept_terms") is not True:
        errors["accept_terms"] = ["Please accept the terms and privacy policy."]
    if errors:
        raise ValidationError("Please check the highlighted fields.", details=errors)
    existing = db.session.scalar(select(Customer).where(Customer.email == email))
    if existing is not None and existing.status == "guest":
        existing.status = "active"
        existing.display_name = name
        existing.password_hash = hash_password(password)
        existing.email_verified_at = None
        audit_service.record("customer.guest_converted", "customer", existing.id)
        send_verification(existing, claims_purchases=True)
        return existing, True
    if existing is not None:
        if existing.status == "active":
            send_password_reset(existing, reason="already_registered")
        return existing, False
    customer = Customer(
        public_id=secrets.token_hex(8),
        email=email,
        display_name=name,
        password_hash=hash_password(password),
    )
    db.session.add(customer)
    db.session.flush()
    audit_service.record("customer.registered", "customer", customer.id)
    send_verification(customer)
    return customer, True


def authenticate(email: str, password: str) -> Customer | None:
    customer = db.session.scalar(select(Customer).where(Customer.email == normalise_email(email)))
    if customer is None or not customer.is_active:
        verify_password(None, password or "")
        return None
    if not verify_password(customer.password_hash, password or ""):
        return None
    customer.last_login_at = _now()
    return customer


# ---- tokens -----------------------------------------------------------------------------


def _issue_token(customer: Customer, purpose: str, ttl: timedelta) -> str:
    db.session.execute(
        update(CustomerToken)
        .where(
            CustomerToken.customer_id == customer.id,
            CustomerToken.purpose == purpose,
            CustomerToken.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    token = secrets.token_urlsafe(32)
    db.session.add(
        CustomerToken(
            customer_id=customer.id,
            purpose=purpose,
            token_hash=_hash(token),
            expires_at=_now() + ttl,
        )
    )
    return token


def _redeem(token: str, purpose: str) -> Customer:
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise InvalidTokenError()
    record = db.session.scalar(
        select(CustomerToken).where(CustomerToken.token_hash == _hash(token))
    )
    if record is None or record.purpose != purpose:
        raise InvalidTokenError()
    result = db.session.execute(
        update(CustomerToken)
        .where(
            CustomerToken.id == record.id,
            CustomerToken.used_at.is_(None),
            CustomerToken.expires_at > _now(),
        )
        .values(used_at=_now())
    )
    if result.rowcount != 1:
        raise InvalidTokenError()
    customer = db.session.get(Customer, record.customer_id)
    if customer is None or not customer.is_active:
        raise InvalidTokenError()
    return customer


def send_verification(customer: Customer, *, claims_purchases: bool = False) -> str:
    hours = current_app.config["CUSTOMER_VERIFY_TTL_HOURS"]
    token = _issue_token(customer, "verify_email", timedelta(hours=hours))
    link = f"{current_app.config['SITE_URL']}/verify-email#token={token}"
    return emails.send(
        "verify_email",
        customer.email,
        {
            "name": customer.display_name,
            "link": link,
            "hours": hours,
            "claims_purchases": claims_purchases,
        },
        customer=customer,
    )


def verify_email(token: str) -> Customer:
    customer = _redeem(token, "verify_email")
    if customer.email_verified_at is None:
        customer.email_verified_at = _now()
        audit_service.record("customer.email_verified", "customer", customer.id)
    return customer


def send_password_reset(customer: Customer, reason: str = "requested") -> str:
    minutes = current_app.config["CUSTOMER_RESET_TTL_MINUTES"]
    token = _issue_token(customer, "password_reset", timedelta(minutes=minutes))
    link = f"{current_app.config['SITE_URL']}/reset-password#token={token}"
    audit_service.record(
        "customer.password_reset_sent", "customer", customer.id, details={"reason": reason}
    )
    return emails.send(
        "password_reset",
        customer.email,
        {"name": customer.display_name, "link": link, "minutes": minutes},
        customer=customer,
    )


def request_verification(email: str) -> None:
    """Resend a confirmation link to an unverified account. Silent for unknown, verified or
    inactive addresses, so the public response never reveals who has an account."""
    customer = db.session.scalar(select(Customer).where(Customer.email == normalise_email(email)))
    if customer is not None and customer.is_active and customer.email_verified_at is None:
        send_verification(customer)


def subscribe_to_newsletter(email: str, name: str, data: dict[str, Any], ip: str | None) -> str:
    """Explicit, optional newsletter opt-in from the account forms. Uses the same double
    opt-in signup as every other form (a confirmation email decides). Returns a public
    status that is identical whether or not the address already has an account."""
    from ..newsletter import subscribers
    from ..newsletter.config import signup_open

    if not signup_open():
        return "unavailable"
    subscribers.subscribe(
        {
            "email": email,
            "first_name": name.split(" ")[0] if name else "",
            "consent": True,
            "consent_version": data.get("newsletter_consent_version"),
            "source": "account",
        },
        ip=ip,
    )
    return "check_email"


def request_password_reset(email: str) -> None:
    customer = db.session.scalar(select(Customer).where(Customer.email == normalise_email(email)))
    if customer is not None and customer.is_active:
        send_password_reset(customer)


def complete_password_reset(token: str, password: str) -> Customer:
    customer = _redeem(token, "password_reset")
    problems = password_problems(
        password if isinstance(password, str) else "", email=customer.email
    )
    if problems:
        db.session.rollback()
        raise ValidationError(details={"password": problems})
    customer.password_hash = hash_password(password)
    # A reset link proves control of the inbox, so the address counts as verified.
    customer.email_verified_at = customer.email_verified_at or _now()
    revoke_all(customer)
    audit_service.record("customer.password_reset", "customer", customer.id)
    return customer


def change_password(customer: Customer, current: str, new: str, keep_session_id: int) -> None:
    if not verify_password(customer.password_hash, current or ""):
        raise AuthenticationError("Your current password is incorrect.")
    problems = password_problems(new if isinstance(new, str) else "", email=customer.email)
    if problems:
        raise ValidationError(details={"new_password": problems})
    customer.password_hash = hash_password(new)
    revoke_all(customer, except_id=keep_session_id)
    audit_service.record("customer.password_changed", "customer", customer.id)


def update_profile(customer: Customer, data: dict[str, Any]) -> Customer:
    errors: dict[str, Any] = {}
    if set(data) - {"display_name"}:
        errors["_unknown"] = ["Only your name can be changed here."]
    name = _clean_name(data.get("display_name"), errors, required=True)
    if errors:
        raise ValidationError(details=errors)
    customer.display_name = name
    return customer


# ---- privacy ----------------------------------------------------------------------------


def export_data(customer: Customer, password: str) -> dict[str, Any]:
    """Everything stored about the customer, for data-portability requests. Requires the
    current password (re-authentication) because the export contains personal data."""
    if not verify_password(customer.password_hash, password or ""):
        raise AuthenticationError("Your password is incorrect.")
    from .checkout import customer_orders
    from .entitlements import account_scope

    audit_service.record("customer.data_exported", "customer", customer.id)
    # Guest-checkout records are included only once the address is confirmed.
    orders = sorted(customer_orders(customer), key=lambda o: o.created_at)
    visible = select(Entitlement.id).where(account_scope(customer))
    entitlements = db.session.scalars(select(Entitlement).where(account_scope(customer))).all()
    downloads = db.session.scalars(
        select(DownloadEvent)
        .where(
            DownloadEvent.customer_id == customer.id,
            DownloadEvent.entitlement_id.is_(None) | DownloadEvent.entitlement_id.in_(visible),
        )
        .order_by(DownloadEvent.created_at)
    ).all()
    return {
        "exported_at": iso(_now()),
        "profile": profile(customer) | {"last_login_at": iso(customer.last_login_at)},
        "orders": [
            {
                "number": o.number,
                "status": o.status,
                "currency": o.currency,
                "total_minor": o.total_minor,
                "refunded_minor": o.refunded_minor,
                "mode": o.mode,
                "created_at": iso(o.created_at),
                "paid_at": iso(o.paid_at),
                "items": [
                    {"title": i.title, "amount_minor": i.line_total_minor, "currency": i.currency}
                    for i in o.items
                ],
            }
            for o in orders
        ],
        "library": [
            {
                "product": e.product.title,
                "source": e.source,
                "status": e.status,
                "granted_at": iso(e.granted_at),
                "revoked_at": iso(e.revoked_at),
            }
            for e in entitlements
        ],
        "downloads": [
            {"at": iso(d.created_at), "status": d.status, "ip_address": d.ip_address}
            for d in downloads
        ],
        "learning": _learning_export(customer),
    }


def _learning_export(customer: Customer) -> list[dict[str, Any]]:
    from ..courses.learning import export_learner

    return export_learner(customer)


def request_deletion(customer: Customer, password: str) -> dict[str, Any]:
    """Anonymise the account. Financial records are retained (accounting/legal duty)."""
    if not verify_password(customer.password_hash, password or ""):
        raise AuthenticationError("Your password is incorrect.")
    from .checkout import guest_visible

    open_orders = select(Order.id).where(
        Order.customer_id == customer.id, Order.status.in_(("pending", "awaiting_payment"))
    )
    if not guest_visible(customer):
        open_orders = open_orders.where(Order.is_guest.is_(False))
    if db.session.scalar(open_orders.limit(1)):
        raise ConflictError("Cancel or complete your unpaid orders before deleting your account.")
    has_guest_orders = db.session.scalar(
        select(Order.id).where(Order.customer_id == customer.id, Order.is_guest.is_(True)).limit(1)
    )
    if has_guest_orders and not guest_visible(customer):
        # The address was never confirmed, so whoever registered it may not be the buyer:
        # give the record back to guest checkout instead of deleting purchases they
        # can't see. The response is the same either way.
        _restore_guest(customer)
    else:
        anonymise(customer, actor=None)
    return {"deleted": True}


def _restore_guest(customer: Customer) -> None:
    from .entitlements import guest_scope

    customer.status = "guest"
    customer.password_hash = None
    customer.deletion_requested_at = None
    revoke_all(customer)
    db.session.execute(
        update(Entitlement)
        .where(
            Entitlement.customer_id == customer.id,
            Entitlement.status == "active",
            ~Entitlement.id.in_(select(Entitlement.id).where(guest_scope(customer))),
        )
        .values(status="revoked", revoked_at=_now(), revoked_reason="Account deleted")
        .execution_options(synchronize_session=False)
    )
    audit_service.record("customer.guest_restored", "customer", customer.id)


def anonymise(customer: Customer, actor) -> None:
    original_id = customer.id
    customer.deletion_requested_at = customer.deletion_requested_at or _now()
    customer.email = f"deleted-{customer.public_id}@deleted.invalid"
    customer.display_name = ""
    customer.password_hash = None
    customer.status = "deleted"
    customer.deleted_at = _now()
    customer.support_notes = ""
    revoke_all(customer)
    db.session.execute(
        update(Entitlement)
        .where(Entitlement.customer_id == original_id, Entitlement.status == "active")
        .values(status="revoked", revoked_at=_now(), revoked_reason="Account deleted")
    )
    db.session.execute(
        update(DownloadEvent)
        .where(DownloadEvent.customer_id == original_id)
        .values(ip_address=None, user_agent="")
    )
    from ..courses.learning import erase_learner

    erase_learner(customer)
    audit_service.record(
        "customer.anonymised",
        "customer",
        original_id,
        actor=actor,
        details={"orders_retained": True},
    )
