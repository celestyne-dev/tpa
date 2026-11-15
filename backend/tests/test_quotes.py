"""Quote collections (Admin › Quotes, /quotes): separate from articles, built on the
article editor, publishing and SEO tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.cms.blocks import validate_blocks
from app.extensions import db
from app.models import Article, MediaAsset, PublishJob
from app.services import publication_service
from app.utils.errors import ValidationError

from .test_admin_content import _image_id

ADMIN = "/api/v1/admin/articles"


def _quotes(n, start=1):
    return [f"Quote number {i} is about **courage** — Author {i}" for i in range(start, start + n)]


def _body(app, *, image=True):
    blocks = [
        {"type": "paragraph", "text": "Why these quotes matter, and how to use them this week."},
        {"type": "list", "ordered": True, "items": _quotes(5)},
    ]
    if image:
        blocks.append({"type": "image", "media_id": _image_id(app), "pin_description": "Pin me"})
    blocks += [
        {"type": "list", "ordered": True, "start": 6, "items": _quotes(5, 6)},
        # The existing lesson blocks, read-only here.
        {
            "type": "exercise",
            "title": "Try this",
            "prompt": "Pick one quote.",
            "allow_response": True,
        },
        {"type": "key_points", "title": "Key points", "items": ["Start small", "Keep going"]},
        {"type": "list", "ordered": True, "start": 11, "items": _quotes(5, 11)},
    ]
    return blocks


def _collection(api, app, **extra):
    payload = {
        "content_type": "quotes",
        "title": "Quotes for Brave Mornings",
        "excerpt": "Fifteen quotes on courage, with reflections.",
        "body": _body(app),
        "primary_topic_id": 1,
        "featured_image_id": _image_id(app),
        **extra,
    }
    res = api.post(ADMIN, payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _publish(api, item, when=None):
    res = api.post(f"{ADMIN}/{item['id']}/publish", {"published_at": when} if when else {})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _jobs(app):
    with app.app_context():
        return db.session.query(PublishJob).count()


# ---- creation and validation -----------------------------------------------------------


def test_create_a_quote_collection_separately_from_articles(seeded, as_role, client):
    api = as_role("editor")
    item = _collection(api, seeded)
    assert item["content_type"] == "quotes" and item["status"] == "draft"
    assert item["noindex"] is True  # not indexed until an editor turns it on
    # Admin › Quotes lists it; Admin › Articles does not.
    quotes = api.get(f"{ADMIN}?content_type=quotes").get_json()
    assert [q["id"] for q in quotes["data"]] == [item["id"]]
    assert quotes["meta"]["counts"]["draft"] == 1
    articles = api.get(ADMIN).get_json()
    assert item["id"] not in [a["id"] for a in articles["data"]]
    # No author is needed to publish a collection.
    _publish(api, item)
    assert client.get("/api/v1/quotes/quotes-for-brave-mornings").status_code == 200


def test_validation_rejects_bad_blocks_and_content_types(seeded, as_role):
    api = as_role("editor")
    res = api.post(ADMIN, {"content_type": "poems", "title": "x", "excerpt": "y"})
    assert res.status_code == 400
    with pytest.raises(ValidationError):
        validate_blocks([{"type": "list", "ordered": True, "start": 0, "items": ["x"]}])
    with pytest.raises(ValidationError):
        validate_blocks([{"type": "callout", "tone": "loud", "text": "x"}])
    # Lesson blocks are for quote collections (and lessons), not articles.
    res = api.post(
        ADMIN,
        {"title": "x", "excerpt": "y", "body": [{"type": "key_points", "items": ["a"]}]},
    )
    assert res.status_code == 400
    res = api.post(
        ADMIN,
        {
            "content_type": "quotes",
            "title": "x",
            "excerpt": "y",
            "body": [
                {"type": "further_reading", "items": [{"label": "x", "href": "javascript:x"}]}
            ],
        },
    )
    assert res.status_code == 400
    item = _collection(api, seeded)
    # The content type is fixed once created: a save never turns it into an article.
    res = api.patch(
        f"{ADMIN}/{item['id']}", {"content_type": "article", "lock_version": item["lock_version"]}
    )
    assert res.status_code == 400


# ---- visibility -----------------------------------------------------------------------------


def test_draft_scheduled_and_published_visibility(seeded, as_role, client):
    api = as_role("editor")
    item = _collection(api, seeded)
    slug = item["slug"]
    assert client.get(f"/api/v1/quotes/{slug}").status_code == 404  # draft
    assert client.get("/api/v1/quotes").get_json()["data"] == []
    when = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assert _publish(api, item, when)["status"] == "scheduled"
    assert client.get(f"/api/v1/quotes/{slug}").status_code == 404
    with seeded.app_context():  # the scheduled time arrives
        db.session.get(Article, item["id"]).published_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
        publication_service.publish_due_scheduled()
        db.session.commit()
    assert client.get(f"/api/v1/quotes/{slug}").status_code == 200
    # Never served or listed as an article.
    assert client.get(f"/api/v1/articles/{slug}").status_code == 404
    listed = [a["slug"] for a in client.get("/api/v1/articles?page_size=50").get_json()["data"]]
    assert slug not in listed
    search = client.get("/api/v1/search?q=Brave").get_json()["data"]["results"]
    assert slug not in [r["slug"] for r in search]
    assert api.post(f"{ADMIN}/{item['id']}/unpublish").status_code == 200
    assert client.get(f"/api/v1/quotes/{slug}").status_code == 404


def test_public_payload_keeps_formatting_numbering_and_images(seeded, as_role, client):
    api = as_role("editor")
    _publish(api, _collection(api, seeded))
    data = client.get("/api/v1/quotes/quotes-for-brave-mornings").get_json()["data"]
    collection = data["collection"]
    assert collection["content_type"] == "quotes"
    body = collection["body"]
    lists = [b for b in body if b["type"] == "list"]
    assert [b.get("start") for b in lists] == [None, 6, 11]  # 1-5, image, 6-10, reflection, 11-15
    assert lists[0]["items"][0] == "Quote number 1 is about **courage** — Author 1"
    image = next(b for b in body if b["type"] == "image")
    assert image["image"]["src"] and image["pin_description"] == "Pin me"
    exercise = next(b for b in body if b["type"] == "exercise")
    assert exercise["allow_response"] is False and exercise["required"] is False  # reflection only
    assert next(b for b in body if b["type"] == "key_points")["items"] == [
        "Start small",
        "Keep going",
    ]
    listing = client.get("/api/v1/quotes").get_json()
    assert [c["slug"] for c in listing["data"]] == ["quotes-for-brave-mornings"]
    assert listing["meta"]["topics"][0]["collection_count"] == 1
    assert client.get("/api/v1/quotes?q=brave").get_json()["data"]
    assert client.get("/api/v1/quotes?q=nothing-here").get_json()["data"] == []


# ---- related content ------------------------------------------------------------------------


def test_related_articles_and_collections_by_topic(seeded, as_role, client):
    api = as_role("editor")
    first = _collection(api, seeded)
    _publish(api, first)
    second = _collection(api, seeded, title="Quotes for Quiet Evenings")
    _publish(api, second)
    data = client.get(f"/api/v1/quotes/{first['slug']}").get_json()["data"]
    assert [c["slug"] for c in data["related_collections"]] == [second["slug"]]
    assert all(a["content_type"] == "article" for a in data["related_articles"])
    assert data["related_articles"]
    # Articles on the same topic recommend the collections.
    with seeded.app_context():
        article = db.session.scalar(
            db.select(Article).where(
                Article.content_type == "article",
                Article.status == "published",
                Article.primary_topic_id == 1,
            )
        )
    detail = client.get(f"/api/v1/articles/{article.slug}").get_json()["data"]
    assert {c["slug"] for c in detail["related_quotes"]} <= {first["slug"], second["slug"]}
    assert detail["related_quotes"]


# ---- SEO: metadata, sitemap, quality checks -------------------------------------------------


def test_indexing_canonical_and_sitemap(seeded, as_role, client):
    api = as_role("editor", "seo_manager")
    item = _collection(api, seeded)
    _publish(api, item)
    path = f"/quotes/{item['slug']}"

    def sitemap():
        return {e["path"]: e for e in client.get("/api/v1/sitemap").get_json()["data"]}

    assert path not in sitemap() and "/quotes" not in sitemap()  # noindex by default
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    res = api.patch(
        f"{ADMIN}/{item['id']}",
        {"noindex": False, "lock_version": detail["lock_version"]},
    )
    assert res.status_code == 200, res.get_json()
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    if detail.get("has_pending_changes"):
        api.post(f"{ADMIN}/{item['id']}/publish-changes", {"lock_version": detail["lock_version"]})
    entries = sitemap()
    assert entries[path]["type"] == "quotes" and entries["/quotes"]["type"] == "page"
    assert entries[path]["images"]  # image sitemap: featured and body images
    assert f"/articles/{item['slug']}" not in entries
    checks = api.get(f"{ADMIN}/{item['id']}/seo-checks").get_json()["data"]
    assert checks["preview"]["url"].endswith(path) and checks["preview"]["indexable"]
    # An external canonical keeps it out of the sitemap.
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    api.patch(
        f"{ADMIN}/{item['id']}",
        {"canonical_url": "https://example.org/elsewhere", "lock_version": detail["lock_version"]},
    )
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    if detail.get("has_pending_changes"):
        api.post(f"{ADMIN}/{item['id']}/publish-changes", {"lock_version": detail["lock_version"]})
    assert path not in sitemap()


def test_quality_checklist_for_editorial_review(seeded, as_role):
    api = as_role("editor")
    with seeded.app_context():
        asset = db.session.get(MediaAsset, _image_id(seeded))
        asset.credit, asset.source_url = "", None
        db.session.commit()
    thin = _collection(
        api,
        seeded,
        title="Bare quotes",
        body=[
            {"type": "list", "ordered": True, "items": ["Be brave", "Be brave", "Keep going"]},
            {"type": "image", "media_id": _image_id(seeded)},
            {"type": "list", "ordered": True, "items": ["Rest well — Unknown"]},
        ],
    )
    codes = {
        c["code"] for c in api.get(f"{ADMIN}/{thin['id']}/seo-checks").get_json()["data"]["checks"]
    }
    assert {
        "quotes_introduction",
        "quotes_commentary",
        "quotes_attribution",
        "quotes_numbering",
        "quotes_repeated",
        "quotes_image_rights",
        "noindex",
    } <= codes
    assert "missing_author" not in codes
    good = _collection(api, seeded)
    other = _collection(api, seeded, title="Brave mornings, again")  # same quotes
    good_codes = {
        c["code"] for c in api.get(f"{ADMIN}/{good['id']}/seo-checks").get_json()["data"]["checks"]
    }
    assert not {"quotes_introduction", "quotes_commentary", "quotes_numbering"} & good_codes
    assert "quotes_attribution" not in good_codes
    assert "quotes_duplicate_content" in good_codes and other["id"]


# ---- homepage builder -------------------------------------------------------------------------


def test_quote_collections_homepage_section(seeded, as_role, client):
    from .test_page_builder import HOMEPAGE, PAGES, _public_home, _save, _sections_payload

    editor = as_role("editor")
    first = _publish(editor, _collection(editor, seeded))
    second = _publish(editor, _collection(editor, seeded, title="Quotes for Quiet Evenings"))
    api = as_role("website_manager")
    options = api.get("/api/v1/admin/builder-options").get_json()["data"]
    assert {q["id"] for q in options["quote_collections"]} == {first["id"], second["id"]}
    assert first["id"] not in {a["id"] for a in options["articles"]}
    home = api.get(HOMEPAGE).get_json()["data"]
    before = [s["type"] for s in _public_home(client)["sections"]]
    section = {
        "name": "Quotes",
        "section_type": "quote_collections",
        "variant": "carousel",
        "content": {
            "heading": "Words for the week",
            "mode": "manual",
            "collections": [second["id"]],
        },
        "design": {},
        "is_visible": True,
    }
    sections = _sections_payload(home)
    sections.insert(1, section)
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    draft = saved.get_json()["data"]
    published = api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": draft["lock_version"]})
    assert published.status_code == 200, published.get_json()
    public = _public_home(client)["sections"]
    quotes = public[1]
    assert quotes["type"] == "quote_collections" and quotes["variant"] == "carousel"
    assert [c["slug"] for c in quotes["data"]["collections"]] == [second["slug"]]
    assert quotes["data"]["collections"][0]["content_type"] == "quotes"
    # Every existing section is still there, in order.
    assert [s["type"] for s in public if s["type"] != "quote_collections"] == before
    # A collection picker shows only collections (an article id given to it is ignored).
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections[1]["content"]["collections"] = [second["id"], 1]
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    preview = api.post(f"{PAGES}/{home['id']}/preview").get_json()["data"]["page"]
    shown = preview["sections"][1]["data"]["collections"]
    assert [c["slug"] for c in shown] == [second["slug"]]


def test_latest_mode_section_and_links(seeded, as_role, client):
    editor = as_role("editor")
    item = _publish(editor, _collection(editor, seeded))
    api = as_role("website_manager")
    links = api.get("/api/v1/admin/link-options?q=quotes").get_json()["data"]
    urls = {link["url"] for link in links}
    assert "/quotes" in urls and f"/quotes/{item['slug']}" in urls


# ---- publishing and navigation ----------------------------------------------------------------


def test_publishing_updating_and_unpublishing_queue_rebuilds(seeded, as_role):
    api = as_role("editor")
    item = _collection(api, seeded)
    jobs = _jobs(seeded)
    _publish(api, item)
    assert _jobs(seeded) > jobs
    with seeded.app_context():
        db.session.query(PublishJob).delete()
        db.session.commit()
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    api.patch(f"{ADMIN}/{item['id']}", {"title": "Braver", "lock_version": detail["lock_version"]})
    detail = api.get(f"{ADMIN}/{item['id']}").get_json()["data"]
    if detail.get("has_pending_changes"):
        api.post(f"{ADMIN}/{item['id']}/publish-changes", {"lock_version": detail["lock_version"]})
    assert _jobs(seeded) >= 1
    with seeded.app_context():
        db.session.query(PublishJob).delete()
        db.session.commit()
    assert api.post(f"{ADMIN}/{item['id']}/unpublish").status_code == 200
    assert _jobs(seeded) >= 1


def test_default_menu_links_quotes_once_a_collection_is_published(seeded, app, as_role, client):
    from .test_navigation_architecture import _drop_saved_menus, _nav

    _drop_saved_menus(app)
    urls = lambda: [i.get("url") for i in _nav(client)["primary"]]  # noqa: E731
    assert "/quotes" not in urls()
    api = as_role("editor")
    _publish(api, _collection(api, seeded))
    assert "/quotes" in urls()


def test_saved_menus_are_left_as_arranged(seeded, as_role, client):
    from .test_navigation_architecture import _nav

    manager = as_role("website_manager")
    res = manager.put(
        "/api/v1/admin/navigation/primary", {"items": [{"label": "Articles", "url": "/articles"}]}
    )
    assert res.status_code == 200, res.get_json()
    api = as_role("editor")
    _publish(api, _collection(api, seeded))
    assert [i["label"] for i in _nav(client)["primary"]] == ["Articles"]


# ---- existing behaviour -------------------------------------------------------------------------


def test_existing_articles_are_unchanged(seeded, client):
    with seeded.app_context():
        assert (
            db.session.scalar(
                db.select(db.func.count(Article.id)).where(Article.content_type != "article")
            )
            == 0
        )
    listing = client.get("/api/v1/articles").get_json()["data"]
    assert listing and all(a["content_type"] == "article" for a in listing)
    detail = client.get(f"/api/v1/articles/{listing[0]['slug']}").get_json()["data"]
    assert detail["related_quotes"] == []
