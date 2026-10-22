"""Blocks, revisions, autosave locking, pending changes, preview and workflow."""

from datetime import UTC, datetime, timedelta

import pytest

from app.cms.blocks import parse_video_url, validate_blocks
from app.extensions import db
from app.models import Article, ArticleRevision, AuditLog, PublishJob
from app.utils.errors import ValidationError

from .conftest import make_photo, make_user
from .test_admin_content import _draft

ART = "/api/v1/admin/articles"


# ---- content blocks -------------------------------------------------------------------


def test_all_block_types_validate():
    blocks = validate_blocks(
        [
            {"type": "paragraph", "text": "Hello"},
            {"type": "heading", "text": "Section", "level": 2},
            {"type": "pullquote", "text": "Small steps.", "cite": "TPA"},
            {"type": "callout", "tone": "success", "text": "Done"},
            {"type": "image", "media_id": 3, "caption": "Calm", "align": "full"},
            {"type": "gallery", "items": [{"media_id": 1}, {"media_id": 2, "caption": "B"}]},
            {
                "type": "video",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Talk",
            },
            {"type": "video", "provider": "vimeo", "video_id": "76979871", "title": "V"},
            {"type": "button", "label": "Read more", "href": "/topics/confidence"},
            {
                "type": "cta",
                "title": "Join",
                "button_label": "Subscribe",
                "button_href": "https://example.org/x",
            },
            {"type": "related", "article_ids": [1, 2, 2]},
            {"type": "resource", "title": "Workbook", "href": "/free-resources", "kind": "product"},
            {"type": "table", "rows": [["Habit", "Minutes"], ["Walk", "20"]], "caption": "Plan"},
        ]
    )
    video = blocks[6]
    assert video["provider"] == "youtube" and video["video_id"] == "dQw4w9WgXcQ"
    assert "url" not in video  # only provider + id are stored
    assert blocks[10]["article_ids"] == [1, 2]
    assert blocks[12]["header_row"] is True


@pytest.mark.parametrize(
    "block",
    [
        {"type": "paragraph", "text": "<script>alert(1)</script>"},
        {"type": "html", "text": "<b>x</b>"},
        {"type": "paragraph", "text": "ok", "onclick": "x"},
        {"type": "button", "label": "Go", "href": "javascript:alert(1)"},
        {"type": "button", "label": "Go", "href": "//evil.example/x"},
        {"type": "button", "label": "Go", "href": "http://insecure.example"},
        {"type": "video", "url": "https://evil.example/watch?v=dQw4w9WgXcQ", "title": "x"},
        {"type": "video", "provider": "youtube", "video_id": "bad id", "title": "x"},
        {"type": "image", "media_id": "3"},
        {"type": "gallery", "items": [{"media_id": 1}]},
        {"type": "table", "rows": [["a", "b"], ["c"]]},
        {"type": "related", "article_ids": [1, 2, 3, 4, 5]},
        {"type": "heading", "text": "H1", "level": 1},
    ],
)
def test_unsafe_or_invalid_blocks_are_rejected(block):
    with pytest.raises(ValidationError):
        validate_blocks([block])


def test_video_url_parsing():
    assert parse_video_url("https://youtu.be/dQw4w9WgXcQ") == ("youtube", "dQw4w9WgXcQ")
    assert parse_video_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")[0] == "youtube"
    assert parse_video_url("https://vimeo.com/76979871") == ("vimeo", "76979871")
    assert parse_video_url("http://youtu.be/dQw4w9WgXcQ") is None


def test_blocks_must_reference_existing_media_and_articles(seeded, as_role):
    api = as_role("editor")
    article = _draft(api, seeded)
    res = api.patch(f"{ART}/{article['id']}", {"body": [{"type": "image", "media_id": 9999}]})
    assert res.status_code == 400
    res = api.patch(f"{ART}/{article['id']}", {"body": [{"type": "related", "article_ids": [999]}]})
    assert res.status_code == 400


def test_new_blocks_are_rendered_by_the_public_api(seeded, as_role, client):
    api = as_role("super_admin")
    upload = api.upload("/api/v1/admin/media", make_photo(800, 500), "calm.jpg", alt_text="Calm")
    media_id = upload.get_json()["data"]["id"]
    article = _draft(api, seeded)
    other = _draft(api, seeded, title="Unpublished draft")
    body = [
        {"type": "paragraph", "text": "Intro"},
        {"type": "gallery", "items": [{"media_id": media_id}, {"media_id": media_id}]},
        {"type": "related", "article_ids": [1, other["id"]]},  # the draft is not shown
        {"type": "video", "provider": "youtube", "video_id": "dQw4w9WgXcQ", "title": "A talk"},
    ]
    assert api.patch(f"{ART}/{article['id']}", {"body": body}).status_code == 200
    assert api.post(f"{ART}/{article['id']}/publish").status_code == 200
    data = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    gallery = next(b for b in data["body"] if b["type"] == "gallery")
    assert all(i["image"]["sources"]["image/webp"] for i in gallery["items"])
    related = next(b for b in data["body"] if b["type"] == "related")
    assert [a["id"] for a in related["articles"]] == ["1"]


