from app.extensions import db
from app.models import AuditLog, RefreshToken, User

from .conftest import PASSWORD, csrf, login, make_user

ME = "/api/v1/admin/auth/me"


# ---- bootstrap -------------------------------------------------------------


def test_bootstrap_super_admin_cli(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["admin", "create-superadmin", "--email", "Owner@Example.org", "--name", "Owner"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "owner@example.org"))
        assert user.role_names == ["super_admin"]
        assert user.password_hash.startswith("scrypt:") and PASSWORD not in user.password_hash

    again = runner.invoke(
        args=["admin", "create-superadmin", "--email", "second@example.org", "--name", "Two"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert again.exit_code != 0 and "already exists" in again.output


def test_bootstrap_rejects_weak_password_and_supports_stdin(app):
    runner = app.test_cli_runner()
    weak = runner.invoke(
        args=[
            "admin",
            "create-superadmin",
            "--email",
            "a@example.org",
            "--name",
            "A",
            "--password-stdin",
        ],
        input="short\n",
    )
    assert weak.exit_code != 0 and "Password rejected" in weak.output
    ok = runner.invoke(
        args=[
            "admin",
            "create-superadmin",
            "--email",
            "a@example.org",
            "--name",
            "A",
            "--password-stdin",
        ],
        input=f"{PASSWORD}\n",
    )
    assert ok.exit_code == 0, ok.output


# ---- login -----------------------------------------------------------------------


def test_login_sets_httponly_cookies_and_returns_no_secrets(app, client):
    make_user(app, "editor@example.org", ["editor"])
    res = login(client, "EDITOR@example.org")
    assert res.status_code == 200
    body = res.get_json()["data"]["user"]
    assert body["email"] == "editor@example.org"
    assert "content.write" in body["permissions"] and "users.manage" not in body["permissions"]
    raw = res.get_data(as_text=True)
    assert "password" not in raw and "token" not in raw

    cookies = res.headers.getlist("Set-Cookie")
    access = next(c for c in cookies if c.startswith("access_token_cookie="))
    refresh = next(c for c in cookies if c.startswith("refresh_token_cookie="))
    assert "HttpOnly" in access and "HttpOnly" in refresh
    assert "Path=/api/" in access and "Path=/api/v1/admin/auth/" in refresh
    assert "SameSite=Strict" in access
    csrf_cookie = next(c for c in cookies if c.startswith("csrf_access_token="))
    assert "HttpOnly" not in csrf_cookie  # readable by the SPA for double-submit

    assert client.get(ME).get_json()["data"]["user"]["roles"] == ["editor"]
    with app.app_context():
        assert db.session.scalar(db.select(User.last_login_at)) is not None


def test_login_failures_are_generic(app, client):
    make_user(app, "editor@example.org", ["editor"])
    wrong = login(client, "editor@example.org", "Wrong-Password-123")
    unknown = login(client, "nobody@example.org", "Wrong-Password-123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()
    assert wrong.get_json()["error"]["message"] == "Invalid email or password."
    with app.app_context():
        failures = db.session.scalars(
            db.select(AuditLog).where(AuditLog.action == "auth.login_failed")
        ).all()
        assert len(failures) == 2
        assert all("Wrong-Password" not in str(f.details) for f in failures)


def test_disabled_users_cannot_log_in(app, client):
    make_user(app, "gone@example.org", ["editor"], status="disabled")
    res = login(client, "gone@example.org")
    assert res.status_code == 401
    assert res.get_json()["error"]["message"] == "Invalid email or password."


def test_disabling_a_user_ends_their_session(app, client):
    uid = make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    assert client.get(ME).status_code == 200
    with app.app_context():
        user = db.session.get(User, uid)
        user.status = "disabled"
        db.session.commit()
    assert client.get(ME).status_code == 401


def test_login_validation(client):
    assert client.post("/api/v1/admin/auth/login", json={"email": "x"}).status_code == 400
    assert client.post("/api/v1/admin/auth/login", data="nope").status_code == 400


# ---- refresh / logout ---------------------------------------------------------------


def _refresh(client):
    return client.post("/api/v1/admin/auth/refresh", headers=csrf(client, "refresh"))


def test_refresh_rotates_and_detects_reuse(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    old_refresh = client.get_cookie("refresh_token_cookie", path="/api/v1/admin/auth/").value
    old_csrf = client.get_cookie("csrf_refresh_token").value

    res = _refresh(client)
    assert res.status_code == 200
    assert (
        client.get_cookie("refresh_token_cookie", path="/api/v1/admin/auth/").value != old_refresh
    )

    # An attacker replaying the rotated token is rejected and every session is ended.
    thief = app.test_client()
    thief.set_cookie("refresh_token_cookie", old_refresh, path="/api/v1/admin/auth/")
    thief.set_cookie("csrf_refresh_token", old_csrf)
    replay = thief.post("/api/v1/admin/auth/refresh", headers={"X-CSRF-TOKEN": old_csrf})
    assert replay.status_code == 401
    assert client.get(ME).status_code == 401  # access token invalidated (session_version bumped)
    assert _refresh(client).status_code == 401
    with app.app_context():
        assert (
            db.session.scalar(
                db.select(db.func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 0
        )


def test_refresh_requires_csrf(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    res = client.post("/api/v1/admin/auth/refresh")
    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "csrf_failed"


def test_logout_revokes_refresh_token_and_clears_cookies(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    refresh_value = client.get_cookie("refresh_token_cookie", path="/api/v1/admin/auth/").value
    refresh_csrf = client.get_cookie("csrf_refresh_token").value
    res = client.post("/api/v1/admin/auth/logout", headers=csrf(client, "refresh"))
    assert res.status_code == 200
    assert client.get_cookie("access_token_cookie", path="/api/") is None
    assert client.get(ME).status_code == 401
    # The stolen refresh token cannot be used after logout.
    other = app.test_client()
    other.set_cookie("refresh_token_cookie", refresh_value, path="/api/v1/admin/auth/")
    other.set_cookie("csrf_refresh_token", refresh_csrf)
    assert (
        other.post("/api/v1/admin/auth/refresh", headers={"X-CSRF-TOKEN": refresh_csrf}).status_code
        == 401
    )


def test_logout_without_csrf_clears_cookies_but_keeps_server_session(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    res = client.post("/api/v1/admin/auth/logout")
    assert res.status_code == 200
    assert client.get_cookie("access_token_cookie", path="/api/") is None
    with app.app_context():
        assert (
            db.session.scalar(
                db.select(db.func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.revoked_at.is_(None))
            )
            == 1
        )


def test_logout_without_session_is_harmless(client):
    assert client.post("/api/v1/admin/auth/logout").status_code == 200


# ---- password change -------------------------------------------------------------------


def test_change_password(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    other_device = app.test_client()
    login(other_device, "editor@example.org")

    url = "/api/v1/admin/auth/change-password"
    bad = client.post(
        url,
        json={"current_password": "nope", "new_password": "New-Strong-Pass-42"},
        headers=csrf(client),
    )
    assert bad.status_code == 400 and "current_password" in bad.get_json()["error"]["details"]
    weak = client.post(
        url, json={"current_password": PASSWORD, "new_password": "short"}, headers=csrf(client)
    )
    assert weak.status_code == 400 and "new_password" in weak.get_json()["error"]["details"]

    ok = client.post(
        url,
        json={"current_password": PASSWORD, "new_password": "New-Strong-Pass-42"},
        headers=csrf(client),
    )
    assert ok.status_code == 200
    assert client.get(ME).status_code == 200  # this session continues with fresh cookies
    assert other_device.get(ME).status_code == 401  # other sessions are signed out
    assert login(app.test_client(), "editor@example.org").status_code == 401
    assert login(app.test_client(), "editor@example.org", "New-Strong-Pass-42").status_code == 200


def test_change_password_requires_csrf(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    res = client.post(
        "/api/v1/admin/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "New-Strong-Pass-42"},
    )
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "csrf_failed"


# ---- abuse protection --------------------------------------------------------------------


def test_login_is_rate_limited(app, client):
    make_user(app, "editor@example.org", ["editor"])
    statuses = [
        login(client, "editor@example.org", "Wrong-Password-1").status_code for _ in range(6)
    ]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert (
        client.post(
            "/api/v1/admin/auth/login", json={"email": "editor@example.org", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_untrusted_origin_is_rejected(app, client):
    make_user(app, "editor@example.org", ["editor"])
    res = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "editor@example.org", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403
    ok = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "editor@example.org", "password": PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert ok.status_code == 200


def test_admin_api_has_no_cors_and_no_cache(app, client):
    make_user(app, "editor@example.org", ["editor"])
    login(client, "editor@example.org")
    res = client.get(ME, headers={"Origin": "http://localhost:5173"})
    assert "Access-Control-Allow-Origin" not in res.headers
    assert res.headers["Cache-Control"] == "no-store"
