"""Dynamic roles, granular permissions and their safeguards."""

from app.auth.permissions import (
    AVAILABLE_PERMISSIONS,
    SENSITIVE_PERMISSIONS,
    TEMPLATE_ROLES,
)
from app.auth.rbac import effective_permissions, sync_rbac
from app.extensions import db
from app.models import Article, AuditLog, Role, User
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Api, login, make_user

ROLES = "/api/v1/admin/roles"


def _role_id(app, name):
    with app.app_context():
        return db.session.scalar(db.select(Role.id).where(Role.name == name))


def _user(app, email):
    return db.session.scalar(db.select(User).where(User.email == email))


def _client(app, email):
    api = Api(app.test_client())
    assert login(api.c, email).status_code == 200
    return api


# ---- catalogue, templates and built-ins -------------------------------------------


def test_templates_are_seeded_with_available_non_sensitive_permissions_only(app):
    with app.app_context():
        roles = {r.name: r for r in db.session.scalars(db.select(Role))}
        assert {"super_admin", "editor", "moderator", "analyst"} <= set(roles)
        for spec in TEMPLATE_ROLES:
            role = roles[spec.key]
            assert role.kind == "template" and role.is_active and not role.grants_all
            assert role.permission_keys <= AVAILABLE_PERMISSIONS
            assert not role.permission_keys & SENSITIVE_PERMISSIONS
        # Future-module templates only reach the dashboard until their modules exist.
        for key in ("product_manager", "orders_manager", "finance_manager", "affiliate_manager"):
            assert roles[key].permission_keys == {"dashboard.view"}
        assert sum(r.grants_all for r in roles.values()) == 1


def test_sync_is_idempotent_and_keeps_template_edits(app):
    with app.app_context():
        assert set(sync_rbac().values()) == {0}
        writer = db.session.scalar(db.select(Role).where(Role.name == "content_writer"))
        writer.permissions = [p for p in writer.permissions if p.key != "media.view"]
        editor = db.session.scalar(db.select(Role).where(Role.name == "editor"))
        editor.permissions = []  # system roles are always restored from code
        db.session.commit()
        counts = sync_rbac()
        db.session.commit()
        assert counts["system_roles_reset"] == 1
        assert "media.view" not in writer.permission_keys
        assert "articles.publish" in editor.permission_keys


def test_sync_strips_sensitive_or_unavailable_grants_from_custom_roles(app):
    from app.models import PermissionDefinition

    with app.app_context():
        perms = {p.key: p for p in db.session.scalars(db.select(PermissionDefinition))}
        rogue = Role(name="rogue", label="Rogue", kind="custom", grants_all=True)
        rogue.permissions = [perms["roles.manage"], perms["products.manage"], perms["tags.manage"]]
        db.session.add(rogue)
        db.session.commit()
        sync_rbac()
        db.session.commit()
        assert rogue.permission_keys == {"tags.manage"} and rogue.grants_all is False


