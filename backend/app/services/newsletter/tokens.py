"""Signed subscriber links and privacy-preserving hashes.

- Manage links (unsubscribe + preferences) are HMAC-signed ``<public_id>.<version>.<sig>``.
  They never expire, so old emails can always unsubscribe, and bumping the subscriber's
  ``token_version`` revokes every earlier link.
- Confirmation links add an issue timestamp and expire after NEWSLETTER_CONFIRM_TTL_HOURS.
- Email and IP hashes are used for the suppression list and consent evidence, so the
  plain values do not need to be kept after erasure.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from flask import current_app

from ...models import Subscriber


def _key(purpose: str) -> bytes:
    secret = current_app.config["SECRET_KEY"]
    return hashlib.sha256(f"tpa-newsletter:{purpose}:{secret}".encode()).digest()


def _sign(purpose: str, payload: str) -> str:
    return hmac.new(_key(purpose), payload.encode(), hashlib.sha256).hexdigest()[:40]


def email_hash(email: str) -> str:
    return hashlib.sha256(normalise_email(email).encode()).hexdigest()


def ip_hash(ip: str | None) -> str:
    if not ip:
        return ""
    return hmac.new(_key("ip"), ip.encode(), hashlib.sha256).hexdigest()


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def manage_token(subscriber: Subscriber) -> str:
    payload = f"{subscriber.public_id}.{subscriber.token_version}"
    return f"{payload}.{_sign('manage', payload)}"


def parse_manage_token(token: str) -> tuple[str, int] | None:
    parts = (token or "").split(".")
    if len(parts) != 3 or len(token) > 120:
        return None
    public_id, version, sig = parts
    if not version.isdigit() or not hmac.compare_digest(
        _sign("manage", f"{public_id}.{version}"), sig
    ):
        return None
    return public_id, int(version)


def confirm_token(subscriber: Subscriber) -> str:
    payload = f"{subscriber.public_id}.{subscriber.token_version}.{int(time.time())}"
    return f"{payload}.{_sign('confirm', payload)}"


def parse_confirm_token(token: str) -> tuple[str, int] | None:
    parts = (token or "").split(".")
    if len(parts) != 4 or len(token) > 140:
        return None
    public_id, version, issued, sig = parts
    if not (version.isdigit() and issued.isdigit()):
        return None
    if not hmac.compare_digest(_sign("confirm", f"{public_id}.{version}.{issued}"), sig):
        return None
    ttl = current_app.config["NEWSLETTER_CONFIRM_TTL_HOURS"] * 3600
    if time.time() - int(issued) > ttl:
        return None
    return public_id, int(version)


def feedback_signature(raw_body: bytes) -> str:
    secret = current_app.config.get("EMAIL_FEEDBACK_SECRET") or ""
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
