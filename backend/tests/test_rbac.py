import re

import pytest

from app.api.admin import ADMIN_ROUTES, PUBLIC_ADMIN_PATHS
from app.auth.permissions import ROLE_PERMISSIONS, Permission, RoleName
from app.extensions import db
from app.models import AuditLog, User

from .conftest import make_user


def _concrete(path: str) -> str:
    return re.sub(r"<(?:int|string):\w+>", "1", path)


@pytest.mark.parametrize("resource,path", ADMIN_ROUTES)
def test_every_admin_endpoint_requires_authentication(client, resource, path):
    if path in PUBLIC_ADMIN_PATHS:
        pytest.skip("authenticates with credentials or the refresh cookie")
    for method in ("get", "post", "patch", "put", "delete"):
        if not hasattr(resource, method):
            continue
        res = getattr(client, method)(f"/api/v1{_concrete(path)}", json={})
        assert res.status_code == 401, (method, path, res.get_json())


def test_permission_matrix_is_least_privilege():
    assert ROLE_PERMISSIONS[RoleName.SUPER_ADMIN] == frozenset(Permission)
    editor = ROLE_PERMISSIONS[RoleName.EDITOR]
    assert Permission.USERS_MANAGE not in editor and Permission.SETTINGS_MANAGE not in editor
    moderator = ROLE_PERMISSIONS[RoleName.MODERATOR]
    assert Permission.CONTENT_PUBLISH not in moderator and Permission.CONTENT_WRITE not in moderator
    analyst = ROLE_PERMISSIONS[RoleName.ANALYST]
    assert not {
        p for p in analyst if p.value.endswith((".write", ".publish", ".moderate", ".manage"))
    }


def test_super_admin_has_full_access(seeded, as_role):
    api = as_role("super_admin")
    for url in [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/users",
        "/api/v1/admin/settings",
        "/api/v1/admin/navigation",
        "/api/v1/admin/audit-log",
        "/api/v1/admin/roles",
    ]:
        assert api.get(url).status_code == 200, url


def test_editor_boundaries(seeded, as_role):
    api = as_role("editor")
    assert api.get("/api/v1/admin/articles").status_code == 200
    assert api.post("/api/v1/admin/tags", {"name": "Gratitude"}).status_code == 201
    for url in [
        "/api/v1/admin/users",
        "/api/v1/admin/settings",
        "/api/v1/admin/audit-log",
        "/api/v1/admin/navigation",
        "/api/v1/admin/roles",
    ]:
        assert api.get(url).status_code == 403, url
    assert api.patch("/api/v1/admin/settings", {"values": {"site.name": "X"}}).status_code == 403


def test_moderator_can_take_content_offline_but_not_publish_or_edit(seeded, as_role):
    api = as_role("moderator")
    assert api.get("/api/v1/admin/articles").status_code == 200
    assert api.post("/api/v1/admin/articles", {"title": "Nope"}).status_code == 403
    assert api.patch("/api/v1/admin/articles/1", {"title": "Changed"}).status_code == 403
    assert api.post("/api/v1/admin/articles/1/unpublish").status_code == 200
    assert api.post("/api/v1/admin/articles/1/publish").status_code == 403
    assert api.post("/api/v1/admin/topics", {"name": "X"}).status_code == 403
    assert api.get("/api/v1/admin/users").status_code == 403


def test_analyst_is_read_only(seeded, as_role):
    api = as_role("analyst")
    assert api.get("/api/v1/admin/dashboard").status_code == 200
    assert api.get("/api/v1/admin/articles").status_code == 200
    assert api.get("/api/v1/admin/dashboard").get_json()["data"]["recent_audit"] is None
    assert api.post("/api/v1/admin/articles", {"title": "Nope"}).status_code == 403
    assert api.post("/api/v1/admin/articles/1/archive").status_code == 403
    assert api.patch("/api/v1/admin/topics/1", {"name": "X"}).status_code == 403
    assert api.get("/api/v1/admin/pages").status_code == 403
    assert api.get("/api/v1/admin/audit-log").status_code == 403


def test_user_without_roles_has_no_access(app):
    make_user(app, "norole@example.org", ["analyst"])
    with app.app_context():
        user = db.session.scalar(db.select(User))
        user.role_links = []
        db.session.commit()
    client = app.test_client()
    client.post(
        "/api/v1/admin/auth/login",
        json={"email": "norole@example.org", "password": "Correct-Horse-Battery-9"},
    )
    assert client.get("/api/v1/admin/dashboard").status_code == 403


