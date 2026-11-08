"""The article sidebar (Admin › Article sidebar) and the article reading links.

The sidebar is a CMS system page without an address: editors reorder, hide, rename and
size its sections in the page builder; the article API returns it resolved for each
article, never repeating the article itself or the related articles shown under it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.cms.defaults import SIDEBAR_SECTIONS
from app.cms.sections import SIDEBAR_TYPES
from app.extensions import db
from app.models import AnalyticsDailyPage, Article, Page

from .test_page_builder import PAGES, _save, _sections_payload

SIDEBAR = "/api/v1/admin/article-sidebar"


def _published(app):
    with app.app_context():
        return [
            (a.id, a.slug)
            for a in db.session.scalars(
                select(Article)
                .where(Article.status == "published")
                .order_by(Article.published_at.desc(), Article.id.desc())
            )
        ]


def _article(client, slug):
    res = client.get(f"/api/v1/articles/{slug}")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _by_type(data):
    return {s["type"]: s for s in data["sidebar"]}


def _publish(api, sections):
    page = api.get(SIDEBAR).get_json()["data"]
    saved = _save(api, page, sections)
    assert saved.status_code == 200, saved.get_json()
    detail = saved.get_json()["data"]
    res = api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": detail["lock_version"]})
    assert res.status_code == 200, res.get_json()
    return res


def test_default_sidebar_sections_in_order(seeded, client):
    slug = _published(seeded)[0][1]
    data = _article(client, slug)
    types = [s["type"] for s in data["sidebar"]]
    assert types == [s["section_type"] for s in SIDEBAR_SECTIONS]
    assert types == [
        "popular_articles",
        "related_articles",
        "newsletter_cta",
        "featured_articles",
        "topics_grid",
    ]
    by_type = _by_type(data)
    assert by_type["newsletter_cta"]["data"]["newsletter_name"] == "The Positive Reset"
    # No advertising by default.
    assert not {"sponsored_banner", "brand_spotlight"} & set(types)


def test_sidebar_never_repeats_the_article_or_its_related_list(seeded, client):
    slug = _published(seeded)[0][1]
    data = _article(client, slug)
    under_article = {a["slug"] for a in data["related"]}
    for section in data["sidebar"]:
        for article in section["data"].get("articles", []):
            assert article["slug"] != slug
            assert article["slug"] not in under_article
    related = _by_type(data)["related_articles"]["data"]["articles"]
    assert related, "seeded articles share topics"
    assert len(related) <= 4


def test_related_articles_prefer_the_same_topic(seeded, client):
    slug = _published(seeded)[0][1]
    data = _article(client, slug)
    topic = data["article"]["topic"]["slug"]
    candidates = data["related"] + _by_type(data)["related_articles"]["data"]["articles"]
    same = [a["topic"]["slug"] == topic for a in candidates if a.get("topic")]
    # Same-topic articles come first.
    assert same == sorted(same, reverse=True)


def test_sidebar_popular_uses_statistics_without_counts(seeded, client):
    rows = _published(seeded)
    current_id, current = rows[0]
    # An article outside the related list under the article (those are never repeated).
    related = {a["slug"] for a in _article(client, current)["related"]}
    other_id, other = next(r for r in rows[1:] if r[1] not in related)
    with seeded.app_context():
        today = datetime.now(UTC).date()
        for content_id, slug, n in ((current_id, current, 90), (other_id, other, 40)):
            db.session.add(
                AnalyticsDailyPage(
                    day=today - timedelta(days=1),
                    path=f"/articles/{slug}",
                    page_type="article",
                    content_type="article",
                    content_id=content_id,
                    views=n,
                    visitors=n,
                )
            )
        db.session.commit()
    popular = _by_type(_article(client, current))["popular_articles"]
    slugs = [a["slug"] for a in popular["data"]["articles"]]
    assert current not in slugs  # the article being read is never "popular" beside itself
    assert slugs == [other]
    assert "views" not in str(popular) and "visitors" not in str(popular)


def test_editors_reorder_hide_rename_and_resize(seeded, as_role, client):
    api = as_role("website_manager")
    page = api.get(SIDEBAR).get_json()["data"]
    assert page["is_sidebar"] is True and page["path"] is None
    assert page["template_label"] == "Article sidebar"
    sections = _sections_payload(page)
    by_type = {s["section_type"]: s for s in sections}
    by_type["topics_grid"]["content"]["heading"] = "Browse topics"
    by_type["related_articles"]["content"]["count"] = 2
    by_type["popular_articles"]["is_visible"] = False
    _publish(
        api, [by_type["topics_grid"], by_type["related_articles"], by_type["popular_articles"]]
    )

    data = _article(client, _published(seeded)[0][1])
    assert [s["type"] for s in data["sidebar"]] == ["topics_grid", "related_articles"]
    assert data["sidebar"][0]["data"]["heading"] == "Browse topics"
    assert len(data["sidebar"][1]["data"]["articles"]) <= 2


def test_manual_editors_picks(seeded, as_role, client):
    api = as_role("website_manager")
    rows = _published(seeded)
    pick_id, pick = rows[-1]
    page = api.get(SIDEBAR).get_json()["data"]
    sections = _sections_payload(page)
    picks = next(s for s in sections if s["section_type"] == "featured_articles")
    picks["content"] = {**picks["content"], "mode": "manual", "articles": [pick_id]}
    _publish(api, sections)
    data = _article(client, rows[0][1])
    [section] = [s for s in data["sidebar"] if s["type"] == "featured_articles"]
    assert [a["slug"] for a in section["data"]["articles"]] == [pick]
    # Beside the picked article itself, the pick is left out rather than repeated.
    beside_itself = [
        s for s in _article(client, pick)["sidebar"] if s["type"] == "featured_articles"
    ]
    assert beside_itself[0]["data"]["articles"] == []


def test_sidebar_accepts_only_compact_section_types(seeded, as_role):
    api = as_role("website_manager")
    page = api.get(SIDEBAR).get_json()["data"]
    hero = {
        "section_type": "hero",
        "variant": "split",
        "content": {"heading": "Big"},
        "design": {},
        "is_visible": True,
    }
    res = _save(api, page, [*_sections_payload(page), hero])
    assert res.status_code == 400
    assert "article sidebar" in str(res.get_json())
    # ...and the sidebar-only section can't be put on an ordinary page.
    assert "related_articles" in SIDEBAR_TYPES
    home = api.get("/api/v1/admin/homepage").get_json()["data"]
    related = {
        "section_type": "related_articles",
        "variant": "list",
        "content": {"heading": "Related", "count": 3},
        "design": {},
        "is_visible": True,
    }
    res = _save(api, home, [*_sections_payload(home), related])
    assert res.status_code == 400
    assert "only available in the article sidebar" in str(res.get_json())


def test_sidebar_is_never_a_public_page(seeded, as_role, client):
    api = as_role("website_manager")
    page = api.get(SIDEBAR).get_json()["data"]
    caps = page["capabilities"]
    assert caps["publish"] and not caps["unpublish"] and not caps["archive"]
    assert not caps["duplicate"] and not caps["change_slug"]
    _publish(api, _sections_payload(page))
    with seeded.app_context():
        row = db.session.scalar(select(Page).where(Page.slug == "article-sidebar"))
        assert row.status == "published" and row.published_path is None
    listed = client.get("/api/v1/pages").get_json()["data"]
    assert all("sidebar" not in (p.get("path") or "") for p in listed)
    assert "article-sidebar" not in client.get("/sitemap.xml").get_data(as_text=True)
    # Its address can't be set.
    detail = api.get(SIDEBAR).get_json()["data"]
    res = _save(api, detail, slug="sidebar")
    assert res.status_code == 400


def test_sidebar_requires_homepage_permissions(seeded, as_role):
    assert as_role("analyst").get(SIDEBAR).status_code == 403


def test_previous_and_next_articles(seeded, client):
    rows = _published(seeded)  # newest first
    newest, middle, oldest = rows[0][1], rows[1][1], rows[-1][1]
    adjacent = _article(client, middle)["adjacent"]
    assert adjacent["next"]["slug"] == newest
    assert adjacent["previous"]["slug"] == rows[2][1]
    assert "body" not in adjacent["next"]
    assert _article(client, newest)["adjacent"]["next"] is None
    assert _article(client, oldest)["adjacent"]["previous"] is None


# ---- the authors index ----------------------------------------------------------------------


def test_authors_index_lists_bios_and_is_in_the_sitemap_only_with_author_pages(seeded, client):
    from .test_technical_release import _make_person

    def sitemap_paths():
        return {e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]}

    assert client.get("/api/v1/authors").get_json()["data"] == []
    assert "/authors" not in sitemap_paths()  # nothing to list: not offered to search engines
    with seeded.app_context():
        from app.models import Author

        slug = db.session.scalar(select(Author.slug))
    _make_person(seeded, slug, bio="Writes about resilience.")
    [entry] = client.get("/api/v1/authors").get_json()["data"]
    assert entry["slug"] == slug and entry["bio"] == "Writes about resilience."
    assert "image" in entry and entry["article_count"] > 0
    assert "/authors" in sitemap_paths()


def test_authors_is_reserved_for_the_website(seeded, as_role):
    api = as_role("website_manager")
    res = api.post(PAGES, {"title": "Authors", "slug": "authors", "template": "standard"})
    assert res.status_code == 400
    assert "reserved" in str(res.get_json())