def test_permission_catalogue_flags(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    groups = admin.get("/api/v1/admin/permissions").get_json()["data"]
    flat = {p["key"]: p for g in groups for p in g["permissions"]}
    assert flat["articles.edit_own"]["available"] and not flat["articles.edit_own"]["sensitive"]
    assert flat["payments.configure"]["sensitive"] and not flat["payments.configure"]["available"]
    assert flat["orders.view"]["available"] is False
    assert {g["name"] for g in groups} >= {"Articles", "Users, roles & audit"}


# ---- role management API -----------------------------------------------------------


def test_super_admin_creates_edits_and_deletes_a_custom_role(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    res = admin.post(
        ROLES,
        {
            "label": "Guest Reviewer",
            "description": "Reads drafts",
            "permissions": ["articles.view", "dashboard.view"],
        },
    )
    assert res.status_code == 201, res.get_json()
    role = res.get_json()["data"]
    assert role["name"] == "guest_reviewer" and role["kind"] == "custom"
    assert role["permissions"] == ["articles.view", "dashboard.view"]
    assert admin.post(ROLES, {"label": "guest reviewer"}).status_code == 409

    res = admin.patch(
        f"{ROLES}/{role['id']}",
        {"permissions": ["articles.view", "analytics.view"], "label": "Reviewer"},
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["permissions"] == ["analytics.view", "articles.view"]
    assert admin.delete(f"{ROLES}/{role['id']}").status_code == 200
    assert admin.get(f"{ROLES}/{role['id']}").status_code == 404
    with app.app_context():
        actions = list(db.session.scalars(db.select(AuditLog.action).order_by(AuditLog.id)))
        assert {"role.created", "role.updated", "role.deleted"} <= set(actions)
        updated = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "role.updated"))
        assert updated.details["permissions"] == {
            "added": ["analytics.view"],
            "removed": ["dashboard.view"],
        }


def test_sensitive_unavailable_and_unknown_permissions_are_rejected(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    for perms in (
        ["roles.manage"],
        ["roles.assign"],
        ["payments.configure"],
        ["settings.security"],
    ):
        res = admin.post(ROLES, {"label": f"Bad {perms[0]}", "permissions": perms})
        assert res.status_code == 400 and "protected" in str(res.get_json()), perms
    res = admin.post(ROLES, {"label": "Shop", "permissions": ["products.manage"]})
    assert res.status_code == 400 and "not available" in str(res.get_json())
    res = admin.post(ROLES, {"label": "Nope", "permissions": ["everything.do"]})
    assert res.status_code == 400
    # grants_all / kind are not writable fields.
    assert admin.post(ROLES, {"label": "Root", "grants_all": True}).status_code == 400
    assert admin.post(ROLES, {"label": "Sys", "kind": "system"}).status_code == 400


def test_built_in_roles_cannot_be_changed_or_deleted(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    for name in ("super_admin", "editor", "moderator", "analyst"):
        role_id = _role_id(app, name)
        assert admin.patch(f"{ROLES}/{role_id}", {"permissions": []}).status_code == 403
        assert admin.patch(f"{ROLES}/{role_id}", {"is_active": False}).status_code == 403
        assert admin.delete(f"{ROLES}/{role_id}").status_code == 403
    with app.app_context():
        super_admin = db.session.scalar(db.select(Role).where(Role.name == "super_admin"))
        assert super_admin.is_active and super_admin.grants_all


def test_templates_are_editable(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    role_id = _role_id(app, "content_writer")
    res = admin.patch(f"{ROLES}/{role_id}", {"description": "Writes drafts for review."})
    assert res.status_code == 200 and res.get_json()["data"]["kind"] == "template"


def test_only_super_admin_can_manage_roles(app, as_role):
    make_user(app, "admin@example.org", ["administrator"])
    administrator = _client(app, "admin@example.org")
    # Administrators can read roles (users.view) but not change them.
    assert administrator.get(ROLES).status_code == 200
    assert administrator.post(ROLES, {"label": "Mine"}).status_code == 403
    role_id = _role_id(app, "content_writer")
    assert administrator.patch(f"{ROLES}/{role_id}", {"permissions": []}).status_code == 403
    assert administrator.delete(f"{ROLES}/{role_id}").status_code == 403
    editor = as_role("editor")
    assert editor.get(ROLES).status_code == 403
    assert editor.get("/api/v1/admin/permissions").status_code == 403


def test_role_in_use_cannot_be_deleted_but_can_be_deactivated(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    role = admin.post(ROLES, {"label": "Tagger", "permissions": ["tags.manage"]}).get_json()["data"]
    member_id = make_user(app, "tagger@example.org", ["tagger"])
    tagger = _client(app, "tagger@example.org")
    assert tagger.post("/api/v1/admin/tags", {"name": "Focus"}).status_code == 201

    res = admin.delete(f"{ROLES}/{role['id']}")
    assert res.status_code == 409 and "1 user(s)" in res.get_json()["error"]["message"]
    assert admin.get(f"{ROLES}/{role['id']}").get_json()["data"]["users"][0]["id"] == member_id

    assert admin.patch(f"{ROLES}/{role['id']}", {"is_active": False}).status_code == 200
    # Deactivation applies on the very next request.
    assert tagger.post("/api/v1/admin/tags", {"name": "Calm"}).status_code == 403
    # An inactive role cannot be newly assigned...
    other = make_user(app, "other@example.org", ["analyst"])
    res = admin.patch(f"/api/v1/admin/users/{other}", {"roles": ["analyst", "tagger"]})
    assert res.status_code == 400 and "Inactive" in str(res.get_json())
    # ...but members keep it (dormant) when their other roles are edited.
    res = admin.patch(f"/api/v1/admin/users/{member_id}", {"roles": ["tagger", "analyst"]})
    assert res.status_code == 200
    assert admin.patch(f"{ROLES}/{role['id']}", {"is_active": True}).status_code == 200
    assert tagger.post("/api/v1/admin/tags", {"name": "Calm"}).status_code == 201


def test_role_referenced_by_pending_invitation_cannot_be_deleted(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    role = admin.post(ROLES, {"label": "Tagger", "permissions": ["tags.manage"]}).get_json()["data"]
    invite = admin.post(
        "/api/v1/admin/invitations", {"email": "invitee@example.org", "roles": ["tagger"]}
    )
    assert invite.status_code == 201
    res = admin.delete(f"{ROLES}/{role['id']}")
    assert res.status_code == 409 and "1 pending invitation" in res.get_json()["error"]["message"]

    # Deactivating the role blocks acceptance instead of silently dropping it.
    assert admin.patch(f"{ROLES}/{role['id']}", {"is_active": False}).status_code == 200
    token = MemoryBackend.outbox[-1].text.split("#token=")[1].split()[0]
    res = app.test_client().post(
        "/api/v1/admin/auth/invitation/accept",
        json={"token": token, "password": PASSWORD, "display_name": "Invitee"},
    )
    assert res.status_code == 409
    with app.app_context():
        assert _user(app, "invitee@example.org") is None
    admin.post(f"/api/v1/admin/invitations/{invite.get_json()['data']['id']}/revoke")
    assert admin.delete(f"{ROLES}/{role['id']}").status_code == 200


# ---- multiple roles and effective permissions --------------------------------------


def test_multiple_roles_resolve_to_the_union_of_active_roles(app, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    uid = make_user(app, "multi@example.org", ["content_writer", "seo_manager"])
    with app.app_context():
        user = db.session.get(User, uid)
        perms = effective_permissions(user)
        assert {"articles.create", "articles.edit_own", "seo.manage", "pages.view"} <= perms
        assert "articles.edit_any" not in perms and "articles.publish" not in perms
    me = _client(app, "multi@example.org").get("/api/v1/admin/auth/me").get_json()["data"]["user"]
    assert me["roles"] == ["content_writer", "seo_manager"] and "seo.manage" in me["permissions"]
    res = admin.patch(f"/api/v1/admin/users/{uid}", {"roles": ["content_writer"]})
    assert res.status_code == 200 and "seo.manage" not in res.get_json()["data"]["permissions"]


def test_settings_are_split_by_permission(seeded, as_role):
    make_user(seeded, "seo@example.org", ["seo_manager"])
    seo = _client(seeded, "seo@example.org")
    groups = seo.get("/api/v1/admin/settings").get_json()["data"]["groups"]
    assert [g["name"] for g in groups] == ["SEO defaults"]
    key = groups[0]["settings"][0]["key"]
    value = "Think Positive Always - practical growth"
    assert seo.patch("/api/v1/admin/settings", {"values": {key: value}}).status_code == 200
    res = seo.patch("/api/v1/admin/settings", {"values": {"site.name": "Changed"}})
    assert res.status_code == 403


def test_future_module_templates_reach_no_operational_endpoints(seeded, as_role):
    make_user(seeded, "pm@example.org", ["product_manager"])
    pm = _client(seeded, "pm@example.org")
    assert pm.get("/api/v1/admin/dashboard").status_code == 200
    dashboard = pm.get("/api/v1/admin/dashboard").get_json()["data"]
    assert dashboard["articles"] is None and dashboard["recent_articles"] is None
    for url in (
        "/api/v1/admin/articles",
        "/api/v1/admin/users",
        "/api/v1/admin/settings",
        "/api/v1/admin/pages",
        "/api/v1/admin/media",
        "/api/v1/admin/roles",
        "/api/v1/admin/audit-log",
        "/api/v1/admin/analytics",
    ):
        assert pm.get(url).status_code == 403, url


# ---- article ownership and review workflow -----------------------------------------


def _complete_payload(api, title):
    base = api.get("/api/v1/admin/articles/1").get_json()["data"]
    return {
        "title": title,
        "excerpt": "A short summary for readers.",
        "body": base["body"],
        "author_id": base["author"]["id"],
        "primary_topic_id": base["primary_topic"]["id"],
        "featured_image_id": base["featured_image"]["id"],
    }


def test_edit_own_versus_edit_any(seeded, as_role):
    editor = as_role("editor", email="ed@example.org")
    make_user(seeded, "writer@example.org", ["content_writer"])
    make_user(seeded, "writer2@example.org", ["content_writer"])
    make_user(seeded, "ce@example.org", ["content_editor"])
    writer, writer2 = _client(seeded, "writer@example.org"), _client(seeded, "writer2@example.org")
    content_editor = _client(seeded, "ce@example.org")

    # Writers only see their own work; other articles look missing.
    assert writer.get("/api/v1/admin/articles").get_json()["data"] == []
    assert writer.get("/api/v1/admin/articles/1").status_code == 404
    created = writer.post("/api/v1/admin/articles", _complete_payload(editor, "My draft"))
    assert created.status_code == 201
    article = created.get_json()["data"]
    aid = article["id"]
    assert article["can"]["edit"] and article["can"]["submit"] and not article["can"]["publish"]
    assert article["created_by"]["display_name"] == "writer"
    assert [a["id"] for a in writer.get("/api/v1/admin/articles").get_json()["data"]] == [aid]

    assert writer.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Mine"}).status_code == 200
    assert writer2.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Hijack"}).status_code == 404
    assert writer.patch("/api/v1/admin/articles/1", {"subtitle": "Hijack"}).status_code == 404
    assert writer.post(f"/api/v1/admin/articles/{aid}/publish").status_code == 403
    assert writer.delete(f"/api/v1/admin/articles/{aid}").status_code == 403

    # edit_any reaches everyone's articles.
    res = content_editor.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Edited"})
    assert res.status_code == 200
    assert (
        content_editor.patch("/api/v1/admin/articles/1", {"subtitle": "Edited"}).status_code == 200
    )

    # Once published, edit_own no longer applies.
    assert editor.post(f"/api/v1/admin/articles/{aid}/publish").status_code == 200
    res = writer.get(f"/api/v1/admin/articles/{aid}").get_json()["data"]
    assert res["status"] == "published" and res["can"]["edit"] is False
    assert writer.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Later"}).status_code == 403


def test_review_workflow_submit_approve_and_reset(seeded, as_role):
    editor = as_role("editor", email="ed@example.org")
    make_user(seeded, "writer@example.org", ["content_writer"])
    writer = _client(seeded, "writer@example.org")
    aid = writer.post("/api/v1/admin/articles", {"title": "For review"}).get_json()["data"]["id"]

    assert writer.post(f"/api/v1/admin/articles/{aid}/approve").status_code == 403
    res = writer.post(f"/api/v1/admin/articles/{aid}/submit")
    assert res.status_code == 200 and res.get_json()["data"]["review_status"] == "submitted"
    assert writer.post(f"/api/v1/admin/articles/{aid}/submit").status_code == 403  # already
    queue = editor.get("/api/v1/admin/articles?review_status=submitted").get_json()["data"]
    assert [a["id"] for a in queue] == [aid]
    res = editor.post(f"/api/v1/admin/articles/{aid}/approve")
    assert res.status_code == 200 and res.get_json()["data"]["review_status"] == "approved"

    # A later change by someone who cannot approve withdraws the approval.
    writer.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Tweaked"})
    detail = writer.get(f"/api/v1/admin/articles/{aid}").get_json()["data"]
    assert detail["review_status"] == "none" and detail["approved_at"] is None
    with seeded.app_context():
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert {"article.submitted", "article.approved"} <= actions


def test_delete_is_limited_to_never_published_articles(seeded, as_role):
    make_user(seeded, "eic@example.org", ["editor_in_chief"])
    eic = _client(seeded, "eic@example.org")
    aid = eic.post("/api/v1/admin/articles", {"title": "Scrap"}).get_json()["data"]["id"]
    assert eic.delete(f"/api/v1/admin/articles/{aid}").status_code == 200
    assert eic.get(f"/api/v1/admin/articles/{aid}").status_code == 404
    res = eic.delete("/api/v1/admin/articles/1")  # published sample article
    assert res.status_code == 409 and "Archive" in res.get_json()["error"]["message"]
    editor = as_role("editor", email="ed@example.org")  # no articles.delete
    other = editor.post("/api/v1/admin/articles", {"title": "Keep"}).get_json()["data"]["id"]
    assert editor.delete(f"/api/v1/admin/articles/{other}").status_code == 403
    with seeded.app_context():
        assert db.session.get(Article, other) is not None


# ---- escalation and direct API access ------------------------------------------------


def test_administrator_cannot_escalate_or_touch_higher_accounts(app, as_role):
    as_role("super_admin", email="owner@example.org")
    make_user(app, "admin@example.org", ["administrator"])
    editor_id = make_user(app, "ed@example.org", ["editor"])
    administrator = _client(app, "admin@example.org")
    with app.app_context():
        owner_id = _user(app, "owner@example.org").id
        admin_id = _user(app, "admin@example.org").id

    # Role assignment needs roles.assign, which only Super Admin holds.
    for target in (editor_id, admin_id):
        res = administrator.patch(f"/api/v1/admin/users/{target}", {"roles": ["super_admin"]})
        assert res.status_code == 403
    res = administrator.post(
        "/api/v1/admin/invitations", {"email": "x@example.org", "roles": ["editor"]}
    )
    assert res.status_code == 403
    # Accounts with more access than the administrator are off limits.
    assert (
        administrator.patch(f"/api/v1/admin/users/{owner_id}", {"status": "disabled"}).status_code
        == 403
    )
    assert (
        administrator.post(
            f"/api/v1/admin/users/{owner_id}/password", {"password": "Another-Strong-Pass-1"}
        ).status_code
        == 403
    )
    assert administrator.post(f"/api/v1/admin/users/{owner_id}/password-reset").status_code == 403
    # Lower accounts can be managed.
    assert (
        administrator.patch(f"/api/v1/admin/users/{editor_id}", {"display_name": "Ed"}).status_code
        == 200
    )


def test_custom_role_permissions_cannot_exceed_the_actor(app, as_role):
    from app.services.admin import role_admin
    from app.utils.errors import ForbiddenError

    uid = make_user(app, "admin@example.org", ["administrator"])
    with app.app_context():
        actor = db.session.get(User, uid)
        try:
            role_admin.create_role({"label": "Big", "permissions": ["articles.view"]}, actor)
        except ForbiddenError:  # pragma: no cover - administrator holds articles.view
            raise AssertionError("administrator should be able to grant what it holds") from None
        db.session.rollback()
        writer_id = make_user(app, "w@example.org", ["content_writer"])
        writer = db.session.get(User, writer_id)
        try:
            role_admin.create_role({"label": "Bigger", "permissions": ["audit.view"]}, writer)
            raise AssertionError("escalation was allowed")
        except ForbiddenError:
            pass


def test_direct_api_access_without_permission_is_denied(seeded, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    admin.post(ROLES, {"label": "Analytics only", "permissions": ["analytics.view"]})
    make_user(seeded, "numbers@example.org", ["analytics_only"])
    api = _client(seeded, "numbers@example.org")
    assert api.get("/api/v1/admin/analytics").status_code == 200
    for method, url, body in (
        ("get", "/api/v1/admin/dashboard", None),
        ("get", "/api/v1/admin/articles", None),
        ("post", "/api/v1/admin/articles", {"title": "x"}),
        ("patch", "/api/v1/admin/articles/1", {"title": "x"}),
        ("post", "/api/v1/admin/articles/1/unpublish", {}),
        ("delete", "/api/v1/admin/articles/1", None),
        ("get", "/api/v1/admin/users", None),
        ("post", ROLES, {"label": "Mine", "permissions": ["analytics.view"]}),
        ("patch", "/api/v1/admin/settings", {"values": {"site.name": "x"}}),
    ):
        res = getattr(api, method)(url, body) if body is not None else getattr(api, method)(url)
        assert res.status_code == 403, (method, url)
