"""Batch 04: homepage builder, CMS pages, shared sections, branding, navigation,
announcements, SEO, publishing integration and permissions."""

from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import Page, PublishJob, Redirect
from app.services import page_render, publication_service

from .conftest import make_photo, make_png

HOMEPAGE = "/api/v1/admin/homepage"
PAGES = "/api/v1/admin/pages"


def _jobs(app) -> int:
    with app.app_context():
        return db.session.query(PublishJob).count()


def _pending_reasons(app) -> list[str]:
    with app.app_context():
        jobs = db.session.query(PublishJob).filter_by(status="pending").all()
        return [r for job in jobs for r in (job.reasons or [])]


def _public_home(client):
    return client.get("/api/v1/pages/resolve?path=/").get_json()["data"]


def _sections_payload(detail):
    return [
        {
            k: s[k]
            for k in ("id", "name", "section_type", "variant", "content", "design", "is_visible")
        }
        | {"visibility": s["visibility"], "reusable_section_id": s["reusable_section_id"]}
        for s in detail["sections"]
    ]


def _save(api, page, sections=None, **meta):
    body = {"lock_version": page["lock_version"]}
    if sections is not None:
        body["sections"] = sections
    if meta:
        body["page"] = meta
    return api.put(f"{PAGES}/{page['id']}/draft", body)


def _upload(api, data=None, name="photo.jpg"):
    res = api.upload("/api/v1/admin/media", data or make_photo(1600, 1000), name, alt_text="Hills")
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]["id"]


# ---- homepage drafts and publishing --------------------------------------------------------


def test_homepage_draft_is_private_until_published(seeded, as_role, client):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    assert home["is_home"] and home["status"] == "published" and not home["has_unpublished_changes"]
    assert [s["section_type"] for s in home["sections"]][:2] == ["hero", "brand_intro"]
    public = _public_home(client)
    assert public["sections"][0]["data"]["heading"] == "A Better Mindset."
    jobs = _jobs(seeded)

    sections = _sections_payload(home)
    sections[0]["content"]["heading"] = "Grow Through Every Season."
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    draft = saved.get_json()["data"]
    assert draft["has_unpublished_changes"] and draft["lock_version"] == home["lock_version"] + 1
    # Saving a draft changes nothing publicly and queues no rebuild.
    assert _public_home(client)["sections"][0]["data"]["heading"] == "A Better Mindset."
    assert _jobs(seeded) == jobs

    preview = api.post(f"{PAGES}/{home['id']}/preview").get_json()["data"]["page"]
    assert preview["sections"][0]["data"]["heading"] == "Grow Through Every Season."
    res = api.post(f"{PAGES}/{home['id']}/preview")
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["X-Robots-Tag"] == "noindex, nofollow"

    published = api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": draft["lock_version"]})
    assert published.status_code == 200, published.get_json()
    assert not published.get_json()["data"]["has_unpublished_changes"]
    assert _public_home(client)["sections"][0]["data"]["heading"] == "Grow Through Every Season."
    assert _jobs(seeded) == jobs + 1


def test_unsaved_changes_preview_never_writes(seeded, as_role):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections[0]["content"]["heading"] = "Only in the preview"
    data = api.post(f"{PAGES}/{home['id']}/preview", {"sections": sections}).get_json()["data"]
    assert data["page"]["sections"][0]["data"]["heading"] == "Only in the preview"
    again = api.get(HOMEPAGE).get_json()["data"]
    assert again["lock_version"] == home["lock_version"]
    assert again["sections"][0]["content"]["heading"] == "A Better Mindset."


def test_concurrent_edits_conflict_instead_of_overwriting(seeded, as_role):
    a = as_role("website_manager")
    b = as_role("administrator")
    home = a.get(HOMEPAGE).get_json()["data"]
    first = _save(a, home, title="Homepage (A)")
    assert first.status_code == 200
    stale = _save(b, home, title="Homepage (B)")
    assert stale.status_code == 409
    error = stale.get_json()["error"]
    assert (
        error["code"] == "edit_conflict"
        and error["details"]["lock_version"] == home["lock_version"] + 1
    )


