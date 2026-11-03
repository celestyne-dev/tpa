"""Technical release: inline links and sources, material "last updated" dates, author
pages, site search, the AI crawler policy and trust (policy) pages.

Everything here runs on test fixtures (the sample content and articles created through
the admin API in a throwaway database); no real article is read or changed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.cms.blocks import (
    blocks_word_count,
    internal_links,
    plain_text,
    strip_inline_links,
    validate_blocks,
)
from app.cms.settings_registry import AI_TRAINING_CRAWLERS, training_crawler_key
from app.extensions import db
from app.models import Article, AuditLog, Author, Page, SiteSetting
from app.utils.errors import ValidationError

from .test_editorial import ART, _published

# ---- inline links and sources -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Read [our guide](/topics/confidence) first.",
        "See [the study](https://example.org/paper?id=4#results).",
        "Write to [us](mailto:hello@example.com).",
        "Brackets [alone] and (parentheses) stay plain text.",
    ],
)
def test_inline_links_accept_site_paths_https_and_mailto(text):
    assert validate_blocks([{"type": "paragraph", "text": text}])[0]["text"] == text


@pytest.mark.parametrize(
    "text",
    [
        "[click](javascript:alert(1))",
        "[click]( javascript:void 0)",
        "[old](http://example.org/insecure)",
        "[data](data:text/html;base64,PHNjcmlwdD4=)",
        "[relative](../escape)",
        "[protocol-relative](//evil.example/x)",
    ],
)
def test_inline_links_reject_every_other_target(text):
    with pytest.raises(ValidationError):
        validate_blocks([{"type": "paragraph", "text": text}])


def test_inline_links_in_lists_callouts_and_tables_are_checked_too():
    for block in (
        {"type": "list", "items": ["fine", "[bad](javascript:x)"]},
        {"type": "callout", "text": "[bad](http://x.example)"},
        {"type": "table", "rows": [["a", "[bad](javascript:x)"]]},
    ):
        with pytest.raises(ValidationError):
            validate_blocks([block])
    ok = validate_blocks(
        [
            {"type": "list", "items": ["See [topic](/topics/resilience)"]},
            {"type": "table", "rows": [["[Guide](/articles/a-guide)", "x"]]},
        ]
    )
    assert internal_links(ok) == ["/topics/resilience", "/articles/a-guide"]


def test_link_syntax_does_not_count_as_words_or_search_text():
    blocks = validate_blocks(
        [{"type": "paragraph", "text": "Try [small steps](https://example.org/a-very/long/url)."}]
    )
    assert blocks_word_count(blocks) == 3
    assert strip_inline_links(blocks[0]["text"]) == "Try small steps."
    assert "example.org" not in plain_text(blocks)


def test_sources_block_validates_https_titles_and_dates():
    [block] = validate_blocks(
        [
            {
                "type": "sources",
                "title": "Sources",
                "items": [
                    {
                        "title": "Sleep and mood",
                        "url": "https://example.org/study",
                        "publisher": "Example Journal",
                        "accessed": "2026-10-30",
                    },
                    {"title": "A report", "url": "https://example.com/r"},
                ],
            }
        ]
    )
    assert block["items"][0]["publisher"] == "Example Journal" and len(block["items"]) == 2
    for bad in (
        {"title": "x", "url": "http://example.org"},
        {"title": "", "url": "https://example.org"},
        {"title": "x", "url": "https://example.org", "accessed": "30/10/2026"},
        {"title": "x", "url": "https://example.org", "rating": 5},
    ):
        with pytest.raises(ValidationError):
            validate_blocks([{"type": "sources", "items": [bad]}])
    with pytest.raises(ValidationError):
        validate_blocks([{"type": "sources", "items": []}])


# ---- material "last updated" date --------------------------------------------------------


def _article(app, slug):
    with app.app_context():
        article = db.session.scalar(select(Article).where(Article.slug == slug))
        db.session.expunge(article)
        return article


def test_last_updated_moves_only_for_material_updates(seeded, as_role, client):
    api = as_role("editor")
    article = _published(api, seeded)
    aid, slug = article["id"], article["slug"]
    before = _article(seeded, slug)
    assert before.content_modified_at is None

    # An ordinary live edit (typo, SEO field) keeps the date empty.
    api.patch(f"{ART}/{aid}", {"subtitle": "Fixed a typo"})
    assert _article(seeded, slug).content_modified_at is None
    # Autosave never changes the live article or its date, even if flagged.
    api.patch(f"{ART}/{aid}", {"subtitle": "Draft", "mode": "autosave", "material_update": True})
    assert _article(seeded, slug).content_modified_at is None
    api.post(f"{ART}/{aid}/discard-changes")

    # A material update sets it; slug and publication dates never change.
    res = api.patch(f"{ART}/{aid}", {"excerpt": "Rewritten advice.", "material_update": True})
    assert res.status_code == 200, res.get_json()
    after = _article(seeded, slug)
    assert after.content_modified_at is not None
    assert (after.slug, after.published_at, after.first_published_at) == (
        before.slug,
        before.published_at,
        before.first_published_at,
    )
    live = client.get(f"/api/v1/articles/{slug}").get_json()["data"]["article"]
    assert live["content_modified_at"] == res.get_json()["data"]["content_modified_at"]
    # A save without changes doesn't move it again.
    stamp = after.content_modified_at
    api.patch(f"{ART}/{aid}", {"excerpt": "Rewritten advice.", "material_update": True})
    assert _article(seeded, slug).content_modified_at == stamp


def test_published_pending_changes_can_be_marked_material(seeded, as_role, client):
    editor = as_role("editor", email="ed@example.org")
    article = _published(editor, seeded)
    aid, slug = article["id"], article["slug"]
    writer = as_role("content_editor")
    assert writer.patch(f"{ART}/{aid}", {"excerpt": "New guidance."}).status_code == 200
    res = editor.post(f"{ART}/{aid}/publish-changes", {"material_update": True})
    assert res.status_code == 200, res.get_json()
    assert _article(seeded, slug).content_modified_at is not None
    with seeded.app_context():
        log = db.session.scalar(
            select(AuditLog).where(AuditLog.action == "article.changes_published")
        )
        assert log.details["material_update"] is True


def test_drafts_never_get_a_last_updated_date(seeded, as_role):
    from .test_admin_content import _draft

    api = as_role("editor")
    draft = _draft(api, seeded)
    api.patch(f"{ART}/{draft['id']}", {"excerpt": "Changed.", "material_update": True})
    assert _article(seeded, draft["slug"]).content_modified_at is None


def test_sitemap_lastmod_follows_publication_or_material_updates(seeded, as_role, client):
    api = as_role("editor")
    article = _published(api, seeded)
    path = f"/articles/{article['slug']}"

    def lastmod():
        entries = client.get("/api/v1/sitemap").get_json()["data"]
        return next(e for e in entries if e["path"] == path)["lastmod"]

    published = lastmod()
    api.patch(f"{ART}/{article['id']}", {"subtitle": "Small fix"})
    assert lastmod() == published  # not every database save
    api.patch(f"{ART}/{article['id']}", {"excerpt": "Big rewrite.", "material_update": True})
    assert lastmod() > published


# ---- author pages -----------------------------------------------------------------------


def _make_person(app, slug="tpa", *, bio="Writes about resilience.", status="active"):
    """The sample articles' author, turned into a real person (fixture data only)."""
    with app.app_context():
        author = db.session.scalar(select(Author).where(Author.slug == slug))
        author.is_person, author.bio, author.status = True, bio, status
        db.session.commit()
        return author.slug


