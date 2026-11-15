"""Encryption at rest for connected-account tokens (Fernet: AES-128-CBC + HMAC-SHA256).

The key comes from ``SOCIAL_TOKEN_ENCRYPTION_KEY`` (never the database or the repository).
Several comma-separated keys rotate: the first encrypts, every key can decrypt.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app


class TokenKeyError(Exception):
    pass


def _keys() -> list[str]:
    raw = current_app.config.get("SOCIAL_TOKEN_ENCRYPTION_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _fernet() -> MultiFernet:
    keys = _keys()
    if not keys:
        raise TokenKeyError("SOCIAL_TOKEN_ENCRYPTION_KEY is not set.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError):
        raise TokenKeyError("SOCIAL_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.") from None


def key_problem() -> str | None:
    try:
        _fernet()
    except TokenKeyError as exc:
        return str(exc)
    return None


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unseal(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise TokenKeyError(
            "A stored token could not be decrypted (the encryption key changed). "
            "Reconnect the account."
        ) from None