def test_reorder_add_duplicate_hide_and_validation(seeded, as_role, client):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections.reverse()
    sections.append(
        {
            "section_type": "quote",
            "variant": "highlighted",
            "content": {"quote": "Progress, not perfection.", "attribution": "TPA"},
            "design": {"background": "sage", "align": "center"},
        }
    )
    sections.append({**sections[-1], "content": {"quote": "Copy of the quote."}})
    sections[1]["is_visible"] = False
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    detail = saved.get_json()["data"]
    assert detail["sections"][0]["section_type"] == "call_to_action"
    assert [s["section_type"] for s in detail["sections"][-2:]] == ["quote", "quote"]
    assert len({s["key"] for s in detail["sections"]}) == len(detail["sections"])
    hidden_key = detail["sections"][1]["key"]
    api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": detail["lock_version"]})
    public = _public_home(client)
    assert hidden_key not in [s["key"] for s in public["sections"]]
    assert public["sections"][-1]["design"] == {
        "background": "sage",
        "spacing": "md",
        "align": "center",
    }

    detail = api.get(HOMEPAGE).get_json()["data"]
    bad = _sections_payload(detail)
    bad[0]["variant"] = "spinning-3d"
    bad[0]["design"] = {"background": "#ff00ff"}
    bad[1]["design"] = {"background": "ivory"}  # partnership sections have no background option
    bad[2]["content"] = {**bad[2]["content"], "script": "<script>"}
    bad.append({"section_type": "html_embed", "content": {"html": "<iframe>"}})
    bad.append({"section_type": "hero", "content": {"heading": "Second hero"}})
    res = _save(api, detail, bad)
    assert res.status_code == 400
    details = res.get_json()["error"]["details"]
    assert "sections.0.variant" in details
    assert "sections.0.design.background" in details
    assert details["sections.1.design"] == ["Not available for this section: background."]
    assert details["sections.2.content"] == ["Unknown field(s): script."]
    assert f"sections.{len(bad) - 2}.section_type" in details  # unknown type rejected
    assert f"sections.{len(bad) - 1}.section_type" in details  # only one hero per page


def test_layout_and_link_validation_by_section_type(seeded, as_role):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections[0]["content"]["primary_cta"] = {"label": "Go", "url": "javascript:alert(1)"}
    sections[0]["variant"] = "full_width"  # needs an image
    sections.append(
        {
            "section_type": "featured_articles",
            "content": {"heading": "Picks", "mode": "manual", "articles": [999]},
        }
    )
    res = _save(api, home, sections)
    details = res.get_json()["error"]["details"]
    assert res.status_code == 400
    assert "sections.0.content.primary_cta.url" in details
    assert "sections.0.content.media" in details
    assert details[f"sections.{len(sections) - 1}.content.articles.0"] == [
        "This article no longer exists."
    ]


def test_revisions_restore_into_draft(seeded, as_role, client):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections[0]["content"]["heading"] = "Version two"
    detail = _save(api, home, sections).get_json()["data"]
    detail = api.post(
        f"{PAGES}/{home['id']}/publish", {"lock_version": detail["lock_version"]}
    ).get_json()["data"]
    revisions = api.get(f"{PAGES}/{home['id']}/revisions").get_json()["data"]
    assert [r["number"] for r in revisions] == [2, 1]
    first = revisions[-1]
    shown = api.get(f"{PAGES}/{home['id']}/revisions/{first['id']}").get_json()["data"]
    assert shown["sections"][0]["heading"] == "A Better Mindset."

    restored = api.post(
        f"{PAGES}/{home['id']}/revisions/{first['id']}/restore",
        {"lock_version": detail["lock_version"]},
    ).get_json()["data"]
    assert restored["sections"][0]["content"]["heading"] == "A Better Mindset."
    assert restored["has_unpublished_changes"]
    assert _public_home(client)["sections"][0]["data"]["heading"] == "Version two"
    api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": restored["lock_version"]})
    assert _public_home(client)["sections"][0]["data"]["heading"] == "A Better Mindset."


