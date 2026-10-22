from flask import current_app, jsonify, request
from flask_jwt_extended import current_user, get_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_restful import Resource
from jwt.exceptions import PyJWTError

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
from ...utils.errors import AuthenticationError
from .._validation import load_body

_login = LoginSchema()
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
        response = jsonify({"data": {"user": auth_service.user_payload(user)}})
        issue_session(user, response)
        audit_service.record("auth.login", "user", user.id, actor=user)
        db.session.commit()
        return response


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
