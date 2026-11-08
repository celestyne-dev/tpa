"""Newsletter sending settings, readiness checks and the public signup status.

Non-secret settings live in ``site_settings`` (``email.*`` keys). Credentials never do:
SMTP passwords and feedback secrets stay in the environment.

Sending modes:
- ``disabled`` (default): nothing is sent; public signup forms stay hidden.
- ``test``: mail is delivered only to NEWSLETTER_TEST_RECIPIENTS; every other
  recipient is recorded as skipped. Safe for dry runs of real campaigns.
- ``live``: needs NEWSLETTER_LIVE_ALLOWED plus every readiness check.

Signup modes (``email.signup_mode``), independent of the sending mode:
- ``double_opt_in`` (default): website sign-ups get a confirmation email and become
  ``subscribed`` only after clicking it. Needs delivery to be ready.
- ``collection_only``: website sign-ups are stored with their consent evidence as
  ``collected`` (address not verified) and no email is sent. Campaigns go out through an
  external email service provider, from the admin export. Needs no SMTP, worker or
  NEWSLETTER_LIVE_ALLOWED. Either way sign-ups open only while the "Newsletter sign-ups
  open" setting (newsletter.is_open) is on.
"""

from __future__ import annotations

import re
from typing import Any

from flask import current_app
from sqlalchemy import select

from ...extensions import db
from ...models import SiteSetting
from ...utils.errors import ValidationError

