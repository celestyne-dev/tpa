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

    # Unticking "Hide from search engines" alone doesn't index a document still pending
    # review (approval is tested below).
    current = api.get(f"{PAGES}/{published['id']}").get_json()["data"]
    saved = _save(api, current, noindex=False)
    assert saved.status_code == 200, saved.get_json()
    _publish(api, saved.get_json()["data"])
    assert "/cookie-policy" not in _sitemap_paths(client)
    seo = client.get("/api/v1/pages/resolve?path=/cookie-policy").get_json()["data"]["seo"]
    assert seo["noindex"] is True


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
    # New installations ask before counting visits (PRIVACY_STATISTICS_MODE defaults to consent).
    assert privacy["statistics_mode"] == "consent"
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


def _raw_send(client, body, ip="203.0.113.7"):
    """A page view exactly as a browser sends it (no consent flag added)."""
    import json as _json

    from .test_analytics import BROWSER, COLLECT

    return client.post(
        COLLECT,
        data=_json.dumps(body).encode(),
        headers={"User-Agent": BROWSER, "Content-Type": "text/plain"},
        environ_base={"REMOTE_ADDR": ip},
    )


def test_by_default_only_visits_the_visitor_accepted_are_counted(seeded, client, app):
    from .test_analytics import _rows

    assert app.config["PRIVACY_STATISTICS_MODE"] == "consent"
    assert _raw_send(client, {"path": "/articles", "spa": False}).status_code == 204
    _raw_send(client, {"path": "/topics", "spa": False, "consent": "yes"})
    assert _rows(seeded) == []
    _raw_send(client, {"path": "/about", "spa": False, "consent": True})
    assert [r.path for r in _rows(seeded)] == ["/about"]
    # Objection mode (only after legal advice) counts visits without a consent flag.
    app.config["PRIVACY_STATISTICS_MODE"] = "objection"
    try:
        _raw_send(client, {"path": "/contact", "spa": False}, ip="203.0.113.9")
    finally:
        app.config["PRIVACY_STATISTICS_MODE"] = "consent"
    assert [r.path for r in _rows(seeded)] == ["/about", "/contact"]


def test_new_installations_default_to_consent(monkeypatch):
    """The default and the documented templates both ask first."""
    from app.config import BaseConfig

    assert BaseConfig.PRIVACY_STATISTICS_MODE in ("consent", "objection")
    source = (ROOT / "backend/app/config/__init__.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PRIVACY_STATISTICS_MODE", "consent")' in source
    for template in (
        "backend/.env.example",
        "deploy/env/production.env.example",
        "deploy/env/staging.env.example",
    ):
        text = (ROOT / template).read_text(encoding="utf-8")
        assert "\nPRIVACY_STATISTICS_MODE=consent\n" in text, template


def test_deploy_check_reports_the_statistics_mode(app, monkeypatch):
    from app.services.deploy_check import _privacy

    monkeypatch.delenv("PRIVACY_STATISTICS_MODE", raising=False)
    [unset] = _privacy({"PRIVACY_STATISTICS_MODE": "consent"})
    assert unset["level"] == "warning" and "not set" in unset["message"]
    monkeypatch.setenv("PRIVACY_STATISTICS_MODE", "objection")
    [explicit] = _privacy({"PRIVACY_STATISTICS_MODE": "objection"})
    assert explicit["level"] == "ok" and explicit["message"].startswith("objection")


def test_sign_in_works_whatever_the_cookie_choice(seeded, client):
    """Necessary cookies don't depend on Cookie settings: consent mode changes nothing."""
    from .test_commerce_checkout import register_customer

    shopper = register_customer(seeded, verify=False, test_account=False)
    assert shopper.get("/api/v1/account/me").status_code == 200
    cookie = shopper.c.get_cookie("tpa_customer", path="/api/v1/")
    assert cookie is not None and cookie.http_only


# ---- review status of legal documents ----------------------------------------------------


def _legal_content(page):
    return _sections_payload(page)


def test_every_legal_template_starts_pending_review():
    for key, template in PAGE_TEMPLATES.items():
        for section in template["sections"]:
            if section["section_type"] == "legal_document":
                assert section["content"]["review_status"] == "pending_review", key
    for key, doc in LEGAL_DOCUMENTS.items():
        assert doc["review_status"] == "pending_review", key


def test_a_pending_document_is_never_indexed_even_if_seo_says_so(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api, title="Editorial Policy", template="editorial_policy", slug="")
    # Untick "Hide from search engines" without approving: still noindex, not listed.
    saved = _save(api, page, noindex=False).get_json()["data"]
    _publish(api, saved)
    public = client.get("/api/v1/pages/resolve?path=/editorial-policy").get_json()["data"]
    assert public["seo"]["noindex"] is True
    data = public["sections"][0]["data"]
    assert data["review_status"] == "pending_review" and data["effective_date"] == ""
    assert "/editorial-policy" not in _sitemap_paths(client)
    # Not claimed as the site's editorial policy in structured data / trust links either.
    assert _site(client).get("trust", {}).get("editorial_policy") is None


