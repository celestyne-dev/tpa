"""Cookie-based JWT sessions: issuing, rotation, revocation and JWT callbacks.

- Access token: short-lived, HttpOnly cookie scoped to /api/.
- Refresh token: HttpOnly cookie scoped to /api/v1/admin/auth/, recorded in the
  refresh_tokens table so it can be rotated and revoked. Reusing a rotated
  refresh token revokes every session of that user.
- Both tokens carry the user's session_version; bumping it (password change,
  account disabled) invalidates all outstanding access tokens immediately.
- CSRF: Flask-JWT-Extended double-submit cookies; mutations must send
  X-CSRF-TOKEN matching the readable csrf_* cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Flask, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import select, update

from ..extensions import db, jwt
from ..models import RefreshToken, User
from ..utils.responses import error_body


def _now() -> datetime:
    return datetime.now(UTC)


def issue_session(user: User, response) -> str:
    claims = {"sv": user.session_version}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)
    decoded = decode_token(refresh)
    db.session.add(
        RefreshToken(
            jti=decoded["jti"],
            user_id=user.id,
            expires_at=datetime.fromtimestamp(decoded["exp"], UTC),
        )
    )
    set_access_cookies(response, access)
    set_refresh_cookies(response, refresh)
    return decoded["jti"]


def rotate_session(user: User, old_jti: str, response) -> None:
    new_jti = issue_session(user, response)
    db.session.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == old_jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), replaced_by_jti=new_jti)
    )


def revoke_refresh_token(jti: str) -> None:
    db.session.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_all_sessions(user: User, *, keep_access: bool = False) -> None:
    """Revoke every refresh token and (unless keep_access) all access tokens."""
    db.session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    if not keep_access:
        user.session_version += 1


def clear_session_cookies(response) -> None:
    unset_jwt_cookies(response)


def _auth_error(status: int, code: str, message: str):
    return jsonify(error_body(code, message)), status


def init_jwt_callbacks(app: Flask) -> None:
    @jwt.user_lookup_loader
    def load_user(_header, payload):
        try:
            user = db.session.get(User, int(payload["sub"]))
        except (TypeError, ValueError):
            return None
        if user is None or not user.is_active or payload.get("sv") != user.session_version:
            return None
        return user

    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload) -> bool:
        if payload.get("type") != "refresh":
            return False
        record = db.session.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        if record is None:
            return True
        if record.revoked_at is not None:
            if record.replaced_by_jti:
                # A rotated token was presented again: treat as theft, end all sessions.
                user = db.session.get(User, record.user_id)
                if user is not None:
                    revoke_all_sessions(user)
                    db.session.commit()
            return True
        return False

    @jwt.user_lookup_error_loader
    def user_lookup_error(_header, _payload):
        return _auth_error(
            401, "session_invalid", "Your session is no longer valid. Please sign in."
        )

    @jwt.expired_token_loader
    def expired(_header, _payload):
        return _auth_error(401, "token_expired", "Your session has expired.")

    @jwt.revoked_token_loader
    def revoked(_header, _payload):
        return _auth_error(401, "session_revoked", "Your session has ended. Please sign in again.")

    @jwt.unauthorized_loader
    def missing(reason: str):
        if "CSRF" in reason:
            return _auth_error(403, "csrf_failed", "Missing or invalid CSRF token.")
        return _auth_error(401, "authentication_required", "Authentication is required.")

    @jwt.invalid_token_loader
    def invalid(reason: str):
        if "CSRF" in reason:
            return _auth_error(403, "csrf_failed", "Missing or invalid CSRF token.")
        return _auth_error(401, "invalid_token", "Your session is invalid. Please sign in.")
