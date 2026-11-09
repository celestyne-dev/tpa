"""Company and legal pages in the CMS: legal templates reproduce the live wording exactly,
create drafts at the built-in address, publish through the normal workflow, and leave
existing pages and data alone."""

import json
from pathlib import Path

from app.cms.templates import LEGAL_DOCUMENTS, PAGE_TEMPLATES

from .test_page_builder import PAGES, _create, _save, _sections_payload

FRONTEND_LEGAL = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "data"
    / "legal"
    / "legalDocuments.json"
)


def _resolve(client, path):
    return client.get(f"/api/v1/pages/resolve?path={path}")


def test_legal_wording_matches_the_built_in_pages():
    """The CMS templates and the built-in pages share one text, character for character."""
    assert json.loads(FRONTEND_LEGAL.read_text(encoding="utf-8")) == LEGAL_DOCUMENTS
    for key, template in (
        ("privacy", "privacy_policy"),
        ("terms", "terms_of_use"),
        ("affiliate", "affiliate_disclosure"),
    ):
        content = PAGE_TEMPLATES[template]["sections"][0]["content"]
        doc = LEGAL_DOCUMENTS[key]
        assert content["body"] == doc["body"]
        assert content["notice"] == doc["notice"]["text"]
        assert content["last_updated"] == doc["last_updated"]
        assert PAGE_TEMPLATES[template]["slug"] == doc["path"].lstrip("/")


def test_legal_template_creates_a_draft_that_replaces_the_page_only_when_published(
    seeded, as_role, client
):
    api = as_role("website_manager")
    templates = {t["key"]: t for t in api.get("/api/v1/admin/page-templates").get_json()["data"]}
    assert templates["privacy_policy"]["slug"] == "privacy-policy"

    page = _create(api, title="Privacy Policy", template="privacy_policy", slug="")
    assert page["path"] == "/privacy-policy" and page["status"] == "draft"
    assert page["meta_description"] == LEGAL_DOCUMENTS["privacy"]["meta_description"]
    [section] = page["sections"]
    assert section["section_type"] == "legal_document"
    assert section["content"]["body"] == LEGAL_DOCUMENTS["privacy"]["body"]

    # A draft is private: the built-in page keeps being served.
    assert "/privacy-policy" not in client.get("/api/v1/site").get_json()["data"]["cms_overrides"]
    assert _resolve(client, "/privacy-policy").status_code == 404

    published = api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": page["lock_version"]})
    assert published.status_code == 200, published.get_json()
    assert "/privacy-policy" in client.get("/api/v1/site").get_json()["data"]["cms_overrides"]
    public = _resolve(client, "/privacy-policy").get_json()["data"]
    [doc] = public["sections"]
    assert doc["type"] == "legal_document"
    assert doc["data"]["last_updated"] == "2026-10-20"
    assert doc["data"]["notice_title"] == "Draft — pending legal review"
    headings = [b["text"] for b in doc["data"]["body"] if b["type"] == "heading"]
    assert headings[0] == "1. Who we are" and headings[-1] == "10. Contact"
    assert public["seo"]["description"] == LEGAL_DOCUMENTS["privacy"]["meta_description"]


def test_legal_document_editing_ordering_visibility_and_dates(seeded, as_role, client):
    api = as_role("website_manager")
    page = _create(api, title="Cookie notes", template="legal", slug="cookie-notes")
    sections = _sections_payload(page)
    doc = sections[0]
    doc["content"] = {
        **doc["content"],
        "effective_date": "2026-12-01",
        "body": [
            {"type": "heading", "level": 2, "text": "1. Scope"},
            {"type": "paragraph", "text": "This applies to **everyone**, see [Terms](/terms)."},
            {"type": "list", "ordered": True, "items": ["First", "Second"]},
            {
                "type": "table",
                "header_row": True,
                "rows": [["Name", "Purpose"], ["session", "Keeps you signed in"]],
            },
        ],
    }
    note = {
        "name": "Note",
        "section_type": "rich_text",
        "variant": "narrow",
        "content": {"body": [{"type": "paragraph", "text": "A closing note."}]},
        "design": {},
        "visibility": {},
        "is_visible": False,
    }
    saved = _save(api, page, [note, doc])
    assert saved.status_code == 200, saved.get_json()
    detail = saved.get_json()["data"]
    assert [s["section_type"] for s in detail["sections"]] == ["rich_text", "legal_document"]
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": detail["lock_version"]})
    public = _resolve(client, "/cookie-notes").get_json()["data"]
    # The hidden section is left out; the document keeps its blocks and dates.
    assert [s["type"] for s in public["sections"]] == ["legal_document"]
    data = public["sections"][0]["data"]
    assert data["effective_date"] == "2026-12-01"
    assert [b["type"] for b in data["body"]] == ["heading", "paragraph", "list", "table"]

    current = api.get(f"{PAGES}/{page['id']}").get_json()["data"]
    bad = _sections_payload(current)
    bad[1]["content"] = {**bad[1]["content"], "last_updated": "20 Oct 2026"}
    res = _save(api, current, bad)
    assert res.status_code == 400
    assert "sections.1.content.last_updated" in res.get_json()["error"]["details"]


def test_about_and_contact_templates_keep_existing_pages(seeded, as_role, client):
    api = as_role("website_manager")
    before = {p["id"]: p["updated_at"] for p in api.get(PAGES).get_json()["data"]}
    about = _create(api, title="About", template="about", slug="")
    contact = _create(api, title="Contact", template="contact", slug="")
    assert about["path"] == "/about" and contact["path"] == "/contact"
    assert [s["section_type"] for s in about["sections"]] == [
        "page_header",
        "image_text",
        "inspirational_message",
        "feature_list",
        "feature_list",
        "audience_metrics",
        "call_to_action",
    ]
    assert [s["section_type"] for s in contact["sections"]] == [
        "page_header",
        "contact_cards",
        "notice_panel",
    ]
    # Nothing else changed, and nothing is public until published.
    after = {p["id"]: p["updated_at"] for p in api.get(PAGES).get_json()["data"]}
    assert {k: after[k] for k in before} == before
    assert client.get("/api/v1/site").get_json()["data"]["cms_overrides"] == []
    # A second page at the same address is refused (the first draft keeps it).
    again = api.post(PAGES, {"title": "About again", "template": "about"})
    assert again.status_code == 400 and "slug" in again.get_json()["error"]["details"]