# ---- revisions -------------------------------------------------------------------------


def test_revisions_are_recorded_compared_and_restored(seeded, as_role):
    api = as_role("editor")
    article = _draft(api, seeded)
    aid = article["id"]
    api.patch(f"{ART}/{aid}", {"title": "Second title", "lock_version": article["lock_version"]})
    third = api.patch(f"{ART}/{aid}", {"subtitle": "Now with subtitle"}).get_json()["data"]
    revs = api.get(f"{ART}/{aid}/revisions").get_json()["data"]
    assert [r["number"] for r in revs] == [3, 2, 1]
    assert revs[0]["summary"] == "Changed subtitle" and revs[1]["summary"] == "Changed title"
    assert revs[2]["summary"] == "Created" and revs[0]["editor"]["display_name"]

    cmp = api.get(f"{ART}/{aid}/revisions/compare?from={revs[2]['id']}&to={revs[0]['id']}")
    fields = {f["field"]: f for f in cmp.get_json()["data"]["fields"]}
    assert fields["title"]["from"] == "Finding Calm in Busy Weeks"
    assert fields["title"]["to"] == "Second title" and "subtitle" in fields

    detail = api.get(f"{ART}/{aid}/revisions/{revs[2]['id']}").get_json()["data"]
    assert detail["snapshot"]["title"] == "Finding Calm in Busy Weeks"

    res = api.post(
        f"{ART}/{aid}/revisions/{revs[2]['id']}/restore",
        {"lock_version": third["lock_version"]},
    )
    assert res.status_code == 200
    restored = res.get_json()["data"]
    assert restored["title"] == "Finding Calm in Busy Weeks" and restored["subtitle"] is None
    revs = api.get(f"{ART}/{aid}/revisions").get_json()["data"]
    assert revs[0]["kind"] == "restore" and revs[0]["summary"] == "Restored revision #1"
    with seeded.app_context():
        entry = db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "article.revision_restored")
        )
        assert entry.details["revision"] == 1


def test_revision_permissions(seeded, as_role):
    editor = as_role("editor", email="ed@example.org")
    article = _draft(editor, seeded)
    rev = editor.get(f"{ART}/{article['id']}/revisions").get_json()["data"][0]
    analyst = as_role("analyst")
    assert analyst.get(f"{ART}/{article['id']}/revisions").status_code == 403
    moderator = as_role("moderator")
    assert moderator.get(f"{ART}/{article['id']}/revisions").status_code == 200
    restore = f"{ART}/{article['id']}/revisions/{rev['id']}/restore"
    assert moderator.post(restore).status_code == 403
    make_user(seeded, "writer@example.org", ["content_writer"])
    writer = as_role("content_writer", email="writer2@example.org")
    # Other people's articles are invisible to edit-own writers.
    assert writer.get(f"{ART}/{article['id']}/revisions").status_code == 404
    assert writer.post(restore).status_code == 404


def test_autosaves_are_coalesced_and_bounded(seeded, as_role):
    api = as_role("editor")
    article = _draft(api, seeded)
    aid = article["id"]
    version = article["lock_version"]
    for i in range(5):
        res = api.patch(
            f"{ART}/{aid}", {"subtitle": f"Draft {i}", "mode": "autosave", "lock_version": version}
        )
        assert res.status_code == 200 and res.get_json()["meta"]["save_result"] == "saved"
        version = res.get_json()["data"]["lock_version"]
    revs = api.get(f"{ART}/{aid}/revisions").get_json()["data"]
    assert [r["kind"] for r in revs] == ["autosave", "manual"]
    with seeded.app_context():
        from app.services.admin import revisions

        article_obj = db.session.get(Article, aid)
        for _ in range(revisions.MAX_AUTOSAVES + 5):
            article_obj.subtitle = f"x{_}"
            revisions.record(article_obj, None, "autosave", "bulk")  # editor None: new rows
            article_obj.updated_by_id = None
        db.session.commit()
        count = db.session.scalar(
            db.select(db.func.count(ArticleRevision.id)).where(
                ArticleRevision.article_id == aid, ArticleRevision.kind == "autosave"
            )
        )
        assert count <= revisions.MAX_AUTOSAVES + 1