SENDING_MODES = ("disabled", "test", "live")
SIGNUP_MODES = ("double_opt_in", "collection_only")
NEWSLETTER_NAME = "The Positive Reset"
NEWSLETTER_TAGLINE = "A Better Mindset. A Brighter Life."
# Keys are stored on subscribers and used by segments and automations, so they never change.
# "weekly" is the historical key of the main edition, which is now sent daily.
PREFERENCES = {
    "weekly": "The Positive Reset — daily email",
    "daily": "Daily encouragement",
    "reflection": "Weekly reflection prompts",
    "resources": "Free resources and guides",
    "products": "New digital products and offers",
}
DEFAULT_PREFERENCES = ["weekly"]
DEFAULT_CONSENT_TEXT = (
    "Yes, email me The Positive Reset every day: practical encouragement, healthier thinking, "
    "personal growth and useful resources. I can unsubscribe at any time with one click."
)
DEFAULT_COLLECTION_CONSENT_TEXT = (
    "Yes, send me The Positive Reset, the daily email newsletter from Think Positive Always, "
    "with practical encouragement, healthier thinking, personal growth and useful resources. "
    "Think Positive Always will store my email address (and first name, if I give it) to send "
    "me this newsletter, using an email service provider. I can unsubscribe at any time."
)
DEFAULTS: dict[str, Any] = {
    "email.sending_mode": "disabled",
    "email.from_name": "Think Positive Always",
    "email.reply_to": "",
    "email.consent_text": DEFAULT_CONSENT_TEXT,
    # A new version for the daily wording; subscribers keep the version they agreed to.
    "email.consent_version": "2026-11",
    "email.postal_address": "",
    "email.attestation": None,
    "email.signup_mode": "double_opt_in",
    # Collection-only wording says exactly what is stored and how it is used, and promises
    # no confirmation email. Versioned separately so the evidence shows which was agreed.
    "email.collection_consent_text": DEFAULT_COLLECTION_CONSENT_TEXT,
    "email.collection_consent_version": "2026-11-collection",
}
ATTESTATIONS = {
    "dns_authenticated": "SPF, DKIM and DMARC are published for the sending domain and pass "
    "for the configured provider.",
    "provider_validated": "The delivery provider account is verified for this sender address.",
    "test_send_checked": "A test email was received, displays correctly and its unsubscribe "
    "link works.",
    "privacy_reviewed": "The privacy policy describes the newsletter, consent and unsubscribing.",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def backend_name() -> str:
    cfg = current_app.config
    return (cfg.get("NEWSLETTER_MAIL_BACKEND") or cfg.get("MAIL_BACKEND") or "none").lower()


def backend_configured() -> bool:
    name = backend_name()
    if name == "smtp":
        cfg = current_app.config
        return bool(cfg.get("NEWSLETTER_SMTP_HOST") or cfg.get("MAIL_SMTP_HOST"))
    if name == "console":
        return current_app.config.get("ENV_NAME") != "production"
    return name == "memory" and bool(current_app.testing)


def sending_mode() -> str:
    mode = get_settings()["email.sending_mode"]
    return mode if mode in SENDING_MODES else "disabled"


def from_address(from_name: str | None = None) -> tuple[str, str]:
    settings = get_settings()
    return (from_name or settings["email.from_name"] or "Think Positive Always").strip(), (
        current_app.config.get("NEWSLETTER_FROM_EMAIL") or ""
    ).strip()


def is_test_recipient(email: str) -> bool:
    allowed = {
        e.strip().lower() for e in current_app.config.get("NEWSLETTER_TEST_RECIPIENTS") or []
    }
    return email.lower() in allowed


def signup_mode() -> str:
    mode = get_settings()["email.signup_mode"]
    return mode if mode in SIGNUP_MODES else "double_opt_in"


def collection_only() -> bool:
    return signup_mode() == "collection_only"


def consent() -> tuple[str, str]:
    """The consent wording and version shown on the website forms in the current mode."""
    settings = get_settings()
    if collection_only():
        return (
            str(settings["email.collection_consent_text"] or "").strip(),
            settings["email.collection_consent_version"],
        )
    return str(settings["email.consent_text"] or "").strip(), settings["email.consent_version"]


def delivery_ready() -> bool:
    """Confirmation emails can be sent (double opt-in needs this; collection does not)."""
    return bool(
        sending_mode() != "disabled"
        and backend_configured()
        and (current_app.config.get("NEWSLETTER_FROM_EMAIL") or "")
    )


def signup_open() -> bool:
    """Public forms take addresses only while sign-ups are switched on, the consent wording
    for the current mode is set and, for double opt-in, confirmation emails can be sent."""
    from ..settings_service import get_values

    if not get_values().get("newsletter.is_open"):
        return False
    text, _version = consent()
    if not text:
        return False
    return True if collection_only() else delivery_ready()


def public_status() -> dict[str, Any]:
    open_ = signup_open()
    text, version = consent()
    return {
        "name": NEWSLETTER_NAME,
        "tagline": NEWSLETTER_TAGLINE,
        "signup_open": open_,
        "signup_mode": signup_mode(),
        # Whether the website sends a confirmation email (the forms say so only when true).
        "confirmation_email": open_ and not collection_only(),
        "consent_text": text if open_ else "",
        "consent_version": version if open_ else "",
        "preferences": [{"key": k, "label": v} for k, v in PREFERENCES.items()],
        "default_preferences": DEFAULT_PREFERENCES,
    }


def _check(key: str, label: str, ok: bool, hint: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "ok": bool(ok), "hint": hint}


def readiness() -> dict[str, Any]:
    cfg = current_app.config
    settings = get_settings()
    attestation = settings["email.attestation"] or {}
    name = backend_name()
    real_provider = name == "smtp" or (current_app.testing and name == "memory")
    checks = [
        _check(
            "backend",
            "A delivery backend is configured on the server",
            backend_configured(),
            "Set NEWSLETTER_MAIL_BACKEND (or MAIL_BACKEND) and the SMTP settings in backend/.env.",
        ),
        _check(
            "from_email",
            "A sender address is configured (NEWSLETTER_FROM_EMAIL)",
            bool(cfg.get("NEWSLETTER_FROM_EMAIL")),
        ),
        _check(
            "consent_text",
            "Consent wording is set",
            bool(str(settings["email.consent_text"] or "").strip()),
        ),
        _check(
            "real_provider",
            "Live mail goes through a real provider (not the development console)",
            real_provider,
        ),
        _check(
            "live_allowed",
            "The deployment allows live sending (NEWSLETTER_LIVE_ALLOWED=true)",
            bool(cfg.get("NEWSLETTER_LIVE_ALLOWED")),
        ),
        _check(
            "postal_address",
            "A postal address for the email footer is set",
            bool(str(settings["email.postal_address"] or "").strip()),
            "Many anti-spam laws require a valid physical postal address in marketing email.",
        ),
    ]
    for key, label in ATTESTATIONS.items():
        checks.append(_check(f"attest_{key}", label, bool(attestation.get(key))))
    test_ready = all(c["ok"] for c in checks[:3])
    return {"checks": checks, "test_ready": test_ready, "live_ready": all(c["ok"] for c in checks)}


def admin_view() -> dict[str, Any]:
    cfg = current_app.config
    settings = get_settings()
    return {
        "sending_mode": sending_mode(),
        "from_name": settings["email.from_name"],
        "from_email": cfg.get("NEWSLETTER_FROM_EMAIL") or "",
        "reply_to": settings["email.reply_to"],
        "consent_text": settings["email.consent_text"],
        "consent_version": settings["email.consent_version"],
        "signup_mode": signup_mode(),
        "signup_modes": list(SIGNUP_MODES),
        "collection_consent_text": settings["email.collection_consent_text"],
        "collection_consent_version": settings["email.collection_consent_version"],
        "signup_open": signup_open(),
        "postal_address": settings["email.postal_address"],
        "attestation": {
            k: bool((settings["email.attestation"] or {}).get(k)) for k in ATTESTATIONS
        },
        "attestation_labels": ATTESTATIONS,
        "backend": backend_name(),
        "backend_configured": backend_configured(),
        "test_recipients": len(cfg.get("NEWSLETTER_TEST_RECIPIENTS") or []),
        "rate_per_minute": cfg.get("NEWSLETTER_SEND_RATE_PER_MINUTE"),
        "feedback_configured": bool(cfg.get("EMAIL_FEEDBACK_SECRET")),
        "feedback_url": f"{cfg['SITE_URL']}/api/v1/email/feedback",
        "delivery_evidence": (
            "SMTP reports only whether the relay accepted a message. Delivery, bounces and "
            "complaints are recorded only when the provider sends signed feedback."
        ),
        "readiness": readiness(),
    }


def update_settings(changes: dict[str, Any], actor) -> dict[str, Any]:
    from .. import audit_service

    settings = get_settings()
    errors: dict[str, list[str]] = {}
    clean: dict[str, Any] = {}
    limits = {
        "from_name": 80,
        "consent_text": 1000,
        "consent_version": 40,
        "postal_address": 300,
        "collection_consent_text": 1000,
        "collection_consent_version": 40,
    }
    for key, value in changes.items():
        full = f"email.{key}"
        if full not in DEFAULTS or key == "attestation":
            errors[key] = ["Unknown or read-only setting."]
            continue
        if key == "sending_mode":
            if value not in SENDING_MODES:
                errors[key] = [f"Use one of: {', '.join(SENDING_MODES)}."]
                continue
        elif key == "signup_mode":
            if value not in SIGNUP_MODES:
                errors[key] = [f"Use one of: {', '.join(SIGNUP_MODES)}."]
                continue
        elif key == "reply_to":
            value = str(value or "").strip()
            if value and not _EMAIL.match(value):
                errors[key] = ["Enter a valid email address or leave empty."]
                continue
        else:
            value = str(value or "").strip()
            if len(value) > limits[key] or any(c in value for c in "<>"):
                errors[key] = [f"Plain text up to {limits[key]} characters."]
                continue
        clean[full] = value
    if errors:
        raise ValidationError("Some email settings are invalid.", details=errors)
    mode = clean.get("email.sending_mode")
    if mode in ("test", "live"):
        state = readiness()
        required = state["live_ready"] if mode == "live" else state["test_ready"]
        if not required:
            names = state["checks"] if mode == "live" else state["checks"][:3]
            raise ValidationError(
                f"{mode.capitalize()} sending cannot be enabled until the readiness checks pass.",
                details={"sending_mode": [c["label"] for c in names if not c["ok"]]},
            )
    for text_key, version_key in (
        ("email.consent_text", "email.consent_version"),
        ("email.collection_consent_text", "email.collection_consent_version"),
    ):
        if (
            text_key in clean
            and clean[text_key] != settings[text_key]
            and (version_key not in clean or clean[version_key] == settings[version_key])
        ):
            short = version_key.removeprefix("email.")
            raise ValidationError(
                details={short: ["Change the consent version when the wording changes."]}
            )
    changed = {}
    for key, value in clean.items():
        if settings[key] != value:
            changed[key] = {"from": settings[key], "to": value}
            _set(key, value, actor.id)
    if changed:
        audit_service.record("email.settings_updated", "email", actor=actor, details=changed)
        if {
            "email.sending_mode",
            "email.consent_text",
            "email.consent_version",
            "email.signup_mode",
            "email.collection_consent_text",
            "email.collection_consent_version",
        } & set(changed):
            # Signup forms are prerendered: rebuild so they appear, disappear or update.
            from ..publication_service import record_public_change

            record_public_change("settings", "email", "newsletter_signup_changed", actor)
    return {"changed": sorted(changed)}


def update_attestation(values: dict[str, Any], actor) -> dict[str, Any]:
    from .. import audit_service

    current = dict(get_settings()["email.attestation"] or {})
    for key, value in values.items():
        if key not in ATTESTATIONS or not isinstance(value, bool):
            raise ValidationError(details={key: ["Unknown confirmation."]})
        current[key] = value
    _set("email.attestation", current, actor.id)
    # Withdrawing a confirmation while live drops back to "disabled" immediately.
    if sending_mode() == "live" and not all(current.get(k) for k in ATTESTATIONS):
        _set("email.sending_mode", "disabled", actor.id)
    audit_service.record("email.attestation_updated", "email", actor=actor, details=current)
    return current