def test_approval_needs_an_effective_date_and_no_draft_wording(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api, title="Disclaimer", template="disclaimer", slug="")
    sections = _sections_payload(page)
    sections[0]["content"] = {**sections[0]["content"], "review_status": "approved"}
    refused = _save(api, page, sections)
    assert refused.status_code == 400
    details = refused.get_json()["error"]["details"]
    assert "sections.0.content.effective_date" in details
    assert "sections.0.content.notice" in details
    assert "sections.0.content.body" in details  # "Decision pending" notes remain

    body = [
        b
        for b in sections[0]["content"]["body"]
        if not (b["type"] == "callout" and b.get("title") == "Decision pending")
    ]
    sections[0]["content"] = {
        **sections[0]["content"],
        "review_status": "approved",
        "effective_date": "2027-01-01",
        "notice_title": "",
        "notice": "",
        "body": body,
    }
    ok = _save(api, page, sections, noindex=False)
    assert ok.status_code == 200, ok.get_json()
    _publish(api, ok.get_json()["data"])
    public = client.get("/api/v1/pages/resolve?path=/disclaimer").get_json()["data"]
    assert public["seo"]["noindex"] is False
    assert public["sections"][0]["data"]["effective_date"] == "2027-01-01"
    assert "/disclaimer" in _sitemap_paths(client)


def test_legal_pages_published_before_review_status_keep_their_settings(seeded, as_role, client):
    """An existing published legal page (saved before this field existed) is not changed."""
    from app.models import Page

    api = as_role("website_manager")
    page = _create(api, title="Terms", template="legal", slug="old-terms")
    published = _publish(api, page)
    with seeded.app_context():
        row = db.session.get(Page, published["id"])
        snapshot = json.loads(json.dumps(row.published_snapshot))
        for section in snapshot["sections"]:
            section["content"].pop("review_status", None)
        row.published_snapshot = snapshot
        db.session.commit()
    public = client.get("/api/v1/pages/resolve?path=/old-terms").get_json()["data"]
    assert public["seo"]["noindex"] is False
    assert "/old-terms" in _sitemap_paths(client)


def test_built_in_legal_drafts_are_not_in_the_sitemap(seeded, client):
    paths = _sitemap_paths(client)
    for path in ["/privacy-policy", "/terms", "/affiliate-disclosure", *POLICY_PATHS]:
        assert path not in paths, path
    assert "/about" in paths and "/contact" in paths


# ---- revised Privacy Policy ------------------------------------------------------------


def test_revised_privacy_policy_covers_what_the_site_does():
    doc = LEGAL_DOCUMENTS["privacy_revised"]
    text = json.dumps(doc, ensure_ascii=False)
    for topic in (
        "Newsletter",
        "Partnership inquiries",
        "Customer accounts",
        "Paystack",
        "Usage statistics",
        "Cookie Policy",
        "How long we keep information",
        "Your rights",
        "International transfers",
    ):
        assert topic in text, topic
    pending = [b["text"] for b in doc["body"] if b["type"] == "callout"]
    # Entity details, legal bases, retention periods and transfers are left to the owner.
    for missing in ("legal name", "lawful basis", "how long to keep", "countries involved"):
        assert any(missing in p for p in pending), missing
    # The only retention periods stated are the website's own configured defaults.
    assert {int(n) for n in __import__("re").findall(r"(\d+) (?:days|hours)", text)} <= {
        90,
        12,
        30,
    }
    assert doc["review_status"] == "pending_review" and doc["effective_date"] == ""


def test_revised_privacy_policy_keeps_the_current_one_until_published(seeded, as_role, client):
    api = as_role("website_manager")
    templates = {t["key"]: t for t in api.get("/api/v1/admin/page-templates").get_json()["data"]}
    assert templates["privacy_policy_revised"]["slug"] == "privacy-policy"
    page = _create(api, title="Privacy Policy", template="privacy_policy_revised", slug="")
    assert page["path"] == "/privacy-policy" and page["status"] == "draft"
    assert page["noindex"] is True
    [section] = page["sections"]
    headings = [b["text"] for b in section["content"]["body"] if b["type"] == "heading"]
    expected = [
        b["text"] for b in LEGAL_DOCUMENTS["privacy_revised"]["body"] if b["type"] == "heading"
    ]
    assert headings == expected and section["content"]["review_status"] == "pending_review"
    # The current Privacy Policy keeps being served; the draft is private.
    assert "/privacy-policy" not in _site(client)["cms_overrides"]
    assert client.get("/api/v1/pages/resolve?path=/privacy-policy").status_code == 404
    # Only one page per address: a second template can't overwrite it.
    again = api.post(PAGES, {"title": "Privacy", "template": "privacy_policy"})
    assert again.status_code == 400
