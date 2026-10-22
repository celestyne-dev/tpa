import json
from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import AuditLog, MediaAsset

BLOCKS = [
    {"type": "paragraph", "text": "A fresh start."},
    {"type": "heading", "text": "Why it matters", "level": 2},
    {"type": "list", "ordered": True, "items": ["One", "Two"]},
    {"type": "list", "items": ["Bullet"]},
    {"type": "quote", "text": "Keep going.", "cite": "TPA"},
    {"type": "callout", "tone": "tip", "title": "Try this", "text": "Write one line a day."},
    {"type": "divider"},
]


def _image_id(app):
    with app.app_context():
        return db.session.scalar(
            db.select(MediaAsset.id).where(MediaAsset.mime_type == "image/svg+xml")
        )


def _draft(api, app, **extra):
    payload = {
        "title": "Finding Calm in Busy Weeks",
        "excerpt": "Small habits for steadier days.",
        "body": BLOCKS,
        "author_id": 1,
        "primary_topic_id": 1,
        "secondary_topic_ids": [2],
        "tag_ids": [1],
        "featured_image_id": _image_id(app),
        **extra,
    }
    res = api.post("/api/v1/admin/articles", payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def test_create_draft_is_not_public(seeded, as_role, client):
    api = as_role("editor")
    article = _draft(api, seeded)
    assert article["status"] == "draft" and article["slug"] == "finding-calm-in-busy-weeks"
    assert article["body"][5] == {
        "type": "callout",
        "tone": "tip",
        "title": "Try this",
        "text": "Write one line a day.",
    }
    assert client.get(f"/api/v1/articles/{article['slug']}").status_code == 404
    slugs = [a["slug"] for a in client.get("/api/v1/articles?page_size=50").get_json()["data"]]
    assert article["slug"] not in slugs


def test_invalid_article_data_is_rejected(seeded, as_role):
    api = as_role("editor")
    assert api.post("/api/v1/admin/articles", {"excerpt": "no title"}).status_code == 400
    html = api.post("/api/v1/admin/articles", {"title": "<script>alert(1)</script>"})
    assert html.status_code == 400
    bad_block = api.post(
        "/api/v1/admin/articles", {"title": "T", "body": [{"type": "html", "text": "x"}]}
    )
    assert bad_block.status_code == 400 and "body" in bad_block.get_json()["error"]["details"]
    tags_in_text = api.post(
        "/api/v1/admin/articles",
        {"title": "T", "body": [{"type": "paragraph", "text": "<img src=x onerror=1>"}]},
    )
    assert tags_in_text.status_code == 400
    unknown_field = api.post("/api/v1/admin/articles", {"title": "T", "status": "published"})
    assert unknown_field.status_code == 400  # status changes only through workflow actions
    assert (
        api.post(
            "/api/v1/admin/articles", {"title": "T", "canonical_url": "javascript:x"}
        ).status_code
        == 400
    )
    assert api.post("/api/v1/admin/articles", {"title": "T", "author_id": 999}).status_code == 400


def test_duplicate_slug_conflict(seeded, as_role):
    api = as_role("editor")
    res = api.post("/api/v1/admin/articles", {"title": "X", "slug": "building-quiet-confidence"})
    assert res.status_code == 409


def test_edit_publish_and_lifecycle(seeded, as_role, client):
    api = as_role("editor")
    article = _draft(api, seeded)
    aid, slug = article["id"], article["slug"]

    edited = api.patch(f"/api/v1/admin/articles/{aid}", {"subtitle": "Updated", "featured": True})
    assert edited.status_code == 200 and edited.get_json()["data"]["subtitle"] == "Updated"

    preview = api.get(f"/api/v1/admin/articles/{aid}/preview").get_json()["data"]
    assert preview["article"]["title"] == article["title"] and preview["status"] == "draft"

    published = api.post(f"/api/v1/admin/articles/{aid}/publish")
    assert published.status_code == 200
    data = published.get_json()["data"]
    assert data["status"] == "published" and data["is_public"] and data["slug_locked"]
    public = client.get(f"/api/v1/articles/{slug}").get_json()["data"]["article"]
    assert public["body"][-1] == {"type": "divider"}
    assert public["tags"] and public["topic"]["slug"]

    locked = api.patch(f"/api/v1/admin/articles/{aid}", {"slug": "a-new-slug"})
    assert locked.status_code == 409

    assert api.post(f"/api/v1/admin/articles/{aid}/unpublish").status_code == 200
    assert client.get(f"/api/v1/articles/{slug}").status_code == 404
    assert api.post(f"/api/v1/admin/articles/{aid}/archive").status_code == 200
    assert api.post(f"/api/v1/admin/articles/{aid}/publish").status_code == 409
    assert api.post(f"/api/v1/admin/articles/{aid}/restore").get_json()["data"]["status"] == "draft"

    with seeded.app_context():
        actions = [
            a
            for (a,) in db.session.execute(
                db.select(AuditLog.action)
                .where(AuditLog.resource_id == str(aid))
                .order_by(AuditLog.id)
            )
        ]
    assert actions == [
        "article.created",
        "article.updated",
        "article.published",
        "article.unpublished",
        "article.archived",
        "article.restored",
    ]


def test_publish_requires_complete_article(seeded, as_role):
    api = as_role("editor")
    res = api.post("/api/v1/admin/articles", {"title": "Incomplete"})
    aid = res.get_json()["data"]["id"]
    blocked = api.post(f"/api/v1/admin/articles/{aid}/publish")
    assert blocked.status_code == 400
    details = blocked.get_json()["error"]["details"]
    assert {"excerpt", "body", "author_id", "primary_topic_id", "featured_image_id"} <= set(details)


def test_scheduling(seeded, as_role, client):
    api = as_role("editor")
    article = _draft(api, seeded)
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    res = api.post(f"/api/v1/admin/articles/{article['id']}/publish", {"published_at": future})
    data = res.get_json()["data"]
    assert data["status"] == "scheduled" and not data["is_public"]
    assert client.get(f"/api/v1/articles/{article['slug']}").status_code == 404
    naive = api.post(
        f"/api/v1/admin/articles/{article['id']}/publish", {"published_at": "2030-01-01T09:00:00"}
    )
    assert naive.status_code == 400
    # Unscheduling returns it to draft and clears the publish time.
    unscheduled = api.post(f"/api/v1/admin/articles/{article['id']}/unpublish").get_json()["data"]
    assert unscheduled["status"] == "draft" and unscheduled["published_at"] is None


def test_article_listing_search_filters_and_pagination(seeded, as_role):
    api = as_role("analyst")
    body = api.get("/api/v1/admin/articles?page_size=4").get_json()
    assert len(body["data"]) == 4 and body["meta"]["pagination"]["total"] == 6
    assert body["meta"]["counts"]["published"] == 6
    found = api.get("/api/v1/admin/articles?q=confidence").get_json()["data"]
    assert [a["slug"] for a in found] == ["building-quiet-confidence"]
    assert api.get("/api/v1/admin/articles?status=draft").get_json()["data"] == []
    assert api.get("/api/v1/admin/articles?status=bogus").status_code == 400


def test_topics_crud_and_referential_integrity(seeded, as_role, client):
    api = as_role("editor")
    created = api.post(
        "/api/v1/admin/topics",
        {"name": "Gratitude", "icon": "leaf", "description": "Noticing the good."},
    )
    assert created.status_code == 201
    tid = created.get_json()["data"]["id"]
    assert api.post("/api/v1/admin/topics", {"name": "X", "icon": "rocket"}).status_code == 400

    in_use = api.delete("/api/v1/admin/topics/1")
    assert in_use.status_code == 409 and in_use.get_json()["error"]["details"]["article_count"] >= 1

    moved = api.post("/api/v1/admin/topics/1/reassign", {"target_id": tid})
    assert moved.status_code == 200 and moved.get_json()["data"]["moved"] >= 1
    assert api.delete("/api/v1/admin/topics/1").status_code == 200

    hidden = api.patch(f"/api/v1/admin/topics/{tid}", {"status": "hidden"})
    assert hidden.status_code == 200
    assert client.get("/api/v1/topics/gratitude").status_code == 404
    assert api.delete(f"/api/v1/admin/topics/{tid}").status_code == 409


def test_authors_and_tags(seeded, as_role):
    api = as_role("editor")
    author = api.post("/api/v1/admin/authors", {"display_name": "Guest Writer", "bio": "Coach."})
    assert author.status_code == 201
    aid = author.get_json()["data"]["id"]
    assert api.delete("/api/v1/admin/authors/1").status_code == 409
    assert api.patch(f"/api/v1/admin/authors/{aid}", {"status": "archived"}).status_code == 200
    assign = api.patch("/api/v1/admin/articles/1", {"author_id": aid})
    assert assign.status_code == 400  # archived authors cannot be assigned
    assert api.delete(f"/api/v1/admin/authors/{aid}").status_code == 200

    tag = api.post("/api/v1/admin/tags", {"name": "Self Care"})
    assert tag.get_json()["data"]["slug"] == "self-care"
    assert api.post("/api/v1/admin/tags", {"name": "Self Care"}).status_code == 409
    assert api.delete("/api/v1/admin/tags/1").status_code == 409
    assert api.delete(f"/api/v1/admin/tags/{tag.get_json()['data']['id']}").status_code == 200


def test_site_settings_are_validated_and_public(seeded, as_role, client):
    api = as_role("super_admin")
    groups = api.get("/api/v1/admin/settings").get_json()["data"]["groups"]
    assert {g["name"] for g in groups} >= {"Branding", "Contact", "Social links", "SEO defaults"}
    bad = api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "contact.email": "not-an-email",
                "social.linkedin": "http://insecure",
                "unknown.key": "x",
                "footer.text": "<b>bold</b>",
            }
        },
    )
    assert bad.status_code == 400
    assert set(bad.get_json()["error"]["details"]) == {
        "contact.email",
        "social.linkedin",
        "unknown.key",
        "footer.text",
    }
    ok = api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "site.name": "Think Positive Always",
                "contact.email": "hello@example.org",
                "social.linkedin": "https://www.linkedin.com/company/example",
                "footer.text": "Encouragement for every season.",
                "newsletter.is_open": False,
            }
        },
    )
    assert ok.status_code == 200
    site = client.get("/api/v1/site").get_json()["data"]
    assert site["contact"]["email"] == "hello@example.org"
    assert site["social_links"] == [
        {
            "platform": "linkedin",
            "label": "LinkedIn",
            "url": "https://www.linkedin.com/company/example",
        }
    ]
    assert site["footer"]["text"] == "Encouragement for every season."


