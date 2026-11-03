"""Two-step sign-in for administrators: time-based one-time codes (RFC 6238, as used by
Google Authenticator, Microsoft Authenticator, 1Password, Bitwarden and others) and
single-use recovery codes. Standard library only.

Secrets: only a random salt is stored per user. The 160-bit authenticator secret is
derived from it with the server key (MFA_KEY, default SECRET_KEY), so a copy of the
database alone can't produce codes. Rotating that key ends every enrolment (each admin
then signs in with a recovery code, or is reset with `flask admin reset-mfa`, and enrols
again).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from flask import current_app

from ..models import User

STEP_SECONDS = 30
DIGITS = 6
# Accept the previous and next 30-second step too (phone clocks drift).
WINDOW = 1
RECOVERY_CODES = 10


def _key() -> bytes:
    return (current_app.config.get("MFA_KEY") or current_app.config["SECRET_KEY"]).encode()


def _secret(user_id: int, salt: str) -> bytes:
    return hmac.new(_key(), f"tpa-mfa:{user_id}:{salt}".encode(), hashlib.sha256).digest()[:20]


def new_salt() -> str:
    return secrets.token_hex(16)


def secret_base32(user: User, salt: str) -> str:
    """The setup key typed into an authenticator app (groups of four for readability)."""
    raw = base64.b32encode(_secret(user.id, salt)).decode().rstrip("=")
    return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def provisioning_uri(user: User, salt: str, issuer: str) -> str:
    """otpauth:// link: opens the authenticator app on a phone (or encodes as a QR code)."""
    secret = secret_base32(user, salt).replace(" ", "")
    label = quote(f"{issuer}:{user.email}")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }  # fmt: skip
    )
    return f"otpauth://totp/{label}?{query}"


def code_at(secret: bytes, step: int) -> str:
    """RFC 4226 HOTP value for one time step."""
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def _clean(code: str) -> str:
    return "".join(ch for ch in str(code or "") if ch.isalnum()).lower()


def match_code(user: User, code: str, salt: str, now: float | None = None) -> int | None:
    """The time step a six-digit code belongs to, or None. A step already used (by this
    user) is refused, so an intercepted code can't be replayed."""
    code = _clean(code)
    if len(code) != DIGITS or not code.isdigit():
        return None
    secret = _secret(user.id, salt)
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if user.mfa_last_step is not None and candidate <= user.mfa_last_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def _hash_recovery(code: str) -> str:
    return hmac.new(_key(), f"tpa-mfa-recovery:{_clean(code)}".encode(), hashlib.sha256).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """(codes shown once, hashes stored). Each code is 10 random base32 characters."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = []
    for _ in range(RECOVERY_CODES):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_hash_recovery(c) for c in codes]


def use_recovery_code(user: User, code: str) -> bool:
    """Accept and consume one recovery code."""
    if len(_clean(code)) != 10:
        return False
    digest = _hash_recovery(code)
    stored = list(user.mfa_recovery_codes or [])
    for value in stored:
        if hmac.compare_digest(value, digest):
            stored.remove(value)
            user.mfa_recovery_codes = stored
            return True
    return False


def verify_second_factor(user: User, code: str) -> str | None:
    """'totp' or 'recovery' when the code is valid for this enrolled user, else None."""
    if not user.mfa_salt:
        return None
    step = match_code(user, code, user.mfa_salt)
    if step is not None:
        user.mfa_last_step = step
        return "totp"
    if use_recovery_code(user, code):
        return "recovery"
    return None
