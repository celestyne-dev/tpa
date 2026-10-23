"""Payment configuration and checkout readiness.

Two layers:
- **Environment (deployment):** the Paystack secret/public keys, the API base and
  ``PAYMENTS_LIVE_ALLOWED``. Secrets are never stored in the database and never
  returned by any API (the admin only sees whether a key is present and its mode).
- **Database (Super Admin, ``payments.configure``):** whether checkout is open
  (``disabled`` | ``test`` | ``live``), which currencies and payment channels are
  enabled for this merchant, order expiry, refund method and the live-readiness
  attestation. Stored in ``site_settings`` under ``payments.*`` keys that are not
  part of the general settings registry, so the general settings API cannot read
  or change them.

Defaults are safe: checkout disabled, no currencies enabled, refunds manual.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from ..commerce.currency import CURRENCIES
from ..extensions import db
from ..models import SiteSetting
from ..utils.errors import ValidationError
from .paystack import SUPPORTED_CHANNELS, get_provider

CHECKOUT_MODES = ("disabled", "test", "live")
DEFAULTS: dict[str, Any] = {
    "payments.provider": "paystack",
    "payments.checkout_mode": "disabled",
    "payments.currencies": [],
    "payments.channels": ["card"],
    "payments.order_expiry_minutes": 60,
    "payments.refunds_via_provider": False,
    "payments.terms_version": "",
    "payments.download_limit": None,
    "payments.live_attestation": None,
}
LIVE_ATTESTATIONS = {
    "merchant_verified": "The Paystack business is fully activated (compliance approved, "
    "settlement account verified).",
    "currencies_enabled": "Every enabled currency is active on the Paystack account for live "
    "charges (e.g. USD/international cards approved by Paystack).",
    "webhook_configured": "The live webhook URL is saved in the Paystack dashboard.",
    "policies_reviewed": "Terms, refund policy and privacy policy have been reviewed for "
    "digital products.",
    "test_purchase_done": "A complete test-mode purchase (payment, webhook, download, refund) "
    "has been checked.",
}


def _stored() -> dict[str, Any]:
    rows = db.session.scalars(select(SiteSetting).where(SiteSetting.key.in_(list(DEFAULTS))))
    return {r.key: r.value for r in rows}


def get_settings() -> dict[str, Any]:
    stored = _stored()
    return {k: (stored[k] if stored.get(k) is not None else v) for k, v in DEFAULTS.items()}


def _set(key: str, value: Any, actor_id: int | None) -> None:
    record = db.session.get(SiteSetting, key)
    if record is None:
        record = SiteSetting(key=key)
        db.session.add(record)
    record.value = value
    record.updated_by_id = actor_id


def provider_status() -> dict[str, Any]:
    provider = get_provider()
    cfg = current_app.config
    return {
        "name": provider.name,
        "label": "Paystack",
        "secret_key_configured": provider.configured(),
        "public_key_configured": bool(cfg.get("PAYSTACK_PUBLIC_KEY")),
        "key_mode": provider.mode,
        "public_key_mode": (
            "test"
            if str(cfg.get("PAYSTACK_PUBLIC_KEY", "")).startswith("pk_test_")
            else "live"
            if str(cfg.get("PAYSTACK_PUBLIC_KEY", "")).startswith("pk_live_")
            else None
        ),
        "api_base_is_official": cfg.get("PAYSTACK_API_BASE") == "https://api.paystack.co",
        "live_allowed_by_deployment": bool(cfg.get("PAYMENTS_LIVE_ALLOWED")),
        "supported_currencies": sorted(provider.supported_currencies),
        "supported_channels": list(provider.supported_channels),
        "webhook_url": f"{current_app.config['SITE_URL']}/api/v1/payments/paystack/webhook",
        "callback_url": f"{current_app.config['SITE_URL']}/checkout/complete",
    }


def checkout_currencies() -> list[str]:
    """Currencies a shopper can actually pay in right now (empty when checkout is closed)."""
    settings = get_settings()
    provider = get_provider()
    return [
        c
        for c in settings["payments.currencies"]
        if c in provider.supported_currencies and c in CURRENCIES
    ]


def effective_mode() -> str:
    """The checkout mode that is actually in force (configuration can only restrict it)."""
    settings = get_settings()
    mode = settings["payments.checkout_mode"]
    provider = get_provider()
    if mode == "disabled" or not provider.configured() or not checkout_currencies():
        return "disabled"
    if mode == "live":
        if provider.mode != "live" or not readiness()["live_ready"]:
            return "disabled"
        return "live"
    if mode == "test":
        return "test" if provider.mode == "test" else "disabled"
    return "disabled"


def checkout_available_for(customer) -> tuple[bool, str]:
    """Whether this customer may pay right now, with a user-facing reason when not."""
    mode = effective_mode()
    if mode == "disabled":
        return False, "Checkout is not open yet. No payments are being taken."
    if mode == "test":
        public = bool(current_app.config.get("PAYMENTS_TEST_CHECKOUT_PUBLIC")) and (
            current_app.config.get("ENV_NAME") != "production"
        )
        if not public and not (customer is not None and customer.is_test_account):
            return False, "Checkout is in testing and not open to customers yet."
    return True, ""


def public_status(customer=None) -> dict[str, Any]:
    mode = effective_mode()
    allowed, reason = checkout_available_for(customer)
    return {
        "open": allowed,
        "mode": mode,
        "test_mode": mode == "test",
        "currencies": checkout_currencies() if mode != "disabled" else [],
        "channels": list(get_settings()["payments.channels"] or []) if mode != "disabled" else [],
        "message": reason,
        "provider": "Paystack" if mode != "disabled" else None,
    }


# ---- readiness -------------------------------------------------------------------------


def _check(key: str, label: str, ok: bool, detail: str = "", level: str = "live") -> dict:
    return {"key": key, "label": label, "ok": bool(ok), "detail": detail, "required_for": level}


def readiness() -> dict[str, Any]:
    from ..models import Order, PaymentEvent
    from ..services.commerce.catalogue import purchasable_count
    from ..storage.private_files import get_private_storage

    cfg = current_app.config
    settings = get_settings()
    provider = get_provider()
    currencies = settings["payments.currencies"]
    unsupported = [c for c in currencies if c not in provider.supported_currencies]
    attestation = settings["payments.live_attestation"] or {}
    test_paid = db.session.scalar(
        select(func.count(Order.id)).where(Order.mode == "test", Order.status == "paid")
    )
    test_webhooks = db.session.scalar(
        select(func.count(PaymentEvent.id)).where(
            PaymentEvent.mode == "test", PaymentEvent.status == "processed"
        )
    )
    try:
        storage_ok = get_private_storage().writable()
    except Exception:  # noqa: BLE001 - reported as a failed check
        storage_ok = False
    checks = [
        _check(
            "secret_key",
            "Paystack secret key is configured on the server",
            provider.configured(),
            "Set PAYSTACK_SECRET_KEY in backend/.env (never in the admin).",
            "test",
        ),
        _check(
            "currencies",
            "At least one checkout currency is enabled and supported by Paystack",
            bool(currencies) and not unsupported,
            f"Unsupported: {', '.join(unsupported)}" if unsupported else "",
            "test",
        ),
        _check(
            "private_storage",
            "Private product file storage is writable",
            storage_ok,
            "Check PRODUCT_FILES_ROOT permissions.",
            "test",
        ),
        _check(
            "products",
            "At least one product is on sale with files and a price",
            purchasable_count() > 0,
            "Publish a product, upload its files, set a price and mark it on sale.",
            "test",
        ),
        _check(
            "live_key",
            "A live secret key (sk_live_) is configured",
            provider.mode == "live",
        ),
        _check(
            "live_allowed",
            "The deployment allows live payments (PAYMENTS_LIVE_ALLOWED=true)",
            bool(cfg.get("PAYMENTS_LIVE_ALLOWED")),
        ),
        _check(
            "official_api",
            "Payments go to the official Paystack API",
            cfg.get("PAYSTACK_API_BASE") == "https://api.paystack.co",
        ),
        _check(
            "https",
            "The site and cookies use HTTPS",
            str(cfg.get("SITE_URL", "")).startswith("https://")
            and bool(cfg.get("JWT_COOKIE_SECURE"))
            and bool(cfg.get("CUSTOMER_COOKIE_SECURE")),
        ),
        _check(
            "email",
            "Transactional email is delivered by SMTP",
            str(cfg.get("MAIL_BACKEND", "")).lower() == "smtp",
            "Receipts and download instructions must actually reach customers.",
        ),
        _check(
            "test_purchase",
            "A test-mode payment was verified and its webhook processed",
            bool(test_paid) and bool(test_webhooks),
        ),
        _check(
            "terms_version",
            "A terms version is recorded for checkout acknowledgements",
            bool(settings["payments.terms_version"]),
        ),
    ]
    for key, label in LIVE_ATTESTATIONS.items():
        checks.append(_check(f"attest_{key}", label, bool(attestation.get(key))))
    test_ready = all(c["ok"] for c in checks if c["required_for"] == "test")
    live_ready = test_ready and all(c["ok"] for c in checks if c["required_for"] == "live")
    return {
        "checks": checks,
        "test_ready": test_ready,
        "live_ready": live_ready,
        "attestation": attestation,
    }


# ---- updates ---------------------------------------------------------------------------


def update_settings(changes: dict[str, Any], actor) -> dict[str, Any]:
    from ..services import audit_service

    settings = get_settings()
    errors: dict[str, list[str]] = {}
    clean: dict[str, Any] = {}
    provider = get_provider()
    for key, value in changes.items():
        full = f"payments.{key}"
        if full not in DEFAULTS or key in ("provider", "live_attestation"):
            errors[key] = ["Unknown or read-only setting."]
            continue
        if key == "checkout_mode":
            if value not in CHECKOUT_MODES:
                errors[key] = [f"Use one of: {', '.join(CHECKOUT_MODES)}."]
                continue
        elif key == "currencies":
            if not isinstance(value, list) or not all(isinstance(c, str) for c in value):
                errors[key] = ["Choose currencies from the list."]
                continue
            value = list(dict.fromkeys(c.upper() for c in value))
            bad = [
                c for c in value if c not in CURRENCIES or c not in provider.supported_currencies
            ]
            if bad:
                errors[key] = [f"Not supported for checkout: {', '.join(bad)}."]
                continue
        elif key == "channels":
            if not isinstance(value, list) or not value:
                errors[key] = ["Enable at least one payment channel."]
                continue
            bad = [c for c in value if c not in SUPPORTED_CHANNELS]
            if bad:
                errors[key] = [f"Unknown channel(s): {', '.join(map(str, bad))}."]
                continue
            value = list(dict.fromkeys(value))
        elif key == "order_expiry_minutes":
            if not isinstance(value, int) or isinstance(value, bool) or not 15 <= value <= 1440:
                errors[key] = ["Use a whole number of minutes between 15 and 1440."]
                continue
        elif key == "refunds_via_provider":
            if not isinstance(value, bool):
                errors[key] = ["Must be true or false."]
                continue
        elif key == "terms_version":
            if not isinstance(value, str) or len(value.strip()) > 40:
                errors[key] = ["Use at most 40 characters, e.g. 2026-10."]
                continue
            value = value.strip()
        elif key == "download_limit" and (
            value is not None
            and (not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1000)
        ):
            errors[key] = ["Leave empty for no limit, or use 1–1000 downloads per file."]
            continue
        clean[full] = value
    if errors:
        raise ValidationError("Some payment settings are invalid.", details=errors)
    if clean.get("payments.checkout_mode") == "live":
        merged_currencies = clean.get("payments.currencies", settings["payments.currencies"])
        if not merged_currencies:
            raise ValidationError(details={"checkout_mode": ["Enable a currency first."]})
        state = readiness()
        if not state["live_ready"]:
            missing = [c["label"] for c in state["checks"] if not c["ok"]]
            raise ValidationError(
                "Live checkout cannot be enabled until every readiness check passes.",
                details={"checkout_mode": missing},
            )
    if clean.get("payments.checkout_mode") == "test" and provider.mode != "test":
        raise ValidationError(
            details={"checkout_mode": ["Test checkout needs a test secret key (sk_test_)."]}
        )
    changed = {}
    for key, value in clean.items():
        if settings[key] != value:
            changed[key] = {"from": settings[key], "to": value}
            _set(key, value, actor.id)
    if changed:
        audit_service.record("payments.settings_updated", "payments", actor=actor, details=changed)
    return {"changed": sorted(changed)}


def update_attestation(values: dict[str, Any], actor) -> dict[str, Any]:
    from ..services import audit_service

    if not isinstance(values, dict) or set(values) - set(LIVE_ATTESTATIONS):
        raise ValidationError(details={"attestation": ["Unknown checklist item."]})
    if not all(isinstance(v, bool) for v in values.values()):
        raise ValidationError(details={"attestation": ["Each item must be true or false."]})
    current = dict(get_settings()["payments.live_attestation"] or {})
    now = datetime.now(UTC).isoformat()
    for key, value in values.items():
        if value:
            current[key] = {"confirmed_at": now, "by": actor.display_name, "by_id": actor.id}
        else:
            current.pop(key, None)
    _set("payments.live_attestation", current, actor.id)
    audit_service.record(
        "payments.live_checklist_updated", "payments", actor=actor, details={"items": values}
    )
    # Withdrawing a confirmation immediately closes live checkout.
    if get_settings()["payments.checkout_mode"] == "live" and not all(
        current.get(k) for k in LIVE_ATTESTATIONS
    ):
        _set("payments.checkout_mode", "disabled", actor.id)
    return current