def test_navigation_management(seeded, as_role, client):
    api = as_role("super_admin")
    menus = api.get("/api/v1/admin/navigation").get_json()["data"]
    assert [m["key"] for m in menus] == ["primary", "footer"]
    bad = api.put(
        "/api/v1/admin/navigation/primary",
        {
            "items": [
                {"label": "Evil", "link_type": "external", "url": "javascript:alert(1)"},
                {"label": "Proto", "link_type": "internal", "url": "//evil.example"},
            ]
        },
    )
    assert bad.status_code == 400 and set(bad.get_json()["error"]["details"]) == {"0", "1"}
    ok = api.put(
        "/api/v1/admin/navigation/primary",
        {
            "items": [
                {"label": "Home", "url": "/"},
                {"label": "Articles", "url": "/articles"},
                {"label": "Hidden", "url": "/shop", "is_visible": False},
                {
                    "label": "LinkedIn",
                    "link_type": "external",
                    "url": "https://www.linkedin.com",
                    "open_in_new_tab": True,
                },
            ]
        },
    )
    assert ok.status_code == 200
    nav = client.get("/api/v1/site").get_json()["data"]["navigation"]
    assert [i["label"] for i in nav["primary"]] == ["Home", "Articles", "LinkedIn"]
    assert nav["primary"][2]["external"] is True
    assert [g["title"] for g in nav["footer"]] == [
        "Explore",
        "Shop & Resources",
        "Company",
        "Legal",
    ]
    assert api.put("/api/v1/admin/navigation/sidebar", {"items": []}).status_code == 404


