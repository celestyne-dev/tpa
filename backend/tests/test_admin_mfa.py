"""Two-step sign-in (TOTP) for administrators: enrolment, the second login step, replay
protection, recovery codes, turning it off, enforcement and the server-side reset."""

from __future__ import annotations

from click.testing import CliRunner
from sqlalchemy import select
from sqlalchemy.orm import undefer_group

from app.auth import mfa
from app.extensions import db, limiter
from app.models import AuditLog, SiteSetting, User

from .conftest import PASSWORD, Api, csrf, login, make_user

EMAIL = "owner@example.org"
MFA = "/api/v1/admin/auth/mfa"


def _user(app, email=EMAIL):
    with app.app_context():
        user = db.session.scalar(
            select(User).where(User.email == email).options(undefer_group("mfa"))
        )
        db.session.expunge(user)
        return user


def _code(app, *, offset=0, salt_field="mfa_salt", email=EMAIL):
    """The authenticator app's current code for this account."""
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == email))
        salt = getattr(user, salt_field)
        return mfa.code_at(mfa._secret(user.id, salt), mfa.current_step() + offset)


def _enrol(app, client):
    api = Api(client)
    setup = api.post(f"{MFA}/setup").get_json()["data"]
    res = api.post(f"{MFA}/enable", {"code": _code(app, salt_field="mfa_pending_salt")})
    assert res.status_code == 200, res.get_json()
    return setup, res.get_json()["data"]


def _signed_in(app):
    make_user(app, EMAIL, ["super_admin"])
    client = app.test_client()
    assert login(client, EMAIL).status_code == 200
    return client


def test_totp_matches_the_rfc_6238_test_vector():
    secret = b"12345678901234567890"
    # RFC 6238 appendix B (SHA-1): T=59 -> 94287082, T=1111111109 -> 07081804 (8 digits).
    assert mfa.code_at(secret, 59 // 30) == "287082"
    assert mfa.code_at(secret, 1111111109 // 30) == "081804"


def test_enrolment_returns_a_setup_key_then_recovery_codes_once(app):
    client = _signed_in(app)
    api = Api(client)
    assert api.get(MFA).get_json()["data"]["enabled"] is False
    setup, enabled = _enrol(app, client)
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert "secret=" in setup["otpauth_uri"] and "issuer=" in setup["otpauth_uri"]
    assert len(setup["setup_key"].replace(" ", "")) == 32  # 160-bit base32
    assert enabled["enabled"] is True and len(enabled["recovery_codes"]) == 10
    user = _user(app)
    # Only salts and hashes are stored: never the secret or the recovery codes.
    assert user.mfa_salt and user.mfa_pending_salt is None
    stored = " ".join(user.mfa_recovery_codes)
    assert not any(code in stored for code in enabled["recovery_codes"])
    assert setup["setup_key"].replace(" ", "") not in str(user.__dict__)
    # Status never shows the codes again; a second setup is refused.
    status = api.get(MFA).get_json()["data"]
    assert status["recovery_codes_left"] == 10 and "recovery_codes" not in status
    assert api.post(f"{MFA}/setup").status_code == 409
    with app.app_context():
        assert db.session.scalar(select(AuditLog).where(AuditLog.action == "auth.mfa_enabled"))


def test_a_wrong_code_does_not_enable(app):
    client = _signed_in(app)
    api = Api(client)
    api.post(f"{MFA}/setup")
    res = api.post(f"{MFA}/enable", {"code": "000000"})
    assert res.status_code == 400 and "code" in res.get_json()["error"]["details"]
    assert _user(app).mfa_salt is None


def test_sign_in_needs_the_second_step_and_codes_cannot_be_replayed(app):
    client = _signed_in(app)
    _enrol(app, client)
    fresh = app.test_client()
    res = login(fresh, EMAIL)
    body = res.get_json()["data"]
    assert res.status_code == 200 and body["mfa_required"] is True and "user" not in body
    # No session yet: no cookies, no access.
    assert fresh.get_cookie("access_token_cookie") is None
    assert fresh.get("/api/v1/admin/auth/me").status_code == 401
    # The code used during enrolment can't be used again.
    used = _code(app)
    res = fresh.post(f"{MFA}/verify", json={"mfa_token": body["mfa_token"], "code": used})
    assert res.status_code == 401
    code = _code(app, offset=1)  # the next step (within the allowed clock drift)
    res = fresh.post(f"{MFA}/verify", json={"mfa_token": body["mfa_token"], "code": code})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["data"]["user"]["mfa_enabled"] is True
    assert fresh.get("/api/v1/admin/auth/me").status_code == 200
    # Replaying the same code (e.g. intercepted) fails.
    other = app.test_client()
    token = login(other, EMAIL).get_json()["data"]["mfa_token"]
    assert other.post(f"{MFA}/verify", json={"mfa_token": token, "code": code}).status_code == 401


def test_challenge_tokens_are_short_lived_and_bound_to_the_session_version(app):
    client = _signed_in(app)
    _enrol(app, client)
    token = login(app.test_client(), EMAIL).get_json()["data"]["mfa_token"]
    for bad in ("", "not-a-token", token[:-2] + "xx"):
        res = app.test_client().post(f"{MFA}/verify", json={"mfa_token": bad, "code": "123456"})
        assert res.status_code == 401
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == EMAIL))
        user.session_version += 1  # e.g. password changed meanwhile
        db.session.commit()
    res = app.test_client().post(
        f"{MFA}/verify", json={"mfa_token": token, "code": _code(app, offset=1)}
    )
    assert res.status_code == 401


