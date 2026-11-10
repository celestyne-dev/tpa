"""Batch 14: the content-first navigation (topic groups, Resources, footer columns), only
valid destinations in menus, the /topics hub in the sitemap, and the Recommended Books &
Tools page built from the existing affiliate links."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.cms.defaults import TOPIC_GROUPS
from app.extensions import db
from app.models import NavigationMenu, Topic

from .test_page_builder import PAGES

ADMIN = "/api/v1/admin"


def _nav(client):
    return client.get("/api/v1/site").get_json()["data"]["navigation"]


def _drop_saved_menus(app):
    with app.app_context():
        for menu in db.session.scalars(select(NavigationMenu)):
            db.session.delete(menu)
        db.session.commit()


def _publish(api, page):
    detail = api.get(f"{PAGES}/{page['id']}").get_json()["data"]
    res = api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": detail["lock_version"]})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---- topic groups ---------------------------------------------------------------------------


def test_topics_are_grouped_once_by_keyword_and_empty_topics_are_left_out(seeded, app):
    from app.services.topic_links import group_anchor, grouped_topic_links

    with app.app_context():
        groups = grouped_topic_links(TOPIC_GROUPS, 6)
        assert list(groups) == ["Mindset", "Wellbeing", "Relationships", "Career & Growth"]
        urls = [link["url"] for links in groups.values() for link in links]
        assert len(urls) == len(set(urls))  # each topic is listed once
        assert "/topics/positive-mindset" in [li["url"] for li in groups["Mindset"]]
        assert "/topics/relationships-boundaries" in [li["url"] for li in groups["Relationships"]]
        assert "/topics/habits-intentional-living" in [
            li["url"] for li in groups["Career & Growth"]
        ]
        # A topic without published articles is never placed in a menu.
        db.session.add(Topic(slug="mindful-mornings", name="Mindful Mornings", status="active"))
        db.session.commit()
        regrouped = grouped_topic_links(TOPIC_GROUPS, 6)
        assert "/topics/mindful-mornings" not in [
            li["url"] for links in regrouped.values() for li in links
        ]
        # The anchor of each group on /topics.
        assert group_anchor("Career & Growth") == "career-growth"


def test_default_navigation_is_content_first(seeded, app, client):
    _drop_saved_menus(app)
    nav = _nav(client)
    labels = [i["label"] for i in nav["primary"]]
    assert labels == [
        "Mindset",
        "Wellbeing",
        "Relationships",
        "Career & Growth",
        "Resources",
        "Newsletter",
    ]
    # Corporate pages live in the footer, not the header.
    assert not {"About", "Contact", "Partner With Us"} & set(labels)
    mindset = nav["primary"][0]["children"]
    assert all(c["url"].startswith("/topics/") for c in mindset[:-1])
    assert mindset[-1] == {
        "label": "All articles",
        "url": "/articles",
        "external": False,
        "open_in_new_tab": False,
        "visibility": "all",
    }
    resources = [c["label"] for c in nav["primary"][4]["children"]]
    # The shop is off and the recommendations page is unpublished: both are left out.
    assert resources == ["All Resources", "Free Downloads", "My Library"]
    footer = {g["title"]: [i["label"] for i in g["items"]] for g in nav["footer"]}
    assert list(footer) == ["Explore", "Resources", "About", "Legal"]
    assert footer["Explore"] == ["Articles", *[label for label, _ in TOPIC_GROUPS]]
    assert footer["Resources"] == ["Resource Library", "Free Resources"]
    assert footer["About"] == ["Our Story", "Partner With Us", "Contact", "Newsletter"]
    explore = {i["label"]: i["url"] for i in nav["footer"][0]["items"]}
    assert explore["Career & Growth"] == "/topics#career-growth"


def test_a_topic_group_without_topics_is_left_out(seeded, app, client):
    _drop_saved_menus(app)
    with app.app_context():
        topic = db.session.scalar(select(Topic).where(Topic.slug == "relationships-boundaries"))
        topic.status = "hidden"
        db.session.commit()
    nav = _nav(client)
    assert "Relationships" not in [i["label"] for i in nav["primary"]]
    assert "Relationships" not in [i["label"] for i in nav["footer"][0]["items"]]


def test_admin_menus_offer_the_recommended_structure_without_saving_it(seeded, as_role):
    api = as_role("website_manager")
    menus = {m["key"]: m for m in api.get(f"{ADMIN}/navigation").get_json()["data"]}
    primary = menus["primary"]
    labels = [i["label"] for i in primary["recommended"]]
    assert labels[:4] == ["Mindset", "Wellbeing", "Relationships", "Career & Growth"]
    assert labels[-2:] == ["Resources", "Newsletter"]
    # The saved menu is untouched until an administrator loads and saves the suggestion.
    assert [i["label"] for i in primary["items"]] == labels
    # Saving the suggestion as it is passes validation.
    res = api.put(f"{ADMIN}/navigation/footer", {"items": menus["footer"]["recommended"]})
    assert res.status_code == 200, res.get_json()
    res = api.put(f"{ADMIN}/navigation/primary", {"items": primary["recommended"]})
    assert res.status_code == 200, res.get_json()
    assert any("/recommended does not point" in w for w in res.get_json()["data"]["warnings"])


# ---- only valid destinations ------------------------------------------------------------------


def test_menus_leave_out_links_to_pages_that_do_not_exist(seeded, as_role, client):
    api = as_role("website_manager")
    res = api.put(
        f"{ADMIN}/navigation/primary",
        {
            "items": [
                {"label": "Articles", "url": "/articles"},
                {"label": "Spring", "url": "/spring-reset"},
                {"label": "Search", "url": "/search?q=calm"},
                {"label": "Library", "url": "/account/library"},
                {"label": "Topics", "url": "/topics"},
                {"label": "Page two", "url": "/articles/page/2"},
                {"label": "LinkedIn", "link_type": "external", "url": "https://www.linkedin.com"},
            ]
        },
    )
    assert res.status_code == 200, res.get_json()
    labels = [i["label"] for i in _nav(client)["primary"]]
    assert labels == ["Articles", "Search", "Library", "Topics", "Page two", "LinkedIn"]
    # Once the page is published the link appears.
    page = api.post(PAGES, {"title": "Spring Reset", "template": "standard"}).get_json()["data"]
    _publish(api, page)
    assert "Spring" in [i["label"] for i in _nav(client)["primary"]]


def test_shop_link_appears_only_when_the_shop_is_on(seeded, as_role, app, client):
    _drop_saved_menus(app)
    api = as_role("website_manager", "administrator")
    assert "/shop" not in [c["url"] for c in _nav(client)["primary"][4]["children"]]
    res = api.patch(f"{ADMIN}/settings", {"values": {"visibility.shop_public": True}})
    assert res.status_code == 200
    resources = [c["url"] for c in _nav(client)["primary"][4]["children"]]
    assert resources == ["/resources", "/free-resources", "/shop", "/account/library"]


# ---- /topics hub ----------------------------------------------------------------------------


def test_topics_hub_is_in_the_sitemap_and_mirrors_the_frontend(seeded, client):
    paths = {e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]}
    assert "/topics" in paths
    navigation = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "config" / "navigation.js"
    ).read_text(encoding="utf-8")
    assert "path: routes.topics, priority: 0.7" in navigation


# ---- Recommended Books & Tools ------------------------------------------------------------------


def test_recommended_page_uses_affiliate_links_and_is_linked_once_published(
    seeded, as_role, app, client
):
    _drop_saved_menus(app)
    aff = as_role("affiliate_manager", email="aff@example.org")
    program = aff.post(
        f"{ADMIN}/affiliate-programs", {"name": "Books", "merchant": "Bookshop", "currency": "USD"}
    ).get_json()["data"]
    link = aff.post(
        f"{ADMIN}/affiliate-links",
        {
            "name": "The Calm Book",
            "slug": "the-calm-book",
            "program_id": program["id"],
            "target_url": "https://bookshop.example/calm",
        },
    ).get_json()["data"]

    api = as_role("website_manager")
    page = api.post(
        PAGES, {"title": "Recommended Books & Tools", "template": "recommended_books_tools"}
    ).get_json()["data"]
    assert page["path"] == "/recommended" and page["status"] == "draft"
    detail = api.get(f"{PAGES}/{page['id']}").get_json()["data"]
    types = [s["section_type"] for s in detail["sections"]]
    assert types.count("affiliate_recommendations") == 3

    # Put the link in the "Books" group, with a category label and a note.
    sections = [
        {
            k: s[k]
            for k in ("id", "name", "section_type", "variant", "content", "design", "is_visible")
        }
        | {"visibility": s["visibility"], "reusable_section_id": s["reusable_section_id"]}
        for s in detail["sections"]
    ]
    books = types.index("affiliate_recommendations")
    sections[books]["content"] = {
        **sections[books]["content"],
        "links": [link["id"]],
        "items": [{"category": "Book", "note": "Short, kind chapters."}],
    }
    saved = api.put(
        f"{PAGES}/{page['id']}/draft",
        {"lock_version": detail["lock_version"], "sections": sections},
    )
    assert saved.status_code == 200, saved.get_json()

    # Not linked while it is a draft.
    assert "/recommended" not in [c["url"] for c in _nav(client)["primary"][4]["children"]]
    _publish(api, page)
    assert "/recommended" in [c["url"] for c in _nav(client)["primary"][4]["children"]]

    live = client.get("/api/v1/pages/resolve?path=/recommended").get_json()["data"]
    groups = [s for s in live["sections"] if s["type"] == "affiliate_recommendations"]
    [card] = groups[0]["data"]["links"]
    assert card["href"].startswith("/api/v1/go/")  # an external affiliate link, not a download
    assert card["sponsored"] is True and card["merchant"] == "Bookshop"  # from the programme
    assert card["category"] == "Book" and card["note"] == "Short, kind chapters."
    assert groups[0]["data"]["disclosure"]
    # Empty groups render no links (the website hides them).
    assert groups[1]["data"]["links"] == [] and groups[2]["data"]["links"] == []