def test_stale_saves_are_rejected_with_a_conflict(seeded, as_role):
    api = as_role("editor")
    article = _draft(api, seeded)
    aid, version = article["id"], article["lock_version"]
    first = api.patch(f"{ART}/{aid}", {"subtitle": "Mine", "lock_version": version})
    assert first.status_code == 200
    stale = api.patch(f"{ART}/{aid}", {"subtitle": "Theirs", "lock_version": version})
    assert stale.status_code == 409
    err = stale.get_json()["error"]
    assert err["code"] == "edit_conflict" and err["details"]["lock_version"] == version + 1
    current = api.get(f"{ART}/{aid}").get_json()["data"]
    assert current["subtitle"] == "Mine"


# ---- published articles: pending changes ---------------------------------------------------


def _published(api, app):
    article = _draft(api, app)
    res = api.post(f"{ART}/{article['id']}/publish")
    assert res.status_code == 200
    return res.get_json()["data"]


def test_autosave_never_changes_a_live_article(seeded, as_role, client):
    api = as_role("editor")
    article = _published(api, seeded)
    aid = article["id"]
    res = api.patch(
        f"{ART}/{aid}",
        {"title": "Half-typed tit", "mode": "autosave", "lock_version": article["lock_version"]},
    )
    body = res.get_json()
    assert body["meta"]["save_result"] == "pending" and body["data"]["title"] == "Half-typed tit"
    assert body["data"]["has_pending_changes"] and body["data"]["pending_fields"] == ["title"]
    live = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert live["title"] == article["title"]
    # The private preview shows the working copy.
    preview = api.get(f"{ART}/{aid}/preview")
    assert preview.get_json()["data"]["article"]["title"] == "Half-typed tit"
    assert preview.headers["Cache-Control"] == "no-store"
    assert "noindex" in preview.headers["X-Robots-Tag"]


def test_non_publishers_save_live_edits_for_review(seeded, as_role, client):
    editor = as_role("editor", email="ed@example.org")
    article = _published(editor, seeded)
    aid = article["id"]
    content_editor = as_role("content_editor")
    res = content_editor.patch(f"{ART}/{aid}", {"excerpt": "A better summary."})
    assert res.status_code == 200 and res.get_json()["meta"]["save_result"] == "pending"
    assert not res.get_json()["data"]["can"]["publish_changes"]
    assert content_editor.post(f"{ART}/{aid}/publish-changes").status_code == 403
    live = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert live["excerpt"] == article["excerpt"]
    with seeded.app_context():
        db.session.query(PublishJob).delete()
        db.session.commit()
    res = editor.post(f"{ART}/{aid}/publish-changes")
    assert res.status_code == 200 and not res.get_json()["data"]["has_pending_changes"]
    live = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert live["excerpt"] == "A better summary."
    with seeded.app_context():
        job = db.session.scalar(db.select(PublishJob))
        assert job.status == "pending" and "published_article_updated" in job.reasons
        assert db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "article.changes_published")
        )


def test_publishers_save_live_and_can_discard_pending(seeded, as_role):
    api = as_role("editor")
    article = _published(api, seeded)
    aid = article["id"]
    saved = api.patch(f"{ART}/{aid}", {"subtitle": "Live now"}).get_json()
    assert saved["meta"]["save_result"] == "saved" and not saved["data"]["has_pending_changes"]
    api.patch(f"{ART}/{aid}", {"subtitle": "Experiment", "mode": "autosave"})
    res = api.post(f"{ART}/{aid}/discard-changes")
    assert res.status_code == 200
    assert res.get_json()["data"]["subtitle"] == "Live now"


def test_restoring_on_a_live_article_creates_pending_changes(seeded, as_role, client):
    api = as_role("editor")
    article = _published(api, seeded)
    aid = article["id"]
    api.patch(f"{ART}/{aid}", {"title": "Renamed live"})
    first = api.get(f"{ART}/{aid}/revisions").get_json()["data"][-1]
    res = api.post(f"{ART}/{aid}/revisions/{first['id']}/restore")
    assert res.get_json()["meta"]["save_result"] == "pending"
    live = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert live["title"] == "Renamed live"