def test_role_changes_take_effect_immediately(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    editor_id = make_user(app, "writer@example.org", ["editor"])
    from .conftest import Api, login

    writer = Api(app.test_client())
    login(writer.c, "writer@example.org")
    assert writer.get("/api/v1/admin/articles").status_code == 200
    res = admin.patch(f"/api/v1/admin/users/{editor_id}", {"roles": ["analyst"]})
    assert res.status_code == 200 and res.get_json()["data"]["roles"] == ["analyst"]
    assert writer.post("/api/v1/admin/tags", {"name": "Hope"}).status_code == 403
    with app.app_context():
        entry = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "user.updated"))
        assert entry.details["roles"] == {"from": ["editor"], "to": ["analyst"]}


def test_privilege_escalation_is_blocked(app, as_role):
    editor = as_role("editor", email="ed@example.org")
    with app.app_context():
        editor_id = db.session.scalar(db.select(User.id).where(User.email == "ed@example.org"))
    assert (
        editor.patch(f"/api/v1/admin/users/{editor_id}", {"roles": ["super_admin"]}).status_code
        == 403
    )
    admin = as_role("super_admin", email="owner@example.org")
    bad = admin.post(
        "/api/v1/admin/users",
        {
            "email": "x@example.org",
            "display_name": "X",
            "password": "Another-Strong-Pass-1",
            "roles": ["root"],
        },
    )
    assert bad.status_code == 400


def test_last_super_admin_is_protected(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    with app.app_context():
        owner_id = db.session.scalar(db.select(User.id).where(User.email == "owner@example.org"))
    res = admin.patch(f"/api/v1/admin/users/{owner_id}", {"roles": ["editor"]})
    assert (
        res.status_code == 409
        and "last active super administrator" in res.get_json()["error"]["message"]
    )
    assert admin.patch(f"/api/v1/admin/users/{owner_id}", {"status": "disabled"}).status_code == 409

    second = admin.post(
        "/api/v1/admin/users",
        {
            "email": "two@example.org",
            "display_name": "Two",
            "password": "Another-Strong-Pass-1",
            "roles": ["super_admin"],
        },
    )
    assert second.status_code == 201
    second_id = second.get_json()["data"]["id"]
    # With two super admins, one may be changed — but never by disabling yourself.
    assert admin.patch(f"/api/v1/admin/users/{owner_id}", {"status": "disabled"}).status_code == 409
    assert (
        admin.patch(f"/api/v1/admin/users/{second_id}", {"status": "disabled"}).status_code == 200
    )
    assert admin.patch(f"/api/v1/admin/users/{owner_id}", {"roles": ["editor"]}).status_code == 409


def test_user_management(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    created = admin.post(
        "/api/v1/admin/users",
        {
            "email": "New@Example.org",
            "display_name": "New",
            "password": "Another-Strong-Pass-1",
            "roles": ["editor"],
        },
    )
    assert created.status_code == 201
    data = created.get_json()["data"]
    assert data["email"] == "new@example.org" and "password_hash" not in data
    dup = admin.post(
        "/api/v1/admin/users",
        {
            "email": "new@example.org",
            "display_name": "Dup",
            "password": "Another-Strong-Pass-1",
            "roles": ["editor"],
        },
    )
    assert dup.status_code == 409
    weak = admin.post(
        "/api/v1/admin/users",
        {"email": "w@example.org", "display_name": "W", "password": "weak", "roles": ["editor"]},
    )
    assert weak.status_code == 400
    reset = admin.post(
        f"/api/v1/admin/users/{data['id']}/password", {"password": "Reset-Strong-Pass-77"}
    )
    assert reset.status_code == 200
    users = admin.get("/api/v1/admin/users").get_json()["data"]
    assert {u["email"] for u in users} == {"owner@example.org", "new@example.org"}
    roles = admin.get("/api/v1/admin/roles").get_json()["data"]
    assert [r["name"] for r in roles] == ["super_admin", "editor", "moderator", "analyst"]
    with app.app_context():
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert {"user.created", "user.password_reset", "auth.login"} <= actions
        assert all(
            "Strong-Pass" not in str(d) for d in db.session.scalars(db.select(AuditLog.details))
        )
