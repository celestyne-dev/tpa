import re
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import AccountToken, AuditLog, User
from app.services.mail import MemoryBackend

from .conftest import Api, csrf, login

NEW_PASSWORD = "Fresh-Invitee-Pass-42"


def _token_from_outbox():
    message = MemoryBackend.outbox[-1]
    match = re.search(r"#token=([A-Za-z0-9_\-]+)", message.text)
    assert match, message.text
    return match.group(1)


def _invite(api, email="new.editor@example.org", roles=("editor",), name="New Editor"):
    res = api.post(
        "/api/v1/admin/invitations", {"email": email, "display_name": name, "roles": list(roles)}
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def test_invitation_is_delivered_and_token_never_exposed(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    res = admin.post(
        "/api/v1/admin/invitations",
        {"email": "New.Editor@Example.org", "display_name": "New Editor", "roles": ["editor"]},
    )
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["email"] == "new.editor@example.org"
    assert data["status"] == "pending" and data["delivery"] == "memory"
    token = _token_from_outbox()
    raw = res.get_data(as_text=True)
    assert token not in raw and "token_hash" not in raw
    assert "/admin/activate#token=" in MemoryBackend.outbox[-1].text

    listed = admin.get("/api/v1/admin/invitations").get_data(as_text=True)
    assert token not in listed
    with app.app_context():
        record = db.session.scalar(db.select(AccountToken))
        assert record.token_hash != token and len(record.token_hash) == 64
        logs = " ".join(str(d) for d in db.session.scalars(db.select(AuditLog.details)))
        assert token not in logs


def test_activation_creates_account_and_signs_in(app, as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    _invite(admin)
    token = _token_from_outbox()

    info = client.post("/api/v1/admin/auth/invitation/verify", json={"token": token})
    assert info.status_code == 200
    assert info.get_json()["data"]["email"] == "new.editor@example.org"
    assert info.get_json()["data"]["roles"] == ["editor"]

    weak = client.post(
        "/api/v1/admin/auth/invitation/accept", json={"token": token, "password": "short"}
    )
    assert weak.status_code == 400 and "password" in weak.get_json()["error"]["details"]

    res = client.post(
        "/api/v1/admin/auth/invitation/accept",
        json={"token": token, "password": NEW_PASSWORD, "display_name": "Ngozi"},
    )
    assert res.status_code == 200
    user = res.get_json()["data"]["user"]
    assert user["roles"] == ["editor"] and user["display_name"] == "Ngozi"
    assert user["email_verified_at"]
    assert client.get("/api/v1/admin/auth/me").status_code == 200  # signed in via cookies
    assert login(app.test_client(), "new.editor@example.org", NEW_PASSWORD).status_code == 200

    statuses = [i["status"] for i in admin.get("/api/v1/admin/invitations").get_json()["data"]]
    assert statuses == ["accepted"]


def test_tokens_are_single_use(as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    _invite(admin)
    token = _token_from_outbox()
    first = client.post(
        "/api/v1/admin/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD}
    )
    assert first.status_code == 200
    replay = client.post(
        "/api/v1/admin/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD}
    )
    assert replay.status_code == 400 and replay.get_json()["error"]["code"] == "link_invalid"
    assert (
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": token}).status_code
        == 400
    )


def test_expired_revoked_and_unknown_tokens_are_rejected(app, as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    invite = _invite(admin, email="late@example.org")
    expired_token = _token_from_outbox()
    with app.app_context():
        record = db.session.get(AccountToken, invite["id"])
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    res = client.post(
        "/api/v1/admin/auth/invitation/accept",
        json={"token": expired_token, "password": NEW_PASSWORD},
    )
    assert res.status_code == 400
    assert (
        admin.get("/api/v1/admin/invitations?status=expired").get_json()["data"][0]["email"]
        == "late@example.org"
    )

    second = _invite(admin, email="revoked@example.org")
    revoked_token = _token_from_outbox()
    assert admin.post(f"/api/v1/admin/invitations/{second['id']}/revoke").status_code == 200
    assert (
        client.post(
            "/api/v1/admin/auth/invitation/accept",
            json={"token": revoked_token, "password": NEW_PASSWORD},
        ).status_code
        == 400
    )
    assert admin.post(f"/api/v1/admin/invitations/{second['id']}/revoke").status_code == 409

    for bogus in ["x" * 43, "short", ""]:
        assert (
            client.post("/api/v1/admin/auth/invitation/verify", json={"token": bogus}).status_code
            == 400
        )
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 1


def test_resend_rotates_token_and_new_invite_replaces_old(as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    invite = _invite(admin)
    old = _token_from_outbox()
    assert admin.post(f"/api/v1/admin/invitations/{invite['id']}/resend").status_code == 200
    new = _token_from_outbox()
    assert new != old
    assert (
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": old}).status_code == 400
    )
    assert (
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": new}).status_code == 200
    )

    _invite(admin)  # re-invite same email: previous invitation is revoked
    newest = _token_from_outbox()
    assert (
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": new}).status_code == 400
    )
    assert (
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": newest}).status_code
        == 200
    )


def test_invitation_validation(as_role):
    admin = as_role("super_admin", email="owner@example.org")
    assert (
        admin.post(
            "/api/v1/admin/invitations", {"email": "owner@example.org", "roles": ["editor"]}
        ).status_code
        == 409
    )
    assert (
        admin.post("/api/v1/admin/invitations", {"email": "bad", "roles": ["editor"]}).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/v1/admin/invitations", {"email": "x@example.org", "roles": ["root"]}
        ).status_code
        == 400
    )
    assert (
        admin.post("/api/v1/admin/invitations", {"email": "x@example.org", "roles": []}).status_code
        == 400
    )


def test_invitations_require_user_management_permission(seeded, as_role, client):
    editor = as_role("editor")
    assert editor.get("/api/v1/admin/invitations").status_code == 403
    assert (
        editor.post(
            "/api/v1/admin/invitations", {"email": "x@example.org", "roles": ["editor"]}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/invitations").status_code == 401


def test_invitation_refused_when_email_not_configured(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    app.config["MAIL_BACKEND"] = "none"
    res = admin.post("/api/v1/admin/invitations", {"email": "x@example.org", "roles": ["editor"]})
    assert res.status_code == 503 and res.get_json()["error"]["code"] == "email_not_configured"
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(AccountToken.id))) == 0


def test_console_backend_is_never_used_in_production(app):
    from app.services import mail

    with app.app_context():
        app.config["MAIL_BACKEND"] = "console"
        app.config["ENV_NAME"] = "production"
        assert isinstance(mail.get_backend(), mail.NullBackend)


def test_production_config_rejects_dev_mail_backends(monkeypatch):
    from app import create_app

    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("MAIL_BACKEND", "console")
    from app.config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    with pytest.raises(RuntimeError, match="MAIL_BACKEND"):
        create_app("production")


def test_smtp_backend_sends_via_starttls(app, monkeypatch):
    from app.services import mail

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, msg):
            sent["to"] = msg["To"]

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    with app.app_context():
        app.config.update(
            MAIL_BACKEND="smtp",
            MAIL_SMTP_HOST="smtp.example.org",
            MAIL_SMTP_USERNAME="mailer",
            MAIL_SMTP_PASSWORD="pw",
        )
        assert mail.send(mail.EmailMessage("a@example.org", "Hi", "Body")) == "smtp"
    assert sent == {
        "host": ("smtp.example.org", 587),
        "tls": True,
        "login": "mailer",
        "to": "a@example.org",
    }


def test_token_endpoints_are_rate_limited(client):
    codes = [
        client.post("/api/v1/admin/auth/invitation/verify", json={"token": "x" * 43}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [400] * 10 and codes[10] == 429


# ---- password reset links --------------------------------------------------------------


def test_admin_triggered_password_reset(app, as_role, client):
    from .conftest import make_user

    admin = as_role("super_admin", email="owner@example.org")
    uid = make_user(app, "writer@example.org", ["editor"])
    writer = app.test_client()
    login(writer, "writer@example.org")

    res = admin.post(f"/api/v1/admin/users/{uid}/password-reset")
    assert res.status_code == 201 and res.get_json()["data"]["purpose"] == "password_reset"
    token = _token_from_outbox()
    assert "/admin/reset-password#token=" in MemoryBackend.outbox[-1].text
    assert token not in res.get_data(as_text=True)

    assert (
        client.post("/api/v1/admin/auth/password-reset/verify", json={"token": token}).get_json()[
            "data"
        ]["email"]
        == "writer@example.org"
    )
    done = client.post(
        "/api/v1/admin/auth/password-reset/complete",
        json={"token": token, "password": "Brand-New-Secure-Pass-7"},
    )
    assert done.status_code == 200
    assert writer.get("/api/v1/admin/auth/me").status_code == 401  # old sessions ended
    assert (
        login(app.test_client(), "writer@example.org", "Brand-New-Secure-Pass-7").status_code == 200
    )
    assert (
        client.post(
            "/api/v1/admin/auth/password-reset/complete",
            json={"token": token, "password": "Another-New-Pass-88"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/admin/auth/invitation/accept", json={"token": token, "password": NEW_PASSWORD}
        ).status_code
        == 400
    )


def test_disabling_an_account_revokes_its_reset_links(app, as_role, client):
    from .conftest import make_user

    admin = as_role("super_admin", email="owner@example.org")
    uid = make_user(app, "writer@example.org", ["editor"])
    admin.post(f"/api/v1/admin/users/{uid}/password-reset")
    token = _token_from_outbox()
    assert admin.patch(f"/api/v1/admin/users/{uid}", {"status": "disabled"}).status_code == 200
    assert (
        client.post(
            "/api/v1/admin/auth/password-reset/complete",
            json={"token": token, "password": "Brand-New-Secure-Pass-7"},
        ).status_code
        == 400
    )
    assert admin.post(f"/api/v1/admin/users/{uid}/password-reset").status_code == 409
    reactivated = admin.patch(f"/api/v1/admin/users/{uid}", {"status": "active"})
    assert reactivated.status_code == 200 and reactivated.get_json()["data"]["status"] == "active"
    with app.app_context():
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert {"user.disabled", "user.reactivated", "user.password_reset_requested"} <= actions


def test_token_endpoints_do_not_require_csrf_but_check_origin(as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    _invite(admin)
    token = _token_from_outbox()
    res = client.post(
        "/api/v1/admin/auth/invitation/verify",
        json={"token": token},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_user_list_filters_and_detail(app, as_role):
    from .conftest import make_user

    admin = as_role("super_admin", email="owner@example.org")
    make_user(app, "writer@example.org", ["editor"], name="Writer One")
    make_user(app, "gone@example.org", ["analyst"], status="disabled")
    emails = lambda q: [u["email"] for u in admin.get(f"/api/v1/admin/users{q}").get_json()["data"]]  # noqa: E731
    assert emails("?q=writer") == ["writer@example.org"]
    assert emails("?status=disabled") == ["gone@example.org"]
    assert emails("?role=super_admin") == ["owner@example.org"]
    assert admin.get("/api/v1/admin/users?status=weird").status_code == 400

    with app.app_context():
        owner_id = db.session.scalar(db.select(User.id).where(User.email == "owner@example.org"))
    detail = admin.get(f"/api/v1/admin/users/{owner_id}").get_json()["data"]
    assert detail["is_last_super_admin"] is True
    assert detail["recent_activity"][0]["action"] == "auth.login"
    assert "password_hash" not in str(detail)
    perms = admin.get("/api/v1/admin/permissions").get_json()["data"]
    flat = {p["key"]: p for g in perms for p in g["permissions"]}
    assert flat["topics.manage"]["available"] is True
    assert flat["roles.manage"]["sensitive"] is True
    assert flat["products.manage"]["available"] is False
    roles = admin.get("/api/v1/admin/roles").get_json()["data"]
    assert roles[0]["label"] == "Super Admin"


def test_new_admin_session_flow_end_to_end(as_role, client):
    """Invite → activate → use permissions → disabled account loses access immediately."""
    admin = as_role("super_admin", email="owner@example.org")
    _invite(admin, email="mod@example.org", roles=("moderator",))
    token = _token_from_outbox()
    res = client.post(
        "/api/v1/admin/auth/invitation/accept",
        json={"token": token, "password": NEW_PASSWORD, "display_name": "Mo"},
    )
    uid = res.get_json()["data"]["user"]["id"]
    moderator = Api(client)
    assert moderator.get("/api/v1/admin/articles").status_code == 200
    assert moderator.post("/api/v1/admin/tags", {"name": "x"}).status_code == 403
    admin.patch(f"/api/v1/admin/users/{uid}", {"status": "disabled"})
    assert client.get("/api/v1/admin/auth/me").status_code == 401
    assert (
        client.post("/api/v1/admin/auth/refresh", headers=csrf(client, "refresh")).status_code
        == 401
    )
