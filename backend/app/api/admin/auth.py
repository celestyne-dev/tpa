from flask import current_app, jsonify, request
from flask_jwt_extended import current_user, get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_restful import Resource
from jwt.exceptions import PyJWTError

from ...auth import mfa
from ...auth.decorators import require_auth
from ...auth.session import (
    clear_session_cookies,
    issue_session,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_session,
)
from ...extensions import db, limiter
from ...schemas.admin import (
    AcceptInvitationSchema,
    ChangePasswordSchema,
    CompleteResetSchema,
    LoginSchema,
    TokenSchema,
)
from ...services import audit_service
from ...services.admin import account_tokens, auth_service
from ...utils.errors import AuthenticationError, ConflictError, ValidationError
from .._validation import load_body

_login = LoginSchema()
_sensitive_limit = [limiter.limit(lambda: current_app.config["RATELIMIT_SENSITIVE"])]
_change_password = ChangePasswordSchema()


def _login_email_key() -> str:
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else ""
    return "login-email:" + auth_service.normalise_email(str(email or ""))[:254]


class LoginResource(Resource):
    method_decorators = {
        "post": [
            limiter.limit(lambda: current_app.config["RATELIMIT_LOGIN"]),
            limiter.limit("10 per hour", key_func=_login_email_key),
        ]
    }

    def post(self):
        data = load_body(_login)
        user = auth_service.authenticate(data["email"], data["password"])
        if user is None:
            audit_service.record(
                "auth.login_failed", "auth", details={"reason": "invalid_credentials"}
            )
            db.session.commit()
            raise AuthenticationError(auth_service.GENERIC_LOGIN_ERROR)
        if user.mfa_salt:
            # Password accepted; the session starts only after the second step.
            audit_service.record("auth.mfa_challenge", "user", user.id, actor=user)
            db.session.commit()
            return {"data": {"mfa_required": True, "mfa_token": _mfa_token(user)}}
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        issue_session(user, response)
        audit_service.record("auth.login", "user", user.id, actor=user)
        db.session.commit()
        return response


# ---- two-step sign-in (TOTP) ---------------------------------------------------------

MFA_TOKEN_MINUTES = 5