def test_pages_and_sections(seeded, as_role):
    api = as_role("editor")
    pages = api.get("/api/v1/admin/pages").get_json()["data"]
    home = next(p for p in pages if p["slug"] == "home")
    assert home["section_count"] == 9 and home["rendered_publicly"] is False
    detail = api.get(f"/api/v1/admin/pages/{home['id']}").get_json()["data"]
    hero = detail["sections"][0]
    assert hero["section_type"] == "hero"
    ok = api.patch(
        f"/api/v1/admin/pages/{home['id']}/sections/{hero['id']}",
        {"content": {**hero["content"], "heading": "A Better Mindset."}},
    )
    assert ok.status_code == 200
    bad = api.patch(
        f"/api/v1/admin/pages/{home['id']}/sections/{hero['id']}",
        {"content": {**hero["content"], "primary_cta_url": "javascript:alert(1)"}},
    )
    assert bad.status_code == 400
    assert (
        api.patch(
            f"/api/v1/admin/pages/{home['id']}/sections/{hero['id']}", {"variant": "fullscreen"}
        ).status_code
        == 400
    )
    assert (
        api.patch(
            f"/api/v1/admin/pages/{home['id']}/sections/{hero['id']}", {"content": {"script": "x"}}
        ).status_code
        == 400
    )
    ids = [s["id"] for s in detail["sections"]]
    reordered = api.put(
        f"/api/v1/admin/pages/{home['id']}/sections/order", {"order": list(reversed(ids))}
    )
    assert reordered.get_json()["data"]["sections"][0]["id"] == ids[-1]
    types = api.get("/api/v1/admin/section-types").get_json()["data"]
    assert {t["type"] for t in types} >= {"hero", "rich_text", "call_to_action"}


