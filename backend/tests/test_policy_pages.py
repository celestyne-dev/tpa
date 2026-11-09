"""Batch 13 policy pages and cookie settings.

The eight policy documents share one text with the built-in pages, start as private
noindex drafts in the CMS, only reach menus and the sitemap once published (and indexable),
never replace an existing page, and keep the CMS workflow (autosave, revisions, rollback,
scheduling). Cookie settings list only technologies the site uses, their wording is
editable as plain text, and consent mode is enforced by the server too.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.cms.templates import LEGAL_DOCUMENTS, PAGE_TEMPLATES, POLICY_DOCUMENTS
from app.extensions import db
from app.services import publication_service

from .test_page_builder import PAGES, _create, _save, _sections_payload

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
POLICY_PATHS = [path for _t, _k, path in POLICY_DOCUMENTS]
DRAFT = "Draft — pending legal review"


def _site(client):
    return client.get("/api/v1/site").get_json()["data"]


def _sitemap_paths(client):
    return {e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]}


def _footer_urls(client):
    nav = _site(client)["navigation"]
    return [i["url"] for g in nav["footer"] for i in g["items"]] + [i["url"] for i in nav["legal"]]


def _publish(api, page):
    res = api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---- wording and configuration ---------------------------------------------------------


def test_policy_wording_is_shared_and_marked_as_a_draft():
    frontend = json.loads(
        (FRONTEND / "src/data/legal/legalDocuments.json").read_text(encoding="utf-8")
    )
    assert frontend == LEGAL_DOCUMENTS
    for template, key, path in POLICY_DOCUMENTS:
        doc = LEGAL_DOCUMENTS[key]
        tpl = PAGE_TEMPLATES[template]
        content = tpl["sections"][0]["content"]
        assert doc["path"] == path and tpl["slug"] == path.lstrip("/")
        assert content["body"] == doc["body"] and content["summary"] == doc["summary"]
        assert content["notice_title"] == DRAFT == doc["notice"]["title"]
        assert doc["effective_date"] == "" and doc["last_updated"]
        assert tpl["noindex"] is True and tpl["seo_title"] == doc["seo_title"]
        assert 50 <= len(doc["meta_description"]) <= 160, key
        headings = [b for b in doc["body"] if b["type"] == "heading"]
        assert len(headings) >= 6, key
        text = json.dumps(doc["body"])
        assert "](/contact)" in text, key


def test_frontend_routes_list_the_same_policy_pages():
    nav = (FRONTEND / "src/config/navigation.js").read_text(encoding="utf-8")
    routes = dict(re.findall(r'^\s+(\w+): "(/[^"]*)",', nav, re.M))
    block = nav.split("export const policyPages")[1].split("];")[0]
    listed = re.findall(r'key: "(\w+)", label: "[^"]+", path: routes\.(\w+)', block)
    assert [(k, routes[r]) for k, r in listed] == [(k, p) for _t, k, p in POLICY_DOCUMENTS]


def test_the_policies_do_not_make_unsupported_claims():
    """No conformance, approval or registration claims; undecided terms are flagged."""
    every = json.dumps({k: LEGAL_DOCUMENTS[k] for _t, k, _p in POLICY_DOCUMENTS})
    for claim in ("fully conform", "is compliant", "WCAG 2.2 AA compliant", "legally approved"):
        assert claim not in every
    refunds = json.dumps(LEGAL_DOCUMENTS["refunds"])
    assert "Decision pending" in refunds
    assert not re.search(r"\b\d+[- ]day refund\b", refunds)
    access = json.dumps(LEGAL_DOCUMENTS["accessibility"])
    assert "do not claim" in access and "not yet been independently audited" in access


def _storage_keys():
    """Every localStorage / sessionStorage key the public site writes."""
    keys = set()
    for file in (FRONTEND / "src").rglob("*.js*"):
        if ".test." in file.name or "/test/" in str(file) or "/admin/" in str(file):
            continue
        text = file.read_text(encoding="utf-8")
        if "localStorage" not in text and "sessionStorage" not in text:
            continue
        keys |= set(re.findall(r'"(tpa[-:][a-z:-]+)"', text))
        keys |= {f"{p}…" for p in re.findall(r"`(tpa[-:][a-z-]+:)\$\{", text)}
    # Event names share the prefix but are not stored; "prefix:" keys hold one entry per id.
    return {
        f"{k}…" if k.endswith(":") else k
        for k in keys
        if not k.endswith("-changed") and not k.endswith("-open")
    }


def test_cookie_policy_lists_every_cookie_and_storage_key(app):
    from app.auth.customer_session import CSRF_COOKIE, SESSION_COOKIE

    rows = [
        r[0]
        for b in LEGAL_DOCUMENTS["cookies"]["body"]
        if b["type"] == "table"
        for r in b["rows"][1:]
    ]
    listed = {name.strip() for row in rows for name in row.split(",")}
    cookies = {
        SESSION_COOKIE,
        CSRF_COOKIE,
        app.config["JWT_ACCESS_COOKIE_NAME"],
        app.config["JWT_REFRESH_COOKIE_NAME"],
        app.config["JWT_ACCESS_CSRF_COOKIE_NAME"],
        app.config["JWT_REFRESH_CSRF_COOKIE_NAME"],
    }
    storage = _storage_keys()
    assert "tpa:privacy-choices" in storage and "tpa:cart" in storage
    assert cookies | storage <= listed, (cookies | storage) - listed


def test_no_third_party_scripts_are_loaded():
    """Nothing that would need consent runs on page load: one first-party module script,
    and the recommended CSP only allows scripts from the site itself."""
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script[^>]*>", html)
    assert scripts == ['<script type="module" src="/src/entry-client.jsx">']
    csp = (ROOT / "deploy/nginx/tpa-security-headers.conf.example").read_text()
    assert "script-src 'self';" in csp
    for tracker in ("googletagmanager", "google-analytics", "facebook.net", "doubleclick"):
        for file in (FRONTEND / "src").rglob("*.js*"):
            assert tracker not in file.read_text(encoding="utf-8"), (tracker, file)


# ---- CMS templates -----------------------------------------------------------------------


@pytest.mark.parametrize(("template", "key", "path"), POLICY_DOCUMENTS)
def test_each_policy_template_creates_a_private_noindex_draft(
    seeded, as_role, client, template, key, path
):
    api = as_role("website_manager")
    doc = LEGAL_DOCUMENTS[key]
    page = _create(api, title=doc["title"], template=template, slug="")
    assert page["path"] == path and page["status"] == "draft"
    assert page["seo_title"] == doc["seo_title"]
    assert page["meta_description"] == doc["meta_description"]
    assert page["noindex"] is True
    [section] = page["sections"]
    assert section["section_type"] == "legal_document"
    assert section["content"]["notice_title"] == DRAFT
    # Private: the built-in draft keeps being served, nothing is listed or linked.
    assert path not in _site(client)["cms_overrides"]
    assert client.get(f"/api/v1/pages/resolve?path={path}").status_code == 404
    assert path not in _sitemap_paths(client)
    assert path not in _footer_urls(client)


def test_publishing_a_policy_replaces_the_draft_but_indexes_it_only_when_allowed(
    seeded, as_role, client
):
    api = as_role("website_manager")
    page = _create(api, title="Cookie Policy", template="cookie_policy", slug="")
    assert "/cookie-policy" not in _footer_urls(client)
    published = _publish(api, page)
    assert "/cookie-policy" in _site(client)["cms_overrides"]
    public = client.get("/api/v1/pages/resolve?path=/cookie-policy").get_json()["data"]
    assert public["seo"]["noindex"] is True
    assert public["seo"]["title"] == "Cookie Policy"
    [doc] = public["sections"]
    assert doc["type"] == "legal_document" and doc["data"]["notice_title"] == DRAFT
    # Published but still hidden from search engines: linked, not in the sitemap.
    assert "/cookie-policy" in _footer_urls(client)
    assert "/cookie-policy" not in _sitemap_paths(client)

    # After review an editor unticks "Hide from search engines" and publishes again.
    current = api.get(f"{PAGES}/{published['id']}").get_json()["data"]
    saved = _save(api, current, noindex=False)
    assert saved.status_code == 200, saved.get_json()
    _publish(api, saved.get_json()["data"])
    entries = {e["path"]: e for e in client.get("/api/v1/sitemap").get_json()["data"]}
    assert entries["/cookie-policy"]["priority"] == 0.2
    assert client.get("/api/v1/pages/resolve?path=/cookie-policy").get_json()["data"]["seo"][
        "canonical_url"
    ] in (None, "")


def test_policy_pages_keep_the_cms_workflow(seeded, as_role, client):
    """Draft saves (what autosave sends), section order and visibility, preview, revisions,
    rollback and scheduled publishing all work on a policy page."""
    api = as_role("website_manager")
    page = _create(api, title="Editorial Policy", template="editorial_policy", slug="")
    sections = _sections_payload(page)
    doc = sections[0]
    doc["content"] = {
        **doc["content"],
        "effective_date": "2027-01-01",
        "body": [
            {"type": "heading", "level": 2, "text": "1. Our mission"},
            {"type": "paragraph", "text": "Edited in the CMS."},
        ],
    }
    intro = {
        "name": "Intro",
        "section_type": "rich_text",
        "variant": "narrow",
        "content": {"body": [{"type": "paragraph", "text": "Before the policy."}]},
        "design": {},
        "visibility": {},
        "is_visible": False,
    }
    saved = _save(api, page, [intro, doc])
    assert saved.status_code == 200, saved.get_json()
    detail = saved.get_json()["data"]
    assert [s["section_type"] for s in detail["sections"]] == ["rich_text", "legal_document"]
    preview = api.post(f"{PAGES}/{page['id']}/preview").get_json()["data"]["page"]
    assert preview["sections"][-1]["data"]["body"][1]["text"] == "Edited in the CMS."
    # Still private while it is a draft.
    assert client.get("/api/v1/pages/resolve?path=/editorial-policy").status_code == 404

    first = _publish(api, detail)
    public = client.get("/api/v1/pages/resolve?path=/editorial-policy").get_json()["data"]
    assert [s["type"] for s in public["sections"]] == ["legal_document"]  # hidden intro
    assert public["sections"][0]["data"]["effective_date"] == "2027-01-01"

    again = _sections_payload(first)
    again[1]["content"] = {
        **again[1]["content"],
        "body": [{"type": "heading", "level": 2, "text": "1. A second version"}],
    }
    second = _publish(api, _save(api, first, again).get_json()["data"])
    revisions = api.get(f"{PAGES}/{page['id']}/revisions").get_json()["data"]
    assert [r["number"] for r in revisions] == [2, 1]
    restored = api.post(
        f"{PAGES}/{page['id']}/revisions/{revisions[-1]['id']}/restore",
        {"lock_version": second["lock_version"]},
    ).get_json()["data"]
    assert restored["sections"][1]["content"]["body"][1]["text"] == "Edited in the CMS."
    assert restored["has_unpublished_changes"]

    when = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    scheduled = api.post(
        f"{PAGES}/{page['id']}/schedule",
        {"scheduled_at": when, "lock_version": restored["lock_version"]},
    )
    assert scheduled.status_code == 200 and scheduled.get_json()["data"]["scheduled_at"]
    with seeded.app_context():
        result = publication_service.publish_due_scheduled(datetime.now(UTC) + timedelta(hours=3))
        db.session.commit()
    assert result["published"] == ["/editorial-policy"]
    live = client.get("/api/v1/pages/resolve?path=/editorial-policy").get_json()["data"]
    assert live["sections"][0]["data"]["body"][1]["text"] == "Edited in the CMS."


def test_a_policy_template_never_replaces_an_existing_page(seeded, as_role, client):
    api = as_role("website_manager")
    existing = _create(api, title="Our disclaimer", template="legal", slug="disclaimer")
    existing = _publish(api, existing)
    before = client.get("/api/v1/pages/resolve?path=/disclaimer").get_json()["data"]
    again = api.post(PAGES, {"title": "Disclaimer", "template": "disclaimer"})
    assert again.status_code == 400 and "slug" in again.get_json()["error"]["details"]
    after = client.get("/api/v1/pages/resolve?path=/disclaimer").get_json()["data"]
    assert after == before
    assert api.get(f"{PAGES}/{existing['id']}").get_json()["data"]["title"] == "Our disclaimer"


def test_only_page_managers_can_create_policy_pages(seeded, as_role):
    editor = as_role("editor")
    res = editor.post(PAGES, {"title": "Disclaimer", "template": "disclaimer"})
    assert res.status_code == 403


# ---- menus -----------------------------------------------------------------------------


def test_menus_link_policy_pages_only_once_published(seeded, as_role, client):
    api = as_role("website_manager")
    saved = api.put(
        "/api/v1/admin/navigation/footer",
        {
            "items": [
                {
                    "label": "Legal",
                    "link_type": "heading",
                    "children": [
                        {"label": "Privacy Policy", "url": "/privacy-policy"},
                        {"label": "Disclaimer", "url": "/disclaimer"},
                    ],
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.get_json()
    warnings = saved.get_json()["data"]["warnings"]
    assert any("/disclaimer is still a draft policy" in w for w in warnings)
    assert _footer_urls(client) == ["/privacy-policy"]

    page = _create(api, title="Disclaimer", template="disclaimer", slug="")
    _publish(api, page)
    assert _footer_urls(client) == ["/privacy-policy", "/disclaimer"]


def test_default_legal_menu_lists_policies_as_they_are_published(seeded, as_role, client):
    from app.models import NavigationMenu

    with seeded.app_context():
        for menu in db.session.scalars(db.select(NavigationMenu)):
            db.session.delete(menu)
        db.session.commit()
    urls = _footer_urls(client)
    assert {"/privacy-policy", "/terms", "/affiliate-disclosure"} <= set(urls)
    assert not set(POLICY_PATHS) & set(urls)
    api = as_role("website_manager")
    _publish(api, _create(api, title="Accessibility", template="accessibility_statement", slug=""))
    urls = _footer_urls(client)
    assert "/accessibility" in urls
    assert not (set(POLICY_PATHS) - {"/accessibility"}) & set(urls)


def test_links_to_policy_drafts_are_not_reported_as_broken(seeded):
    from app.services.seo_service import broken_links

    with seeded.app_context():
        assert broken_links(POLICY_PATHS) == []


# ---- cookie settings ---------------------------------------------------------------------


def test_cookie_settings_list_only_technologies_in_use(seeded, client, app):
    privacy = _site(client)["privacy"]
    assert privacy["statistics_mode"] == "objection"
    assert privacy["policy_path"] == "/cookie-policy"
    assert [c["key"] for c in privacy["categories"]] == ["necessary", "statistics"]
    assert privacy["categories"][0]["required"] is True
    assert privacy["categories"][1]["required"] is False
    # No advertising or third-party tracking categories: the site uses none.
    assert not {"advertising", "marketing", "third_party"} & {
        c["key"] for c in privacy["categories"]
    }
    app.config["ANALYTICS_TRACKING"] = "disabled"
    try:
        keys = [c["key"] for c in _site(client)["privacy"]["categories"]]
    finally:
        app.config["ANALYTICS_TRACKING"] = "enabled"
    assert keys == ["necessary"]


def test_cookie_settings_wording_is_editable_plain_text(seeded, as_role, client):
    api = as_role("super_admin")
    groups = api.get("/api/v1/admin/settings?groups=Privacy choices").get_json()["data"]["groups"]
    assert [g["name"] for g in groups] == ["Privacy choices"]
    keys = {s["key"] for s in groups[0]["settings"]}
    assert {
        "privacy.notice_text",
        "privacy.statistics_description",
        "privacy.policy_path",
        "privacy.consent_version",
        "privacy.settings_label",
    } <= keys
    bad = api.patch(
        "/api/v1/admin/settings",
        {"values": {"privacy.notice_text": "<script>alert(1)</script>"}},
    )
    assert bad.status_code == 400 and "privacy.notice_text" in bad.get_json()["error"]["details"]
    ok = api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "privacy.settings_label": "Privacy settings",
                "privacy.statistics_label": "Visit counts",
                "privacy.consent_version": "2027-01",
            }
        },
    )
    assert ok.status_code == 200, ok.get_json()
    privacy = _site(client)["privacy"]
    assert privacy["settings_label"] == "Privacy settings"
    assert privacy["categories"][1]["label"] == "Visit counts"
    assert privacy["version"] == "2027-01"


def test_consent_mode_is_application_configuration():
    from app.config import privacy_statistics_mode

    assert privacy_statistics_mode("objection") == "objection"
    assert privacy_statistics_mode(" Objection ") == "objection"
    # Anything unexpected falls back to the stricter mode.
    for value in ("consent", "", None, "off", "opt-out"):
        assert privacy_statistics_mode(value) == "consent"


def test_consent_mode_counts_only_visits_the_visitor_accepted(seeded, client, app):
    from .test_analytics import _rows, _send

    app.config["PRIVACY_STATISTICS_MODE"] = "consent"
    try:
        _send(client, {"path": "/articles", "spa": False})
        assert _rows(seeded) == []
        _send(client, {"path": "/about", "spa": False, "consent": True})
        assert [r.path for r in _rows(seeded)] == ["/about"]
        assert _site(client)["privacy"]["statistics_mode"] == "consent"
    finally:
        app.config["PRIVACY_STATISTICS_MODE"] = "objection"
    # Objection mode (the default) counts as before.
    _send(client, {"path": "/contact", "spa": False}, ip="203.0.113.9")
    assert [r.path for r in _rows(seeded)] == ["/about", "/contact"]