def _mfa_token(user) -> str:
    """Short-lived proof that the password step passed (no session, no access)."""
    import secrets as _secrets
    from datetime import UTC, datetime, timedelta

    import jwt

    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "purpose": "admin-mfa",
        "sv": user.session_version,
        "iat": now,
        "exp": now + timedelta(minutes=MFA_TOKEN_MINUTES),
        "jti": _secrets.token_hex(8),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def _mfa_user(token: str):
    import jwt

    from ...models import User

    try:
        payload = jwt.decode(
            str(token or ""), current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "admin-mfa":
        return None
    user = db.session.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.session_version != payload.get("sv"):
        return None
    return user


def _mfa_token_key() -> str:
    body = request.get_json(silent=True)
    token = body.get("mfa_token") if isinstance(body, dict) else ""
    return "mfa-token:" + str(token or "")[-24:]


def _body(*fields: str) -> dict:
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    return {f: str(body.get(f) or "")[:300] for f in fields}


class MfaVerifyResource(Resource):
    """Second sign-in step: a code from the authenticator app, or a recovery code."""

    method_decorators = {
        "post": [
            limiter.limit(lambda: current_app.config["RATELIMIT_LOGIN"]),
            limiter.limit("5 per 5 minutes", key_func=_mfa_token_key),
        ]
    }

    def post(self):
        data = _body("mfa_token", "code")
        user = _mfa_user(data["mfa_token"])
        if user is None:
            raise AuthenticationError("Your sign-in expired. Please sign in again.")
        method = mfa.verify_second_factor(user, data["code"])
        if method is None:
            audit_service.record("auth.mfa_failed", "user", user.id, actor=user)
            db.session.commit()
            raise AuthenticationError("That code isn't valid. Check your authenticator app.")
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        issue_session(user, response)
        audit_service.record(
            "auth.login",
            "user",
            user.id,
            actor=user,
            details={
                "second_factor": method,
                **(
                    {"recovery_codes_left": len(user.mfa_recovery_codes or [])}
                    if method == "recovery"
                    else {}
                ),
            },
        )
        db.session.commit()
        return response


def _status(user) -> dict:
    return {
        "enabled": bool(user.mfa_salt),
        "enabled_at": user.mfa_enabled_at.isoformat() if user.mfa_enabled_at else None,
        "recovery_codes_left": len(user.mfa_recovery_codes or []),
        "required": auth_service.mfa_required(),
        "setup_pending": bool(user.mfa_pending_salt) and not user.mfa_salt,
    }


class MfaStatusResource(Resource):
    @require_auth
    def get(self):
        return {"data": _status(current_user)}


class MfaSetupResource(Resource):
    """Start enrolment: a new setup key (shown once) for the authenticator app."""

    method_decorators = {"post": _sensitive_limit}

    @require_auth
    def post(self):
        user = current_user
        if user.mfa_salt:
            raise ConflictError("Two-step sign-in is already on. Turn it off first to reset it.")
        user.mfa_pending_salt = mfa.new_salt()
        site_name = _site_name()
        db.session.commit()
        return {
            "data": {
                "setup_key": mfa.secret_base32(user, user.mfa_pending_salt),
                "otpauth_uri": mfa.provisioning_uri(user, user.mfa_pending_salt, site_name),
                "account": user.email,
                "issuer": site_name,
            }
        }


class MfaEnableResource(Resource):
    """Finish enrolment with a code from the app; returns the recovery codes once."""

    method_decorators = {"post": _sensitive_limit}

    @require_auth
    def post(self):
        user = current_user
        if user.mfa_salt:
            raise ConflictError("Two-step sign-in is already on.")
        if not user.mfa_pending_salt:
            raise ConflictError("Start the setup first.")
        step = mfa.match_code(user, _body("code")["code"], user.mfa_pending_salt)
        if step is None:
            raise ValidationError(
                details={"code": ["That code isn't valid. Check the app's clock and try again."]}
            )
        from datetime import UTC, datetime

        codes, hashes = mfa.new_recovery_codes()
        user.mfa_salt, user.mfa_pending_salt = user.mfa_pending_salt, None
        user.mfa_last_step = step
        user.mfa_enabled_at = datetime.now(UTC)
        user.mfa_recovery_codes = hashes
        audit_service.record("auth.mfa_enabled", "user", user.id, actor=user)
        db.session.commit()
        return {"data": {**_status(user), "recovery_codes": codes}}


def _confirm(user, data) -> None:
    """Password and a current second factor, for turning it off or new recovery codes."""
    from ...auth.passwords import verify_password

    if not verify_password(user.password_hash, data["password"]):
        raise ValidationError(details={"password": ["The password is incorrect."]})
    if mfa.verify_second_factor(user, data["code"]) is None:
        raise ValidationError(details={"code": ["That code isn't valid."]})


class MfaDisableResource(Resource):
    method_decorators = {"post": _sensitive_limit}

    @require_auth
    def post(self):
        user = current_user
        if not user.mfa_salt:
            return {"data": _status(user)}
        _confirm(user, _body("password", "code"))
        user.mfa_salt = user.mfa_pending_salt = user.mfa_enabled_at = None
        user.mfa_last_step = None
        user.mfa_recovery_codes = None
        audit_service.record("auth.mfa_disabled", "user", user.id, actor=user)
        db.session.commit()
        return {"data": _status(user)}


class MfaRecoveryCodesResource(Resource):
    """New recovery codes (the old ones stop working)."""

    method_decorators = {"post": _sensitive_limit}

    @require_auth
    def post(self):
        user = current_user
        if not user.mfa_salt:
            raise ConflictError("Turn on two-step sign-in first.")
        _confirm(user, _body("password", "code"))
        codes, hashes = mfa.new_recovery_codes()
        user.mfa_recovery_codes = hashes
        audit_service.record("auth.mfa_recovery_codes_replaced", "user", user.id, actor=user)
        db.session.commit()
        return {"data": {**_status(user), "recovery_codes": codes}}


def _site_name() -> str:
    from ...services.settings_service import get_values

    return str(get_values().get("site.name") or "Think Positive Always")[:60]


class RefreshResource(Resource):
    method_decorators = {"post": [limiter.limit(lambda: current_app.config["RATELIMIT_REFRESH"])]}

    def post(self):
        verify_jwt_in_request(refresh=True)
        user = current_user
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        rotate_session(user, get_jwt()["jti"], response)
        db.session.commit()
        return response


class LogoutResource(Resource):
    def post(self):
        # Works even when the access token has expired: the refresh cookie identifies the session.
        # Cookies are always cleared; the server-side session is revoked only when the refresh
        # token and its CSRF value verify.
        try:
            verify_jwt_in_request(refresh=True, optional=True)
            payload = get_jwt()
        except (JWTExtendedException, PyJWTError):
            payload = None
        if payload:
            revoke_refresh_token(payload["jti"])
            audit_service.record(
                "auth.logout",
                "user",
                payload.get("sub"),
                actor=current_user if current_user else None,
            )
            db.session.commit()
        response = jsonify({"data": {"logged_out": True}})
        clear_session_cookies(response)
        return response


class MeResource(Resource):
    @require_auth
    def get(self):
        return {"data": {"user": auth_service.user_payload(current_user)}}


class ChangePasswordResource(Resource):
    method_decorators = {"post": [limiter.limit(lambda: current_app.config["RATELIMIT_SENSITIVE"])]}

    @require_auth
    def post(self):
        data = load_body(_change_password)
        user = current_user
        auth_service.change_password(user, data["current_password"], data["new_password"])
        revoke_all_sessions(user)  # signs out every other device
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        issue_session(user, response)
        audit_service.record("auth.password_changed", "user", user.id, actor=user)
        db.session.commit()
        return response


# ---- token-based flows (no session; the emailed token authorises one action) --------

_sensitive = [limiter.limit(lambda: current_app.config["RATELIMIT_SENSITIVE"])]


class InvitationVerifyResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        token = load_body(TokenSchema())["token"]
        return {"data": account_tokens.describe(token, account_tokens.INVITATION)}


class InvitationAcceptResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        data = load_body(AcceptInvitationSchema())
        user = account_tokens.accept_invitation(
            data["token"], data["password"], data.get("display_name")
        )
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        issue_session(user, response)  # the new administrator is signed in immediately
        db.session.commit()
        return response


class PasswordResetVerifyResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        token = load_body(TokenSchema())["token"]
        return {"data": account_tokens.describe(token, account_tokens.PASSWORD_RESET)}


class PasswordResetCompleteResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        data = load_body(CompleteResetSchema())
        account_tokens.complete_password_reset(data["token"], data["password"])
        db.session.commit()
        response = jsonify({"data": {"reset": True}})
        clear_session_cookies(response)
        return response