def test_discard_draft_returns_to_live_version(seeded, as_role):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)[:2]
    detail = _save(api, home, sections).get_json()["data"]
    assert len(detail["sections"]) == 2
    back = api.post(f"{PAGES}/{home['id']}/discard").get_json()["data"]
    assert len(back["sections"]) == 9 and not back["has_unpublished_changes"]


def test_fresh_install_serves_default_homepage(app, client):
    page = client.get("/api/v1/pages/resolve?path=/")
    assert page.status_code == 200
    assert [s["type"] for s in page.get_json()["data"]["sections"]][0] == "hero"


# ---- CMS pages -----------------------------------------------------------------------------------


def _create(api, **data):
    res = api.post(PAGES, {"title": "Spring Reset", "template": "landing", **data})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def test_page_templates_create_editable_starter_sections(seeded, as_role):
    api = as_role("website_manager")
    templates = {t["key"]: t for t in api.get("/api/v1/admin/page-templates").get_json()["data"]}
    assert set(templates) == {
        "standard",
        "landing",
        "newsletter",
        "lead_magnet",
        "campaign",
        "partnership",
        "coming_soon",
    }
    for key in templates:
        page = _create(api, title=f"Template {key}", template=key)
        assert page["status"] == "draft" and page["sections"], key
        assert page["path"] == f"/template-{key.replace('_', '-')}"
    coming = api.get(f"{PAGES}?q=coming").get_json()["data"][0]
    detail = api.get(f"{PAGES}/{coming['id']}").get_json()["data"]
    assert "product_previews" in [s["section_type"] for s in detail["sections"]]


def test_page_lifecycle_slug_redirect_sitemap_and_404(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api)
    assert client.get("/api/v1/pages/resolve?path=/spring-reset").status_code == 404  # draft
    page = _save(
        api,
        page,
        seo_title="Spring Reset Guide",
        meta_description="A short guide to a gentle spring reset.",
    ).get_json()["data"]
    page = api.post(
        f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]}
    ).get_json()["data"]
    live = client.get("/api/v1/pages/resolve?path=/spring-reset").get_json()["data"]
    assert live["seo"]["title"] == "Spring Reset Guide" and live["sections"]
    assert any(p["path"] == "/spring-reset" for p in client.get("/api/v1/pages").get_json()["data"])
    sitemap = client.get("/api/v1/sitemap").get_json()["data"]
    assert any(e["path"] == "/spring-reset" for e in sitemap)

    page = _save(api, page, slug="gentle-spring-reset").get_json()["data"]
    assert page["path"] == "/gentle-spring-reset" and page["live_path"] == "/spring-reset"
    assert any("redirect" in w for w in page["warnings"])
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    with seeded.app_context():
        redirect = db.session.query(Redirect).filter_by(source_path="/spring-reset").one()
        assert redirect.destination == "/gentle-spring-reset" and redirect.status_code == 301
    assert client.get("/_redirect/spring-reset").status_code == 301
    assert client.get("/api/v1/pages/resolve?path=/spring-reset").status_code == 404

    # noindex pages leave the sitemap; unpublished pages disappear.
    page = api.get(f"{PAGES}/{page['id']}").get_json()["data"]
    page = _save(api, page, noindex=True).get_json()["data"]
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    sitemap = client.get("/api/v1/sitemap").get_json()["data"]
    assert not any(e["path"] == "/gentle-spring-reset" for e in sitemap)
    api.post(f"{PAGES}/{page['id']}/unpublish")
    assert client.get("/api/v1/pages/resolve?path=/gentle-spring-reset").status_code == 404
    archived = api.post(f"{PAGES}/{page['id']}/archive").get_json()["data"]
    assert archived["status"] == "archived"
    assert all(p["id"] != page["id"] for p in api.get(PAGES).get_json()["data"])