def test_dashboard_counts_are_real(seeded, as_role):
    data = as_role("super_admin").get("/api/v1/admin/dashboard").get_json()["data"]
    assert data["articles"] == {
        "total": 6,
        "draft": 0,
        "scheduled": 0,
        "published": 6,
        "archived": 0,
    }
    assert data["topics_total"] == 8 and data["authors_total"] == 1
    assert len(data["recent_articles"]) == 6
    assert isinstance(data["recent_audit"], list)


def test_dashboard_on_fresh_install(app, as_role):
    data = as_role("super_admin").get("/api/v1/admin/dashboard").get_json()["data"]
    assert data["articles"]["total"] == 0 and data["recent_articles"] == []


def test_publication_status_tracks_rebuilds(seeded, as_role, tmp_path):
    api = as_role("editor")
    manifest = tmp_path / "prerender-manifest.json"
    seeded.config["FRONTEND_BUILD_MANIFEST"] = str(manifest)
    status = api.get("/api/v1/admin/publishing/status").get_json()["data"]
    assert status["build_manifest_found"] is False

    manifest.write_text(json.dumps({"generatedAt": datetime.now(UTC).isoformat()}))
    assert (
        api.get("/api/v1/admin/publishing/status").get_json()["data"]["rebuild_required"] is False
    )
    article = _draft(api, seeded)
    api.post(f"/api/v1/admin/articles/{article['id']}/publish")
    status = api.get("/api/v1/admin/publishing/status").get_json()["data"]
    assert status["rebuild_required"] is True and status["last_build_at"]


def test_audit_log_listing_and_sanitisation(seeded, as_role):
    api = as_role("super_admin")
    api.patch("/api/v1/admin/settings", {"values": {"contact.email": "hello@example.org"}})
    entries = api.get("/api/v1/admin/audit-log?action=settings").get_json()["data"]
    assert entries[0]["action"] == "settings.updated"
    assert entries[0]["actor"]["email"] == "super_admin@example.org"
    from app.services.audit_service import sanitize

    assert sanitize({"password": "x", "nested": {"refresh_token": "y", "ok": 1}}) == {
        "password": "[redacted]",
        "nested": {"refresh_token": "[redacted]", "ok": 1},
    }


def test_media_listing(seeded, as_role):
    media = as_role("editor").get("/api/v1/admin/media").get_json()["data"]
    assert len(media) == 12 and all(m["url"].startswith("/") for m in media)


def test_media_metadata_validation():
    import pytest

    from app.services.admin.media_admin import validate_metadata
    from app.utils.errors import ValidationError

    with pytest.raises(ValidationError):
        validate_metadata({"filename": "../etc/passwd", "mime_type": "text/html", "size_bytes": -1})
    with pytest.raises(ValidationError):
        validate_metadata({"filename": "photo.png", "mime_type": "image/png", "size_bytes": 10})
    assert validate_metadata(
        {
            "filename": "photo.png",
            "mime_type": "image/png",
            "size_bytes": 10,
            "alt_text": "A calm lake",
        }
    )
