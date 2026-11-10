"""Editorial homepage: new section types, hiding rules, the daily newsletter wording,
switched-off website areas and the "load the editorial layout" builder action."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.cms.defaults import HOME_SECTIONS
from app.cms.sections import SECTION_TYPES
from app.extensions import db
from app.models import AnalyticsDailyPage, Article

from .test_commerce_catalogue import PRODUCTS, _create, _sellable, _upload
from .test_page_builder import HOMEPAGE, PAGES, _public_home, _save, _sections_payload

# The content-first homepage (Batch 14). "Featured digital products" (product_previews)
# is in the layout too but stays off the live site while the shop is switched off.
EDITORIAL_ORDER = [
    "hero",
    "featured_articles",
    "topics_grid",
    "popular_articles",
    "newsletter_cta",
    "latest_articles",
    "resource_showcase",
    "topic_articles",
    "brand_intro",
]


def _by_type(client):
    return {s["type"]: s for s in _public_home(client)["sections"]}


def _slugs(articles):
    return [a["slug"] for a in articles]


def _publish_home(api, sections):
    home = api.get(HOMEPAGE).get_json()["data"]
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    detail = saved.get_json()["data"]
    res = api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": detail["lock_version"]})
    assert res.status_code == 200, res.get_json()


def _edit_section(api, key, **content):
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    index = next(i for i, s in enumerate(home["sections"]) if s["key"] == key)
    section = sections[index]
    section["content"] = {**section["content"], **content}
    _publish_home(api, sections)


def _settings(api, **values):
    res = api.patch("/api/v1/admin/settings", {"values": values})
    assert res.status_code == 200, res.get_json()


def _free_resource(api, title, **extra):
    product = _create(
        api, title, product_type="checklist", short_description=f"{title}: a short guide.", **extra
    )
    assert _upload(api, product["id"]).status_code == 201
    api.patch(f"{PRODUCTS}/{product['id']}", {"pricing_model": "free"})
    api.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    return product


# ---- layout and article sections ----------------------------------------------------------


def test_default_homepage_is_the_editorial_layout_without_duplicates(seeded, client):
    sections = _public_home(client)["sections"]
    assert [s["type"] for s in sections] == EDITORIAL_ORDER
    by_type = {s["type"]: s for s in sections}
    # A compact introduction that keeps the headline.
    intro = by_type["hero"]
    assert intro["data"]["heading"] == "A Better Mindset. A Brighter Life."
    assert intro["design"]["spacing"] == "sm"
    featured = by_type["featured_articles"]
    assert featured["variant"] == "lead_with_two"
    assert 1 <= len(featured["data"]["articles"]) <= 3  # a lead and two stories alongside
    assert by_type["topics_grid"]["variant"] == "compact_4"
    assert by_type["topics_grid"]["data"]["heading"] == "Explore by topic"
    # Later sections leave out articles already shown above: no article appears twice.
    popular = by_type["popular_articles"]["data"]
    shown = (
        _slugs(featured["data"]["articles"])
        + _slugs(by_type["latest_articles"]["data"]["articles"])
        + _slugs(popular["articles"])
    )
    assert len(shown) == len(set(shown))
    # No reading statistics yet: never shown as "Most read". Featured articles may stand
    # in, under their own clearly named heading.
    if popular["articles"]:
        assert popular["fallback"] is True and popular["heading"] == "Editor's picks"
    else:
        assert popular["heading"] == "Trending this month"
    # Nothing hardcoded: no available resources is an empty list (the website hides it).
    assert by_type["resource_showcase"]["data"]["resources"] == []
    # Topics: only topics with published articles; rows by topic never repeat a story.
    assert all(t["article_count"] > 0 for t in by_type["topics_grid"]["data"]["topics"])
    for group in by_type["topic_articles"]["data"]["groups"]:
        assert group["articles"] and not set(_slugs(group["articles"])) & set(shown)
    # The community section never shows an unverified figure.
    assert by_type["brand_intro"]["data"]["heading"] == "Encouragement for real life"


def test_latest_articles_keep_their_old_behaviour_unless_deduplication_is_on(
    seeded, as_role, client
):
    api = as_role("website_manager")
    featured = _slugs(_by_type(client)["featured_articles"]["data"]["articles"])
    _edit_section(api, "latest", exclude_shown=False, count=12)
    latest = _slugs(_by_type(client)["latest_articles"]["data"]["articles"])
    assert set(featured) <= set(latest)  # existing sections (option off) show every article
    _edit_section(api, "latest", exclude_shown=True)
    latest = _slugs(_by_type(client)["latest_articles"]["data"]["articles"])
    assert not set(featured) & set(latest)


def test_editors_picks_follow_the_chosen_order_and_skip_unpublished(seeded, as_role, client):
    api = as_role("website_manager")
    # A "good news" collection is no longer in the default layout: add one, as an editor would.
    home = api.get(HOMEPAGE).get_json()["data"]
    _publish_home(
        api,
        _sections_payload(home)
        + [
            {
                "section_type": "article_collection",
                "variant": "grid_3",
                "content": {"heading": "Real stories of hope and change", "articles": []},
            }
        ],
    )
    with seeded.app_context():
        a, b, c = list(
            db.session.scalars(
                select(Article).where(Article.status == "published").order_by(Article.id)
            )
        )[:3]
        picks, expected = [c.id, a.id, b.id], [c.slug, a.slug]
    good_news = api.get(HOMEPAGE).get_json()["data"]["sections"][-1]["key"]
    _edit_section(api, good_news, articles=picks)
    with seeded.app_context():
        db.session.get(Article, picks[2]).status = "draft"  # unpublished after being picked
        db.session.commit()
    assert _slugs(_by_type(client)["article_collection"]["data"]["articles"]) == expected


def test_popular_articles_come_from_aggregate_statistics_only(seeded, as_role, client):
    with seeded.app_context():
        published = list(
            db.session.scalars(
                select(Article).where(Article.status == "published").order_by(Article.id)
            )
        )
        a, b, old, hidden = published[0], published[1], published[2], published[3]
        today = datetime.now(UTC).date()

        def views(article, n, days_ago):
            db.session.add(
                AnalyticsDailyPage(
                    day=today - timedelta(days=days_ago),
                    path=f"/articles/{article.slug}",
                    page_type="article",
                    content_type="article",
                    content_id=article.id,
                    views=n,
                    visitors=n,
                )
            )

        views(a, 5, 1)
        views(b, 4, 2)
        views(b, 5, 3)  # 9 in total: most read
        views(old, 500, 45)  # outside the 30-day window
        views(hidden, 50, 1)
        hidden.status = "draft"  # never listed once unpublished
        expected, old_slug = [b.slug, a.slug], old.slug
        db.session.commit()
    manager = as_role("website_manager")
    section = _by_type(client)["popular_articles"]
    assert section["data"]["fallback"] is False
    assert section["data"]["heading"] == "Trending this month"
    assert _slugs(section["data"]["articles"]) == expected
    assert "views" not in str(section) and "visitors" not in str(section)
    _edit_section(manager, "most-read", period="90")
    assert _slugs(_by_type(client)["popular_articles"]["data"]["articles"])[0] == old_slug


# ---- resources ----------------------------------------------------------------------------------


def test_resource_showcase_lists_only_available_published_resources(seeded, as_role, client):
    api = as_role("product_manager")
    free = _free_resource(api, "Morning reset checklist")
    assert api.post(f"{PRODUCTS}/{free['id']}/publish").status_code == 200
    _free_resource(api, "Unpublished draft checklist")  # never published
    _sellable(api, "Paid reflection workbook")
    # The starter catalogue (seeded) is "coming soon": never shown.
    section = _by_type(client)["resource_showcase"]
    [card] = section["data"]["resources"]
    assert card["title"] == "Morning reset checklist"
    assert card["description"] == "Morning reset checklist: a short guide."
    assert card["slug"] == "morning-reset-checklist" and card["is_free"] is True
    assert set(card) == {
        "slug",
        "title",
        "description",
        "type_label",
        "is_free",
        "cover",
        "cover_theme",
    }
    # The homepage asks for all available resources, but paid ones are promoted only while
    # the shop is switched on; never drafts or coming-soon items.
    manager = as_role("website_manager")
    _edit_section(manager, "resources", mode="all", count=9)
    titles = [r["title"] for r in _by_type(client)["resource_showcase"]["data"]["resources"]]
    assert titles == ["Morning reset checklist"]
    _settings(manager, **{"visibility.shop_public": True})
    titles = [r["title"] for r in _by_type(client)["resource_showcase"]["data"]["resources"]]
    assert sorted(titles) == ["Morning reset checklist", "Paid reflection workbook"]


def test_resource_showcase_manual_selection_keeps_order(seeded, as_role, client):
    api = as_role("product_manager")
    first = _free_resource(api, "First guide")
    second = _free_resource(api, "Second guide")
    for p in (first, second):
        assert api.post(f"{PRODUCTS}/{p['id']}/publish").status_code == 200
    with seeded.app_context():
        from app.models import Product

        ids = {p.title: p.id for p in db.session.scalars(select(Product))}
    _edit_section(
        as_role("website_manager"),
        "resources",
        mode="manual",
        products=[ids["Second guide"], ids["First guide"]],
    )
    titles = [r["title"] for r in _by_type(client)["resource_showcase"]["data"]["resources"]]
    assert titles == ["Second guide", "First guide"]


# ---- newsletter -----------------------------------------------------------------------------------


def test_newsletter_wording_is_daily_and_preference_keys_are_unchanged(seeded, client):
    site = client.get("/api/v1/site").get_json()["data"]["newsletter"]
    assert site["cadence"] == "daily"
    labels = {p["key"]: p["label"] for p in site["preferences"]}
    assert labels["weekly"] == "The Positive Reset — daily email"  # historical key kept
    assert site["default_preferences"] == ["weekly"]
    assert site["is_open"] is False and site["consent_text"] == ""  # nothing collected
    section = _by_type(client)["newsletter_cta"]
    assert section["data"]["eyebrow"] == "Daily newsletter" and section["data"]["is_open"] is False
    assert "each day" in section["data"]["description"]
    from app.services.newsletter import config

    assert "every day" in config.DEFAULT_CONSENT_TEXT
    assert "week" not in " ".join(
        v for k, v in config.PREFERENCES.items() if k in ("weekly", "daily")
    )


# ---- switched-off website areas -------------------------------------------------------------


def _nav_urls(client):
    nav = client.get("/api/v1/site").get_json()["data"]["navigation"]
    urls = []
    for item in nav["primary"] + (nav["mobile"] or []) + nav["legal"]:
        urls.append(item["url"])
        urls += [c["url"] for c in item.get("children") or []]
    for group in nav["footer"]:
        urls += [i["url"] for i in group["items"]]
    return [u for u in urls if u]


def test_shop_and_courses_are_left_out_until_switched_on(seeded, as_role, client):
    api = as_role("website_manager", "administrator")
    site = client.get("/api/v1/site").get_json()["data"]
    assert site["features"] == {"shop": False, "courses": False}
    urls = _nav_urls(client)
    assert "/free-resources" in urls and "/resources" in urls
    assert not [u for u in urls if re.match(r"^/(shop|cart|courses)(/|$)", u)]
    # The homepage's digital-products section is hidden on the website (shown in
    # previews with a note).
    home = api.get(HOMEPAGE).get_json()["data"]
    assert "product_previews" in [s["section_type"] for s in home["sections"]]
    assert "product_previews" not in _by_type(client)
    preview = api.post(f"{PAGES}/{home['id']}/preview").get_json()["data"]["page"]
    [promo] = [s for s in preview["sections"] if s["type"] == "product_previews"]
    assert "shop is switched off" in promo["preview_note"]

    _settings(api, **{"visibility.shop_public": True})
    assert client.get("/api/v1/site").get_json()["data"]["features"]["shop"] is True
    assert "/shop" in _nav_urls(client) and "/courses" not in _nav_urls(client)
    assert "product_previews" in _by_type(client)
    # Courses are not in the default menus; an editor's link to them shows only once
    # courses are switched on.
    footer = api.get("/api/v1/admin/navigation").get_json()["data"]
    footer = next(m for m in footer if m["key"] == "footer")["items"]
    footer[0]["children"].append({"label": "Courses", "url": "/courses"})
    assert api.put("/api/v1/admin/navigation/footer", {"items": footer}).status_code == 200
    assert "/courses" not in _nav_urls(client)
    _settings(api, **{"visibility.courses_public": True})
    assert "/courses" in _nav_urls(client)


def test_hidden_destinations_match_whole_path_segments():
    from app.services.navigation_service import is_hidden_destination

    hidden = ("/shop", "/cart", "/courses")
    for url in ("/shop", "/shop/", "/shop/calm-workbook", "/cart?x=1", "/courses#top"):
        assert is_hidden_destination(url, hidden), url
    for url in ("/shopping-guide", "/free-resources", "/resources", "https://example.org/shop", ""):
        assert not is_hidden_destination(url, hidden), url


# ---- builder: load the editorial layout into the draft ----------------------------------------


def test_editorial_layout_loads_into_the_draft_only_and_keeps_seo(seeded, as_role, client):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)[:2]
    sections[0]["content"]["heading"] = "Our own layout"
    saved = _save(api, home, sections, seo_title="Positive living, every day")
    detail = saved.get_json()["data"]
    res = api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": detail["lock_version"]})
    detail = res.get_json()["data"]
    revisions_before = len(api.get(f"{PAGES}/{home['id']}/revisions").get_json()["data"])

    assert api.post(f"{HOMEPAGE}/editorial-layout", {"lock_version": 1}).status_code == 409
    assert as_role("analyst").post(f"{HOMEPAGE}/editorial-layout", {}).status_code == 403
    res = api.post(f"{HOMEPAGE}/editorial-layout", {"lock_version": detail["lock_version"]})
    assert res.status_code == 200, res.get_json()
    draft = res.get_json()["data"]
    assert [s["key"] for s in draft["sections"]] == [s["key"] for s in HOME_SECTIONS]
    assert draft["seo_title"] == "Positive living, every day"  # SEO fields are kept
    assert draft["has_unpublished_changes"] and draft["status"] == "published"
    # The live homepage is unchanged until someone publishes; the old draft is in History.
    live = _public_home(client)["sections"]
    assert len(live) == 2 and live[0]["data"]["heading"] == "Our own layout"
    revisions = api.get(f"{PAGES}/{home['id']}/revisions").get_json()["data"]
    assert len(revisions) == revisions_before + 1 and revisions[0]["kind"] == "draft_backup"


def test_editorial_layout_is_homepage_only(seeded, as_role):
    import pytest

    from app.models import Page, User
    from app.services.admin import page_admin
    from app.utils.errors import ConflictError

    from .conftest import make_user

    api = as_role("website_manager")
    page = api.post(PAGES, {"title": "Spring", "template": "standard"}).get_json()["data"]
    make_user(seeded, "layout-owner@example.org", ["super_admin"])
    with seeded.app_context():
        model = db.session.get(Page, page["id"])
        user = db.session.scalar(select(User).where(User.email == "layout-owner@example.org"))
        with pytest.raises(ConflictError):
            page_admin.load_editorial_layout(model, user, model.lock_version)


# ---- frontend registry stays in step with the section types ---------------------------------


def test_every_section_type_has_a_frontend_component():
    registry = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "sections"
        / "registry.js"
    ).read_text(encoding="utf-8")
    block = registry.split("export const SECTION_COMPONENTS = {", 1)[1].split("};", 1)[0]
    keys = set(re.findall(r"^\s*([a-z_]+):", block, re.M))
    assert keys == set(SECTION_TYPES) - {"section_group"}


def test_most_read_falls_back_to_named_featured_articles_without_statistics(
    seeded, as_role, client
):
    """No reading statistics: featured articles appear under "Editor's picks" (never
    called most read). With the fallback off the section is simply empty (hidden)."""
    manager = as_role("website_manager")
    # Enough featured articles that some remain after the stories shown above.
    _edit_section(manager, "latest", count=1)
    with seeded.app_context():
        for article in db.session.scalars(select(Article).where(Article.status == "published")):
            article.featured = True
        db.session.commit()
    home = _by_type(client)
    section = home["popular_articles"]["data"]
    assert section["fallback"] is True and section["heading"] == "Editor's picks"
    # The fallback never repeats a story shown above it, and the latest articles below
    # leave out what it shows.
    above = _slugs(home["featured_articles"]["data"]["articles"])
    assert not set(_slugs(section["articles"])) & set(above)
    below = _slugs(home["latest_articles"]["data"]["articles"])
    assert not set(_slugs(section["articles"])) & set(below)
    with seeded.app_context():
        featured = set(
            db.session.scalars(
                select(Article.slug).where(Article.status == "published", Article.featured)
            )
        )
    assert section["articles"] and set(_slugs(section["articles"])) <= featured
    _edit_section(manager, "most-read", fallback="none")
    section = _by_type(client)["popular_articles"]["data"]
    assert section["articles"] == [] and section["heading"] == "Trending this month"