def test_reserved_routes_and_slug_collisions(seeded, as_role):
    api = as_role("website_manager")
    for slug in ("admin", "api", "articles", "topics", "shop", "media", "login"):
        res = api.post(PAGES, {"title": "X", "slug": slug})
        assert res.status_code == 400, slug
        assert "reserved" in res.get_json()["error"]["details"]["slug"][0]
    assert api.post(PAGES, {"title": "Bad", "slug": "Not A Slug"}).status_code == 400
    _create(api, title="Campaigns", slug="campaigns", template="standard")
    clash = api.post(PAGES, {"title": "Campaigns again", "slug": "campaigns"})
    assert clash.status_code == 400 and "slug" in clash.get_json()["error"]["details"]
    check = api.get(f"{PAGES}/slug-check?slug=about").get_json()["data"]
    assert check["available"] and check["overrides_builtin"]


def test_child_pages_paths_and_cycles(seeded, as_role):
    api = as_role("website_manager")
    parent = _create(api, title="Guides", slug="guides", template="standard")
    child = _create(api, title="Journal prompts", slug="journal-prompts", parent_id=parent["id"])
    assert child["path"] == "/guides/journal-prompts"
    res = _save(api, parent, parent_id=child["id"])
    assert res.status_code == 400 and "page.parent_id" in res.get_json()["error"]["details"]
    home_id = api.get(HOMEPAGE).get_json()["data"]["id"]
    bad = api.post(PAGES, {"title": "Under home", "slug": "under-home", "parent_id": home_id})
    assert bad.status_code == 400
    # Renaming the parent moves the child's draft path too.
    _save(api, api.get(f"{PAGES}/{parent['id']}").get_json()["data"], slug="free-guides")
    assert (
        api.get(f"{PAGES}/{child['id']}").get_json()["data"]["path"]
        == "/free-guides/journal-prompts"
    )


def test_cms_page_can_replace_builtin_page(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api, title="About us", slug="about", template="standard")
    assert any("replaces the built-in /about" in w for w in page["warnings"])
    assert client.get("/api/v1/site").get_json()["data"]["cms_overrides"] == []
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    assert client.get("/api/v1/site").get_json()["data"]["cms_overrides"] == ["/about"]


def test_duplicate_and_schedule_pages(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api)
    copy = api.post(f"{PAGES}/{page['id']}/duplicate").get_json()["data"]
    assert copy["slug"] == "spring-reset-copy" and copy["status"] == "draft"
    assert len(copy["sections"]) == len(page["sections"])
    when = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    scheduled = api.post(
        f"{PAGES}/{page['id']}/schedule",
        {"scheduled_at": when, "lock_version": page["lock_version"]},
    )
    assert scheduled.status_code == 200 and scheduled.get_json()["data"]["scheduled_at"]
    with seeded.app_context():
        assert publication_service.publish_due_scheduled()["published"] == []
        result = publication_service.publish_due_scheduled(datetime.now(UTC) + timedelta(hours=3))
        db.session.commit()
        assert result["published"] == ["/spring-reset"]
    assert client.get("/api/v1/pages/resolve?path=/spring-reset").status_code == 200


# ---- shared sections and CTAs -------------------------------------------------------------------