def test_recovery_codes_work_once(app):
    client = _signed_in(app)
    _setup, enabled = _enrol(app, client)
    recovery = enabled["recovery_codes"][0]
    for attempt in (recovery.upper(), recovery):
        c = app.test_client()
        token = login(c, EMAIL).get_json()["data"]["mfa_token"]
        res = c.post(f"{MFA}/verify", json={"mfa_token": token, "code": attempt})
        if attempt == recovery.upper():
            assert res.status_code == 200  # case and dashes don't matter
        else:
            assert res.status_code == 401  # already used
    assert len(_user(app).mfa_recovery_codes) == 9


def test_second_step_is_rate_limited(app):
    client = _signed_in(app)
    _enrol(app, client)
    was_enabled = limiter.enabled
    limiter.enabled = True
    try:
        c = app.test_client()
        token = login(c, EMAIL).get_json()["data"]["mfa_token"]
        codes = [
            c.post(f"{MFA}/verify", json={"mfa_token": token, "code": "000000"}).status_code
            for _ in range(7)
        ]
    finally:
        limiter.enabled = was_enabled
        limiter.reset()
    assert codes[0] == 401 and 429 in codes


def test_turning_it_off_needs_the_password_and_a_code(app):
    client = _signed_in(app)
    _enrol(app, client)
    api = Api(client)
    assert (
        api.post(f"{MFA}/disable", {"password": "wrong", "code": _code(app, offset=1)}).status_code
        == 400
    )
    assert api.post(f"{MFA}/disable", {"password": PASSWORD, "code": "000000"}).status_code == 400
    res = api.post(f"{MFA}/disable", {"password": PASSWORD, "code": _code(app, offset=1)})
    assert res.status_code == 200 and res.get_json()["data"]["enabled"] is False
    user = _user(app)
    assert user.mfa_salt is None and user.mfa_recovery_codes is None
    assert login(app.test_client(), EMAIL).get_json()["data"]["user"]["email"] == EMAIL


def test_new_recovery_codes_replace_the_old_ones(app):
    client = _signed_in(app)
    _setup, enabled = _enrol(app, client)
    api = Api(client)
    res = api.post(
        f"{MFA}/recovery-codes", {"password": PASSWORD, "code": enabled["recovery_codes"][1]}
    )
    assert res.status_code == 200
    new = res.get_json()["data"]["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(enabled["recovery_codes"])


def test_enforcement_limits_unenrolled_admins_to_their_security_page(app):
    client = _signed_in(app)
    api = Api(client)
    assert api.get("/api/v1/admin/dashboard").status_code == 200
    with app.app_context():
        db.session.add(SiteSetting(key="security.require_admin_mfa", value=True))
        db.session.commit()
    res = api.get("/api/v1/admin/dashboard")
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "mfa_enrollment_required"
    me = api.get("/api/v1/admin/auth/me").get_json()["data"]["user"]
    assert me["mfa_required"] is True and me["mfa_enabled"] is False
    _enrol(app, client)
    assert api.get("/api/v1/admin/dashboard").status_code == 200
    # Signed-out requests still get 401 (not a hint about enforcement).
    assert app.test_client().get("/api/v1/admin/dashboard").status_code == 401


def test_server_reset_command_turns_it_off_and_signs_out(app):
    client = _signed_in(app)
    _enrol(app, client)
    runner = CliRunner()
    from app.cli import reset_mfa

    with app.app_context():
        result = runner.invoke(reset_mfa, [EMAIL, "--yes"])
    assert result.exit_code == 0, result.output
    assert _user(app).mfa_salt is None
    assert client.get("/api/v1/admin/auth/me", headers=csrf(client)).status_code == 401
    with app.app_context():
        log = db.session.scalar(select(AuditLog).where(AuditLog.action == "auth.mfa_reset"))
        assert log.details == {"by": "server command"}