def test_slug_changes_after_publication_need_seo_permission_and_create_redirects(
    seeded, as_role, client
):
    editor = as_role("editor", email="ed@example.org")
    article = _published(editor, seeded)
    aid, old = article["id"], article["slug"]
    assert editor.patch(f"{ART}/{aid}", {"slug": "renamed"}).status_code == 409
    owner = as_role("super_admin", email="owner@example.org")
    res = owner.patch(f"{ART}/{aid}", {"slug": "renamed"})
    assert res.status_code == 200 and res.get_json()["data"]["slug"] == "renamed"
    hop = client.get(f"/_redirect/articles/{old}")
    assert hop.status_code == 301 and hop.headers["Location"] == "/articles/renamed"
    # Renaming back removes the now-wrong redirect instead of creating a loop.
    owner.patch(f"{ART}/{aid}", {"slug": old})
    assert client.get(f"/_redirect/articles/{old}").status_code == 404
    assert client.get("/_redirect/articles/renamed").headers["Location"] == f"/articles/{old}"


def test_indexing_fields_require_seo_permission(seeded, as_role):
    editor = as_role("editor")
    article = _draft(editor, seeded)
    res = editor.patch(f"{ART}/{article['id']}", {"noindex": True})
    assert res.status_code == 403
    res = editor.patch(f"{ART}/{article['id']}", {"meta_description": "Fine to edit."})
    assert res.status_code == 200


# ---- preview and workflow ----------------------------------------------------------------


def test_preview_respects_ownership_and_permission(seeded, as_role):
    editor = as_role("editor", email="ed@example.org")
    article = _draft(editor, seeded)
    writer = as_role("content_writer")
    assert writer.get(f"{ART}/{article['id']}/preview").status_code == 404
    own = writer.post(ART, {"title": "Mine"}).get_json()["data"]
    assert writer.get(f"{ART}/{own['id']}/preview").status_code == 200
    pm = as_role("product_manager")
    assert pm.get(f"{ART}/{article['id']}/preview").status_code == 403


def test_editorial_workflow_end_to_end(seeded, as_role, client):
    writer = as_role("content_writer")
    draft = writer.post(ART, {"title": "Workflow piece"}).get_json()["data"]
    aid = draft["id"]
    assert draft["can"]["publish"] is False and draft["can"]["approve"] is False
    assert writer.post(f"{ART}/{aid}/approve").status_code == 403
    assert writer.post(f"{ART}/{aid}/publish").status_code == 403
    assert writer.post(f"{ART}/{aid}/submit").get_json()["data"]["review_status"] == "submitted"
    editor = as_role("editor")
    assert editor.post(f"{ART}/{aid}/approve").get_json()["data"]["review_status"] == "approved"
    # Complete the article, then schedule it.
    full = _draft(editor, seeded, title="Ready article")
    when = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    res = editor.post(f"{ART}/{full['id']}/publish", {"published_at": when})
    assert res.get_json()["data"]["status"] == "scheduled"
    assert client.get(f"/api/v1/articles/{full['slug']}").status_code == 404
    with seeded.app_context():
        from app.services.publication_service import publish_due_scheduled

        assert publish_due_scheduled()["published"] == []
        later = datetime.now(UTC) + timedelta(hours=3)
        first = publish_due_scheduled(later)
        second = publish_due_scheduled(later)  # idempotent
        db.session.commit()
        assert first["published"] == [full["slug"]] and second["published"] == []
        article = db.session.get(Article, full["id"])
        assert article.status == "published" and article.first_published_at is not None
        assert db.session.scalar(
            db.select(db.func.count(PublishJob.id)).where(PublishJob.status == "pending")
        )
        actions = set(db.session.scalars(db.select(AuditLog.action)))
        assert {"article.submitted", "article.approved", "article.scheduled"} <= actions


def test_publish_due_cli_is_idempotent(seeded):
    with seeded.app_context():
        article = db.session.scalar(db.select(Article).where(Article.status == "published"))
        article.status = "scheduled"
        article.published_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    runner = seeded.test_cli_runner()
    first = runner.invoke(args=["content", "publish-due"])
    second = runner.invoke(args=["content", "publish-due"])
    assert "Published 1 scheduled article" in first.output
    assert "No scheduled articles are due" in second.output


def test_workflow_filters(seeded, as_role):
    editor = as_role("editor")
    article = _published(editor, seeded)
    editor.patch(f"{ART}/{article['id']}", {"subtitle": "pending", "mode": "autosave"})
    pending = editor.get(f"{ART}?has_pending=true").get_json()["data"]
    assert [a["id"] for a in pending] == [article["id"]]
    mine = editor.get(f"{ART}?mine=true").get_json()["data"]
    assert all(a["created_by"]["id"] == mine[0]["created_by"]["id"] for a in mine)