def test_shared_section_propagates_or_detaches(seeded, as_role, client):
    api = as_role("website_manager")
    shared = api.post(
        "/api/v1/admin/shared-sections",
        {
            "name": "Spring CTA",
            "section_type": "call_to_action",
            "variant": "banner",
            "content": {
                "heading": "Join the reset",
                "primary_cta": {"label": "Read", "url": "/articles"},
            },
        },
    ).get_json()["data"]
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home) + [
        {"reusable_section_id": shared["id"], "name": "Shared CTA"}
    ]
    home = _save(api, home, sections).get_json()["data"]
    api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": home["lock_version"]})
    assert _public_home(client)["sections"][-1]["data"]["heading"] == "Join the reset"
    usage = api.get(f"/api/v1/admin/shared-sections/{shared['id']}").get_json()["data"]["usage"]
    assert usage == [
        {"type": "page", "id": home["id"], "title": "Homepage", "path": "/", "live": True}
    ]

    updated = api.put(
        f"/api/v1/admin/shared-sections/{shared['id']}",
        {"lock_version": shared["lock_version"], "content": {"heading": "Join us this spring"}},
    ).get_json()["data"]
    # The change joins the pending (debounced) rebuild instead of queueing a second one.
    assert updated["propagated"] and "shared_section_updated" in _pending_reasons(seeded)
    assert _public_home(client)["sections"][-1]["data"]["heading"] == "Join us this spring"

    kept = api.put(
        f"/api/v1/admin/shared-sections/{shared['id']}",
        {
            "lock_version": updated["lock_version"],
            "content": {"heading": "Only for new pages"},
            "propagate": False,
        },
    ).get_json()["data"]
    assert kept["detached"] >= 1 and kept["usage"] == []
    assert _public_home(client)["sections"][-1]["data"]["heading"] == "Join us this spring"
    assert api.delete(f"/api/v1/admin/shared-sections/{shared['id']}").status_code == 200


def test_shared_groups_reject_cycles(seeded, as_role):
    api = as_role("website_manager")

    def make(name, section_type="quote", content=None):
        res = api.post(
            "/api/v1/admin/shared-sections",
            {
                "name": name,
                "section_type": section_type,
                "content": content or {"quote": "Be kind."},
            },
        )
        assert res.status_code == 201, res.get_json()
        return res.get_json()["data"]

    quote = make("Quote")
    group_a = make("Group A", "section_group", {"items": [quote["id"]]})
    group_b = make("Group B", "section_group", {"items": [group_a["id"]]})
    loop = api.put(
        f"/api/v1/admin/shared-sections/{group_a['id']}",
        {
            "lock_version": group_a["lock_version"],
            "content": {"items": [quote["id"], group_b["id"]]},
        },
    )
    assert (
        loop.status_code == 400
        and "loop" in loop.get_json()["error"]["details"]["content.items"][0]
    )
    itself = api.put(
        f"/api/v1/admin/shared-sections/{group_a['id']}",
        {"lock_version": group_a["lock_version"], "content": {"items": [group_a["id"]]}},
    )
    assert itself.status_code == 400
    in_use = api.delete(f"/api/v1/admin/shared-sections/{quote['id']}")
    assert in_use.status_code == 409


def test_global_cta_used_by_sections(seeded, as_role, client):
    api = as_role("website_manager")
    cta = api.post(
        "/api/v1/admin/ctas",
        {"name": "Subscribe", "label": "Join The Positive Reset", "url": "/newsletter"},
    ).get_json()["data"]
    assert (
        api.post("/api/v1/admin/ctas", {"name": "Bad", "label": "x", "url": "ftp://x"}).status_code
        == 400
    )
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    sections[0]["content"]["primary_cta"] = {"cta_id": cta["id"]}
    home = _save(api, home, sections).get_json()["data"]
    api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": home["lock_version"]})
    assert (
        _public_home(client)["sections"][0]["data"]["primary_cta"]["label"]
        == "Join The Positive Reset"
    )
    api.patch(f"/api/v1/admin/ctas/{cta['id']}", {"label": "Subscribe today"})
    assert _public_home(client)["sections"][0]["data"]["primary_cta"]["label"] == "Subscribe today"
    assert api.delete(f"/api/v1/admin/ctas/{cta['id']}").status_code == 409


# ---- media, branding, navigation, announcements ------------------------------------------------------


