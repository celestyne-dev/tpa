"""Company page sections: contact cards, verified audience figures, notices, the optional
image in image-and-text sections, and the company page templates."""

from datetime import date

from app.cms.sections import validate_section
from app.cms.templates import PAGE_TEMPLATES
from app.extensions import db
from app.models.partnerships import AudienceMetric
from app.utils.errors import ValidationError

from .test_page_builder import PAGES, _create, _save, _sections_payload


def _metric(app, metric_type, value, *, verified=True, public=True, platform="LinkedIn"):
    with app.app_context():
        db.session.add(
            AudienceMetric(
                metric_type=metric_type,
                value=value,
                platform=platform,
                source=f"{platform} analytics",
                measured_on=date(2026, 10, 1),
                verified=verified,
                is_public=public,
            )
        )
        db.session.commit()


def _resolve(client, path):
    return client.get(f"/api/v1/pages/resolve?path={path}").get_json()["data"]


def test_image_text_image_is_optional():
    clean = validate_section(
        "image_text", "image_right", {"heading": "Our story", "body": "Text only."}
    )
    assert clean["media"] is None


def test_contact_cards_validate_choices_and_links():
    good = validate_section(
        "contact_cards",
        "cards_3",
        {
            "items": [
                {
                    "icon": "pen-line",
                    "title": "Editorial feedback",
                    "text": "Tell us.",
                    "email": "general",
                    "cta_label": "Partner with us",
                    "cta_url": "/partner-with-us#partnership-inquiry",
                }
            ]
        },
    )
    assert good["items"][0]["email"] == "general"
    try:
        validate_section(
            "contact_cards",
            "cards_3",
            {"items": [{"title": "X", "email": "someone@example.com", "cta_url": "javascript:x"}]},
        )
    except ValidationError as exc:
        details = exc.details
    else:  # pragma: no cover
        raise AssertionError("invalid card accepted")
    assert any(k.endswith(".email") for k in details)
    assert any(k.endswith(".cta_url") for k in details)


def test_audience_figures_show_only_verified_public_measurements(seeded, as_role, client):
    _metric(seeded, "social_followers", 1200)
    _metric(seeded, "website_users", 900, platform="Website")
    _metric(seeded, "social_followers", 999999, verified=False)  # never shown
    _metric(seeded, "website_pageviews", 5000, public=False, platform="Website")  # never shown
    api = as_role("website_manager")
    page = _create(api, title="Audience", template="standard", slug="audience")
    sections = [
        {
            "name": "All",
            "section_type": "audience_metrics",
            "variant": "cards",
            "content": {"heading": "All figures", "metric_group": "all"},
            "design": {},
            "visibility": {},
            "is_visible": True,
        },
        {
            "name": "Website",
            "section_type": "audience_metrics",
            "variant": "cards",
            "content": {"heading": "Website", "metric_group": "website"},
            "design": {},
            "visibility": {},
            "is_visible": True,
        },
    ]
    detail = _save(api, page, sections).get_json()["data"]
    api.post(f"{PAGES}/{page['id']}/publish", {"lock_version": detail["lock_version"]})
    everything, website = _resolve(client, "/audience")["sections"]
    assert sorted(m["value"] for m in everything["data"]["metrics"]) == [900.0, 1200.0]
    assert [m["metric_type"] for m in website["data"]["metrics"]] == ["website_users"]
    for m in everything["data"]["metrics"]:
        assert m["measured_on"] == "2026-10-01" and m["source"]


def test_company_templates_create_complete_editable_pages(seeded, as_role, client):
    api = as_role("website_manager")
    expected = {
        "partner_with_us": ("/partner-with-us", "partnership_inquiry"),
        "advertise": ("/advertise", "audience_metrics"),
    }
    for key, (path, must_have) in expected.items():
        page = _create(api, title=PAGE_TEMPLATES[key]["label"], template=key, slug="")
        assert page["path"] == path and page["status"] == "draft"
        assert page["meta_description"] == PAGE_TEMPLATES[key]["meta_description"]
        types = [s["section_type"] for s in page["sections"]]
        assert must_have in types
    partner = api.get(f"{PAGES}?q=Partner").get_json()["data"][0]
    detail = api.get(f"{PAGES}/{partner['id']}").get_json()["data"]
    hero = detail["sections"][0]
    assert hero["content"]["primary_cta"]["url"] == "/partner-with-us#partnership-inquiry"
    # Reorder and hide sections, publish, and the public page follows.
    sections = _sections_payload(detail)
    sections[1], sections[2] = sections[2], sections[1]
    sections[3]["is_visible"] = False
    saved = _save(api, detail, sections).get_json()["data"]
    api.post(f"{PAGES}/{partner['id']}/publish", {"lock_version": saved["lock_version"]})
    public = _resolve(client, "/partner-with-us")
    shown = [s["type"] for s in public["sections"]]
    assert shown[:3] == ["hero", "feature_list", "image_text"]
    assert "partnership_inquiry" in shown
    assert len(shown) == len(sections) - 1
    assert "/partner-with-us" in client.get("/api/v1/site").get_json()["data"]["cms_overrides"]
