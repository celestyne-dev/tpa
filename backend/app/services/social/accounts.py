"""Connecting, refreshing and disconnecting the Pinterest and Instagram accounts.

OAuth state: a signed, time-limited value bound to the platform and to the administrator who
started the connection (CSRF protection). The callback is completed by an authenticated
admin API call, so a forged or replayed callback is refused. Tokens are stored encrypted;
API responses describe the account but never include a token.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from ...extensions import db
from ...models import SocialAccount, User
from ...utils.errors import NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import crypto, instagram, pinterest
from .http import SocialError

PLATFORMS = ("pinterest", "instagram")
LABELS = {"pinterest": "Pinterest", "instagram": "Instagram"}
STATE_MAX_AGE = 600  # seconds the administrator has to approve on the platform
CLIENTS = {"pinterest": pinterest, "instagram": instagram}
# Refresh this long before expiry (the publishing timer also refreshes daily).
REFRESH_MARGIN = {"pinterest": timedelta(days=3), "instagram": timedelta(days=10)}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def check_platform(platform: str) -> str:
    if platform not in PLATFORMS:
        raise NotFoundError("Unknown platform.")
    return platform


def setup_missing(platform: str) -> list[str]:
    """Environment settings an operator still has to provide (names only, never values)."""
    cfg = current_app.config
    prefix = platform.upper()
    missing = [
        name for name in (f"{prefix}_CLIENT_ID", f"{prefix}_CLIENT_SECRET") if not cfg.get(name)
    ]
    if platform == "instagram" and not cfg.get("INSTAGRAM_CONFIG_ID"):
        missing.append("INSTAGRAM_CONFIG_ID")  # the Unified Login configuration
    if crypto.key_problem():
        missing.append("SOCIAL_TOKEN_ENCRYPTION_KEY")
    return missing


def redirect_uri(platform: str) -> str:
    configured = current_app.config.get(f"{platform.upper()}_REDIRECT_URI") or ""
    if configured:
        return configured
    base = current_app.config.get("ADMIN_BASE_URL", "").rstrip("/")
    return f"{base}/admin/integrations/{platform}/callback"


def get_account(platform: str) -> SocialAccount | None:
    return db.session.scalar(select(SocialAccount).where(SocialAccount.platform == platform))


def _required_scopes(platform: str) -> tuple[str, ...]:
    return CLIENTS[platform].SCOPES


def account_dict(platform: str) -> dict[str, Any]:
    account = get_account(platform)
    missing = setup_missing(platform)
    body: dict[str, Any] = {
        "platform": platform,
        "label": LABELS[platform],
        "setup": {"ready": not missing, "missing": missing},
        "redirect_uri": redirect_uri(platform),
        "scopes_requested": list(_required_scopes(platform)),
        "connected": False,
        "account": None,
    }
    if account is None:
        return body
    granted = list(account.scopes or [])
    connected_by = (
        db.session.get(User, account.connected_by_id) if account.connected_by_id else None
    )
    body["connected"] = account.status == "connected"
    body["account"] = {
        "status": account.status,
        "external_id": account.external_id,
        "username": account.username,
        "account_type": account.account_type,
        "profile_url": account.profile_url,
        "scopes": granted,
        "missing_scopes": [s for s in _required_scopes(platform) if granted and s not in granted],
        "access_expires_at": iso(account.access_expires_at),
        "refresh_expires_at": iso(account.refresh_expires_at),
        "last_error": account.last_error,
        "connected_at": iso(account.connected_at),
        "connected_by": connected_by.display_name if connected_by else None,
    }
    return body


def all_accounts() -> list[dict[str, Any]]:
    return [account_dict(p) for p in PLATFORMS]


# ---- connect ------------------------------------------------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="social-oauth-state")


def start_connect(platform: str, user: User) -> dict[str, str]:
    check_platform(platform)
    if missing := setup_missing(platform):
        raise ValidationError(
            f"{LABELS[platform]} is not set up on the server yet. Missing: {', '.join(missing)}.",
            details={"setup": missing},
        )
    state = _serializer().dumps({"p": platform, "u": user.id, "n": secrets.token_urlsafe(16)})
    url = CLIENTS[platform].authorize_url(state, redirect_uri(platform))
    return {"authorize_url": url}


def _check_state(platform: str, state: str, user: User) -> None:
    try:
        data = _serializer().loads(state or "", max_age=STATE_MAX_AGE)
    except SignatureExpired:
        raise ValidationError("The connection request expired. Start again.") from None
    except BadSignature:
        raise ValidationError("The connection request is invalid. Start again.") from None
    if not isinstance(data, dict) or data.get("p") != platform or data.get("u") != user.id:
        raise ValidationError("This connection was started by someone else. Start again.")


def _expiry(seconds: Any) -> datetime | None:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    return _now() + timedelta(seconds=value) if value > 0 else None


def _store_tokens(account: SocialAccount, tokens: dict[str, Any], platform: str) -> None:
    account.access_token_enc = crypto.seal(tokens["access_token"])
    account.access_expires_at = _expiry(tokens.get("expires_in"))
    if platform == "pinterest" and tokens.get("refresh_token"):
        account.refresh_token_enc = crypto.seal(tokens["refresh_token"])
        account.refresh_expires_at = _expiry(tokens.get("refresh_token_expires_in"))
    if tokens.get("scope"):
        account.scopes = [s for s in str(tokens["scope"]).replace(",", " ").split() if s]


def complete_connect(platform: str, code: str, state: str, user: User) -> dict[str, Any]:
    check_platform(platform)
    _check_state(platform, state, user)
    if not code or len(code) > 2000:
        raise ValidationError("The platform did not return an authorisation code.")
    if missing := setup_missing(platform):
        raise ValidationError(f"Missing server settings: {', '.join(missing)}.")
    try:
        if platform == "pinterest":
            tokens = pinterest.exchange_code(code, redirect_uri(platform))
            profile = pinterest.user_account(tokens["access_token"])
            external_id = str(profile.get("id") or profile.get("username") or "")
            username = profile.get("username")
            account_type = profile.get("account_type")
            profile_url = f"https://www.pinterest.com/{username}/" if username else None
            scopes = None
        else:
            tokens = instagram.exchange_code(code, redirect_uri(platform))
            scopes = tokens.get("scopes")
            if scopes is not None and "instagram_basic" not in scopes:
                raise SocialError(
                    "The instagram_basic permission was not granted. Add it to the Unified "
                    "Login configuration in the Meta app and approve it when connecting.",
                    permission=True,
                )
            existing = get_account(platform)
            profile = instagram.discover_account(
                tokens["access_token"],
                tokens.get("target_ids"),
                prefer=[
                    current_app.config.get("INSTAGRAM_ACCOUNT_ID") or "",
                    existing.external_id if existing else "",
                ],
            )
            external_id = profile["id"]
            username = profile["username"] or None
            account_type = None
            profile_url = f"https://www.instagram.com/{username}/" if username else None
    except SocialError as exc:
        audit_service.record(
            "social.connect_failed", "social_account", platform, actor=user,
            details={"error": exc.message},
        )  # fmt: skip
        db.session.commit()
        raise ValidationError(exc.message) from None
    if not external_id:
        raise ValidationError(f"{LABELS[platform]} did not identify the account.")
    account = get_account(platform)
    if account is None:
        account = SocialAccount(platform=platform, scopes=[])
        db.session.add(account)
    elif account.external_id != external_id:
        audit_service.record(
            "social.account_replaced", "social_account", platform, actor=user,
            details={"previous": account.username, "new": username},
        )  # fmt: skip
    account.status = "connected"
    account.external_id = external_id[:100]
    account.username = str(username)[:200] if username else None
    account.account_type = str(account_type)[:50] if account_type else None
    account.profile_url = profile_url
    if platform == "instagram":
        account.scopes = list(scopes or [])  # empty: Meta did not report the permissions
    else:
        account.scopes = list(scopes) if scopes else list(_required_scopes(platform))
    account.refresh_token_enc = None if platform == "instagram" else account.refresh_token_enc
    _store_tokens(account, tokens, platform)
    account.last_error = None
    account.connected_by_id = user.id
    account.connected_at = _now()
    db.session.flush()
    audit_service.record(
        "social.account_connected", "social_account", platform, actor=user,
        details={
            "username": account.username,
            "account_type": account.account_type,
            "token": tokens.get("kind") if platform == "instagram" else None,
            "expires": account.access_expires_at is not None,
        },
    )  # fmt: skip
    return account_dict(platform)


def disconnect(platform: str, user: User) -> dict[str, Any]:
    check_platform(platform)
    account = get_account(platform)
    if account is None:
        raise NotFoundError(f"{LABELS[platform]} is not connected.")
    username = account.username
    db.session.delete(account)
    db.session.flush()
    audit_service.record(
        "social.account_disconnected", "social_account", platform, actor=user,
        details={"username": username},
    )  # fmt: skip
    return account_dict(platform)


# ---- tokens -------------------------------------------------------------------------------


def _mark(account: SocialAccount, exc: SocialError) -> None:
    account.last_error = exc.message[:500]
    if exc.reconnect:
        account.status = "expired"


def _refresh(account: SocialAccount) -> None:
    if account.platform == "pinterest":
        if not account.refresh_token_enc:
            raise SocialError(
                "Pinterest did not provide a refresh token. Reconnect.", reconnect=True
            )
        tokens = pinterest.refresh(crypto.unseal(account.refresh_token_enc))
    else:
        # Only reached for a user token with an expiry; system-user tokens never expire.
        tokens = instagram.extend(crypto.unseal(account.access_token_enc))
    _store_tokens(account, tokens, account.platform)
    account.status = "connected"
    account.last_error = None


def _renew_instagram(account: SocialAccount, expires: datetime) -> None:
    """Renew an expiring Instagram user token. A failed renewal never blocks a post while
    the current token is still valid."""
    if expires <= _now():
        raise SocialError("The Instagram connection has expired. Reconnect.", reconnect=True)
    try:
        _refresh(account)
    except SocialError as exc:
        if exc.reconnect:
            raise
        account.last_error = f"The connection could not be renewed yet: {exc.message}"[:500]
        return
    audit_service.record("social.token_refreshed", "social_account", "instagram")


def access_token(platform: str) -> tuple[SocialAccount, str]:
    """The connected account and a usable access token (refreshed when close to expiry)."""
    account = get_account(platform)
    if account is None:
        raise SocialError(f"{LABELS[platform]} is not connected.", reconnect=True)
    if account.status == "expired":
        raise SocialError(
            f"The {LABELS[platform]} connection has expired. Reconnect it in Admin › Integrations.",
            reconnect=True,
        )
    try:
        expires = _aware(account.access_expires_at)
        # No expiry (Instagram system-user tokens): nothing to refresh, ever.
        if expires is not None and expires - _now() < REFRESH_MARGIN[platform]:
            if platform == "instagram":
                _renew_instagram(account, expires)
            else:
                _refresh(account)
                audit_service.record("social.token_refreshed", "social_account", platform)
        return account, crypto.unseal(account.access_token_enc)
    except crypto.TokenKeyError as exc:
        error = SocialError(str(exc), reconnect=True)
        _mark(account, error)
        raise error from None
    except SocialError as exc:
        _mark(account, exc)
        raise


def mark_failure(platform: str, exc: SocialError) -> None:
    """Record a reconnect-type failure seen while publishing."""
    if exc.reconnect and (account := get_account(platform)) is not None:
        _mark(account, exc)


def refresh_due() -> dict[str, list[str]]:
    """Refresh tokens close to expiry (run by the publishing timer)."""
    out: dict[str, list[str]] = {"refreshed": [], "failed": []}
    for account in db.session.scalars(select(SocialAccount)):
        if account.status != "connected":
            continue
        expires = _aware(account.access_expires_at)
        if expires is None or expires - _now() >= REFRESH_MARGIN[account.platform]:
            continue
        try:
            access_token(account.platform)
            out["refreshed"].append(account.platform)
        except SocialError:
            out["failed"].append(account.platform)
    return out