def test_page_images_are_optimised_and_tracked(seeded, as_role, client):
    api = as_role("website_manager", "super_admin", email="media-builder@example.org")
    media_id = _upload(api)
    page = _create(api, title="Image page", slug="image-page", template="standard")
    sections = _sections_payload(page) + [
        {
            "section_type": "image_text",
            "content": {"heading": "With an image", "media": media_id},
            "design": {"aspect_ratio": "wide"},
        }
    ]
    page = _save(api, page, sections, social_image_id=media_id).get_json()["data"]
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    live = client.get("/api/v1/pages/resolve?path=/image-page").get_json()["data"]
    image = live["sections"][-1]["data"]["media"]
    assert (
        image["srcset"] and "image/webp" in image["sources"] and image["width"] and image["height"]
    )
    assert live["seo"]["og_image"]["width"] == 1200
    detail = api.get(f"/api/v1/admin/media/{media_id}").get_json()["data"]
    assert any(u["type"] == "page" and u["public"] for u in detail["usage"])
    assert api.delete(f"/api/v1/admin/media/{media_id}").status_code == 409
    sitemap = client.get("/api/v1/sitemap").get_json()["data"]
    entry = next(e for e in sitemap if e["path"] == "/image-page")
    assert entry["images"]


def test_branding_settings_and_favicons(seeded, as_role, client):
    api = as_role("website_manager", "super_admin", email="brand@example.org")
    icon = _upload(api, make_png(600, 600, alpha=True), "icon.png")
    res = api.patch(
        "/api/v1/admin/settings",
        {"values": {"branding.favicon_media_id": icon, "branding.palette": "evergreen"}},
    )
    assert res.status_code == 200, res.get_json()
    branding = client.get("/api/v1/site").get_json()["data"]["branding"]
    assert branding["palette"] == "evergreen"
    assert branding["favicon"]["ico"].endswith("/favicon.ico")
    assert client.get(branding["favicon"]["png512"]).status_code == 200
    bad = api.patch("/api/v1/admin/settings", {"values": {"branding.palette": "neon"}})
    assert bad.status_code == 400
    groups = api.get("/api/v1/admin/settings?groups=Branding").get_json()["data"]["groups"]
    assert [g["name"] for g in groups] == ["Branding"]


def test_navigation_groups_visibility_and_warnings(seeded, as_role, client):
    api = as_role("website_manager")
    res = api.put(
        "/api/v1/admin/navigation/primary",
        {
            "items": [
                {"label": "Home", "url": "/"},
                {
                    "label": "Explore",
                    "link_type": "heading",
                    "children": [
                        {"label": "Articles", "url": "/articles"},
                        {"label": "Missing", "url": "/not-a-page"},
                    ],
                },
                {"label": "About", "url": "/about", "visibility": "desktop"},
            ]
        },
    )
    assert res.status_code == 200, res.get_json()
    menu = res.get_json()["data"]
    assert menu["warnings"] == ["/not-a-page does not point to a published page yet."]
    nav = client.get("/api/v1/site").get_json()["data"]["navigation"]
    assert nav["primary"][1]["children"][0]["label"] == "Articles"
    assert nav["primary"][2]["visibility"] == "desktop"
    assert nav["mobile"] is None
    legal = api.put(
        "/api/v1/admin/navigation/legal",
        {"items": [{"label": "Privacy", "url": "/privacy-policy"}]},
    )
    assert legal.status_code == 200
    assert (
        client.get("/api/v1/site").get_json()["data"]["navigation"]["legal"][0]["label"]
        == "Privacy"
    )
    grouped_legal = api.put(
        "/api/v1/admin/navigation/legal",
        {"items": [{"label": "Group", "link_type": "heading", "children": []}]},
    )
    assert grouped_legal.status_code == 400


def test_footer_and_header_settings_are_public(seeded, as_role, client):
    api = as_role("website_manager")
    res = api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "footer.copyright": "© {year} Think Positive Always.",
                "footer.promo_text": "A new journal is coming soon.",
                "header.cta_label": "Subscribe",
            }
        },
    )
    assert res.status_code == 200, res.get_json()
    site = client.get("/api/v1/site").get_json()["data"]
    assert site["footer"]["promo"]["text"] == "A new journal is coming soon."
    assert site["header"]["cta"] == {"label": "Subscribe", "href": "/newsletter"}