def test_author_pages_exist_only_for_real_people_with_a_bio(seeded, client):
    with seeded.app_context():
        db_slug = db.session.scalar(select(Author.slug))
    # Editorial byline (not a person): no page, no link.
    assert client.get(f"/api/v1/authors/{db_slug}").status_code == 404
    article = client.get("/api/v1/articles").get_json()["data"][0]
    assert "has_page" not in article["author"]
    slug = _make_person(seeded, db_slug)
    res = client.get(f"/api/v1/authors/{slug}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["data"]["author"]["bio"] == "Writes about resilience."
    assert body["data"]["author"]["article_count"] == body["meta"]["pagination"]["total"] > 0
    assert all(a["author"]["slug"] == slug for a in body["data"]["articles"])
    assert client.get("/api/v1/articles").get_json()["data"][0]["author"]["has_page"] is True
    assert client.get("/api/v1/authors").get_json()["data"][0]["slug"] == slug
    sitemap = client.get("/api/v1/sitemap").get_json()["data"]
    assert {"type": "author", "path": f"/authors/{slug}"}.items() <= next(
        e for e in sitemap if e["type"] == "author"
    ).items()
    # No bio, or archived: no page.
    _make_person(seeded, slug, bio="  ")
    assert client.get(f"/api/v1/authors/{slug}").status_code == 404
    _make_person(seeded, slug, status="archived")
    assert client.get(f"/api/v1/authors/{slug}").status_code == 404
    assert not [
        e for e in client.get("/api/v1/sitemap").get_json()["data"] if e["type"] == "author"
    ]
    assert client.get("/api/v1/authors/Not_A_Slug").status_code == 404


# ---- search -----------------------------------------------------------------------------


def _search(client, q, **params):
    return client.get("/api/v1/search", query_string={"q": q, **params})


def test_search_finds_published_articles_only(seeded, as_role, client):
    from .test_admin_content import _draft

    api = as_role("editor")
    draft = _draft(api, seeded, title="Zebra crossings for the mind")
    scheduled = _draft(api, seeded, title="Zebra patterns in planning")
    when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    assert api.post(f"{ART}/{scheduled['id']}/publish", {"published_at": when}).status_code == 200
    assert _search(client, "zebra").get_json()["data"]["results"] == []
    published = _published(api, seeded)  # "Finding Calm in Busy Weeks"
    res = _search(client, "finding calm")
    data = res.get_json()["data"]
    assert res.status_code == 200 and data["terms"] == ["finding", "calm"]
    assert published["slug"] in [r["slug"] for r in data["results"]]
    assert draft["slug"] not in [r["slug"] for r in data["results"]]


def test_search_matches_every_term_and_body_text(seeded, client):
    sample = client.get("/api/v1/articles", query_string={"page_size": 1}).get_json()["data"][0]
    words = [w for w in sample["title"].lower().split() if len(w) > 3][:2]
    results = _search(client, " ".join(words)).get_json()["data"]["results"]
    assert sample["slug"] in [r["slug"] for r in results]
    assert _search(client, f"{words[0]} qqxxzzunmatched").get_json()["data"]["results"] == []
    with seeded.app_context():
        article = db.session.scalar(select(Article).where(Article.slug == sample["slug"]))
        body_word = next(
            w
            for w in plain_text(article.body).lower().split()
            if len(w) > 6 and w.isalpha() and w not in article.title.lower()
        )
    assert sample["slug"] in [
        r["slug"] for r in _search(client, body_word).get_json()["data"]["results"]
    ]


def test_search_input_is_bounded_and_operator_free(client, seeded):
    assert _search(client, "").get_json()["data"]["results"] == []
    assert _search(client, "x" * 101).status_code == 400
    assert _search(client, "a", page=0).status_code == 400
    data = _search(client, "calm & !( | ) :* <script>").get_json()["data"]
    assert data["terms"] == ["calm", "script"]
    from app.services.article_service import search_terms

    assert len(search_terms(" ".join(f"word{i}" for i in range(20)))) == 8


def test_search_is_rate_limited(app, client):
    from app.extensions import limiter

    was_enabled = limiter.enabled
    limiter.enabled = True
    try:
        codes = [_search(client, "calm").status_code for _ in range(62)]
    finally:
        limiter.enabled = was_enabled
        limiter.reset()
    assert codes[0] == 200 and 429 in codes


# ---- AI crawler policy and trust pages ----------------------------------------------------


def _site(client):
    return client.get("/api/v1/site").get_json()["data"]


def test_training_crawlers_are_blocked_until_approved_one_by_one(seeded, client):
    tokens = [t for t, _w, _x in AI_TRAINING_CRAWLERS]
    assert _site(client)["seo"]["blocked_training_crawlers"] == tokens
    for search_bot in ("OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "PerplexityBot"):
        assert search_bot not in tokens
    with seeded.app_context():
        db.session.add(SiteSetting(key=training_crawler_key("CCBot"), value=True))
        db.session.commit()
    assert "CCBot" not in _site(client)["seo"]["blocked_training_crawlers"]
    assert "GPTBot" in _site(client)["seo"]["blocked_training_crawlers"]


def test_policy_pages_are_linked_only_while_published(seeded, client):
    assert _site(client)["trust"] == {"editorial_policy": None, "corrections_policy": None}
    with seeded.app_context():
        db.session.add(
            Page(
                title="Editorial policy",
                slug="editorial-policy",
                path="/editorial-policy",
                status="draft",
            )
        )
        db.session.commit()
    assert _site(client)["trust"]["editorial_policy"] is None  # a draft is never claimed
    with seeded.app_context():
        page = db.session.scalar(select(Page).where(Page.path == "/editorial-policy"))
        page.status, page.published_path = "published", "/editorial-policy"
        page.published_snapshot = {"page": {"title": "How we write and check"}}
        db.session.commit()
    assert _site(client)["trust"]["editorial_policy"] == {
        "path": "/editorial-policy",
        "title": "How we write and check",
    }


# ---- Content-Security-Policy reports ------------------------------------------------------


def test_csp_reports_are_logged_without_visitor_details(client, caplog):
    report = {
        "csp-report": {
            "document-uri": "https://example.com/articles/calm?email=a@b.example#x",
            "violated-directive": "script-src-elem",
            "effective-directive": "script-src-elem",
            "blocked-uri": "https://tracker.example/x.js?id=secret",
        }
    }
    with caplog.at_level("WARNING"):
        res = client.post(
            "/api/v1/csp-report",
            data=json.dumps(report),
            headers={"Content-Type": "application/csp-report"},
        )
    assert res.status_code == 204 and res.data == b""
    [line] = [r.getMessage() for r in caplog.records if "CSP report" in r.getMessage()]
    assert line == "CSP report: script-src-elem blocked https://tracker.example on /articles/calm"
    assert "secret" not in caplog.text and "a@b.example" not in caplog.text
    # Reporting API bodies, junk and oversized bodies are all accepted quietly.
    reporting = [{"type": "csp-violation", "body": {"effectiveDirective": "img-src",
                  "blockedURL": "data", "documentURL": "https://example.com/"}}]  # fmt: skip
    assert client.post("/api/v1/csp-report", json=reporting).status_code == 204
    assert client.post("/api/v1/csp-report", data=b"not json").status_code == 204
    assert client.post("/api/v1/csp-report", data=b"x" * 20000).status_code == 204