def test_announcements_scheduling_and_targeting(seeded, as_role, client):
    api = as_role("marketing_manager")
    now = datetime.now(UTC)
    res = api.post(
        "/api/v1/admin/announcements",
        {
            "name": "Journal launch",
            "message": "A new guided journal is coming soon.",
            "cta_label": "Join the newsletter",
            "cta_url": "/newsletter",
            "is_enabled": True,
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=8)).isoformat(),
            "target": "paths",
            "target_paths": ["/", "/articles"],
        },
    )
    assert res.status_code == 201, res.get_json()
    created = res.get_json()["data"]
    assert created["state"] == "scheduled"
    public = client.get("/api/v1/site").get_json()["data"]["announcements"]
    assert public[0]["message"].startswith("A new guided journal") and public[0]["paths"] == [
        "/",
        "/articles",
    ]
    assert (
        api.post(
            "/api/v1/admin/announcements",
            {
                "name": "Bad",
                "message": "<b>hi</b>",
                "ends_at": now.isoformat(),
                "starts_at": (now + timedelta(1)).isoformat(),
            },
        ).status_code
        == 400
    )
    api.patch(
        f"/api/v1/admin/announcements/{created['id']}",
        {
            "ends_at": (now - timedelta(minutes=1)).isoformat(),
            "starts_at": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert client.get("/api/v1/site").get_json()["data"]["announcements"] == []


def test_scheduler_rebuilds_when_visibility_window_passes(seeded, as_role):
    api = as_role("website_manager")
    home = api.get(HOMEPAGE).get_json()["data"]
    start = datetime.now(UTC) + timedelta(hours=1)
    sections = _sections_payload(home)
    sections[1]["visibility"] = {"devices": "all", "starts_at": start.isoformat()}
    home = _save(api, home, sections).get_json()["data"]
    api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": home["lock_version"]})
    with seeded.app_context():
        assert page_render.public_page("/")["sections"][1]["type"] != "brand_intro"
        assert publication_service.publish_due_scheduled()["boundary_rebuild"] is False
        db.session.commit()
        later = publication_service.publish_due_scheduled(start + timedelta(minutes=1))
        assert later["boundary_rebuild"] is True


# ---- SEO --------------------------------------------------------------------------------------------


def test_page_seo_checks_and_dashboard(seeded, as_role):
    api = as_role("website_manager")
    page = _create(api, title="Quiet page", slug="quiet-page", template="landing")
    checks = api.get(f"{PAGES}/{page['id']}/seo-checks").get_json()["data"]["checks"]
    assert "missing_meta_description" in {c["code"] for c in checks}
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    overview = as_role("seo_manager").get("/api/v1/admin/seo/overview").get_json()["data"]
    assert any(p["path"] == "/quiet-page" for p in overview["pages_with_issues"])
    assert overview["sitemap"]["pages"] >= 1


def test_sitemap_settings_exclude_paths_and_topics(seeded, as_role, client):
    api = as_role("super_admin")
    api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "seo.sitemap_exclude": "/free-resources\n/terms",
                "seo.sitemap_include_topics": False,
            }
        },
    )
    paths = [e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]]
    assert "/free-resources" not in paths and "/terms" not in paths
    assert not any(p.startswith("/topics/") for p in paths)
    assert "/" in paths and any(p.startswith("/articles/") for p in paths)


# ---- permissions -------------------------------------------------------------------------------------


def test_permissions_are_enforced_per_page(seeded, as_role):
    editor = as_role("editor")
    home = editor.get(HOMEPAGE).get_json()["data"]
    assert home["capabilities"]["edit"] and not home["capabilities"]["publish"]
    assert _save(editor, home, title="Homepage").status_code == 200
    home = editor.get(HOMEPAGE).get_json()["data"]
    assert (
        editor.post(
            f"{PAGES}/{home['id']}/publish", {"lock_version": home["lock_version"]}
        ).status_code
        == 403
    )
    assert editor.post(PAGES, {"title": "Nope"}).status_code == 403
    assert (
        editor.post(
            "/api/v1/admin/shared-sections", {"name": "x", "section_type": "quote"}
        ).status_code
        == 403
    )
    assert editor.get("/api/v1/admin/announcements").status_code == 403
    assert (
        editor.patch(
            "/api/v1/admin/settings", {"values": {"branding.palette": "classic"}}
        ).status_code
        == 403
    )

    moderator = as_role("moderator")
    assert moderator.get(HOMEPAGE).status_code == 200
    assert _save(moderator, home, title="x").status_code == 403

    analyst = as_role("analyst")
    assert analyst.get(HOMEPAGE).status_code == 403
    assert analyst.get(PAGES).status_code == 403

    marketing = as_role("marketing_manager")
    assert marketing.get("/api/v1/admin/announcements").status_code == 200
    assert marketing.get(PAGES).status_code == 403


def test_technical_settings_are_super_admin_only(seeded, as_role):
    manager = as_role("website_manager")
    groups = {g["name"] for g in manager.get("/api/v1/admin/settings").get_json()["data"]["groups"]}
    assert "Technical" not in groups and {"Branding", "Footer", "Header"} <= groups
    denied = manager.patch("/api/v1/admin/settings", {"values": {"seo.allow_indexing": False}})
    assert denied.status_code == 403
    owner = as_role("super_admin")
    ok = owner.patch(
        "/api/v1/admin/settings",
        {"values": {"seo.allow_indexing": False, "seo.canonical_site_url": "https://example.com/"}},
    )
    assert ok.status_code == 200
    seo = seeded.test_client().get("/api/v1/site").get_json()["data"]["seo"]
    assert seo["allow_indexing"] is False and seo["canonical_site_url"] == "https://example.com"
    bad = owner.patch(
        "/api/v1/admin/settings", {"values": {"seo.canonical_site_url": "https://x.com/page"}}
    )
    assert bad.status_code == 400


def test_role_grants_do_not_widen_editorial_roles(app):
    from app.auth.permissions import ROLE_SPECS

    website = {
        p for p in ROLE_SPECS["editor"].permissions if p.split(".")[0] in ("homepage", "pages")
    }
    assert website == {"homepage.view", "homepage.edit", "pages.view", "pages.edit"}
    assert not {p for p in ROLE_SPECS["analyst"].permissions if p.startswith(("homepage", "pages"))}
    assert "homepage.edit" not in ROLE_SPECS["moderator"].permissions
    assert "settings.technical" not in ROLE_SPECS["administrator"].permissions
    assert {"homepage.publish", "pages.publish", "branding.manage"} <= ROLE_SPECS[
        "website_manager"
    ].permissions


def test_public_api_never_returns_drafts(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api, title="Secret draft", slug="secret-draft")
    assert client.get("/api/v1/pages/resolve?path=/secret-draft").status_code == 404
    assert all(p["path"] != "/secret-draft" for p in client.get("/api/v1/pages").get_json()["data"])
    assert client.get("/api/v1/pages/resolve?path=/../admin").status_code == 400
    with seeded.app_context():
        page_row = db.session.get(Page, page["id"])
        assert page_row.published_snapshot is None


def test_builder_options_for_pickers_respect_permissions(seeded, as_role):
    api = as_role("website_manager")
    data = api.get("/api/v1/admin/builder-options").get_json()["data"]
    assert len(data["articles"]) == 6 and {"id", "title", "slug"} <= set(data["articles"][0])
    assert data["topics"] and data["authors"]
    assert as_role("analyst").get("/api/v1/admin/builder-options").status_code == 403
    links = api.get("/api/v1/admin/link-options?q=about").get_json()["data"]
    assert any(item["url"] == "/about" for item in links)


def test_frontend_section_schema_fixture_is_current(app):
    """frontend/src/test/sectionTypes.json mirrors GET /admin/section-types (regenerate if this fails)."""
    import json
    from pathlib import Path

    from app.cms.sections import section_types_schema

    fixture = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "sectionTypes.json"
    )
    assert json.loads(fixture.read_text(encoding="utf-8")) == json.loads(
        json.dumps(section_types_schema())
    )
