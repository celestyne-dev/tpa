"""Pinterest website verification (Admin › Settings › Technical) and the /advertise
Media Kit buttons."""

from __future__ import annotations

import pytest

from app.cms.settings_registry import clean_verification_token

TOKEN = "b06712ca94d844702b0fee51d1b82b90"


def _site(client):
    return client.get("/api/v1/site").get_json()["data"]


def test_the_pinterest_code_is_public_by_default(seeded, client):
    assert _site(client)["seo"]["pinterest_verification"] == TOKEN


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (TOKEN, TOKEN),
        (f'<meta name="p:domain_verify" content="{TOKEN}"/>', TOKEN),
        (f"<meta name='p:domain_verify' content='{TOKEN}' >", TOKEN),
        ("", ""),
    ],
)
def test_codes_and_pasted_tags_are_accepted(value, expected):
    assert clean_verification_token(value) == (expected, None)


@pytest.mark.parametrize(
    "value",
    [
        '<meta name="p:domain_verify" content="abc"/><script>alert(1)</script>',
        '<script>alert("x")</script>',
        '<meta name="google-site-verification" content="abcdefghij"/>',
        'abcdefgh" onload="x',
        "short",
        "has spaces in it",
        f'<meta name="p:domain_verify" content="{TOKEN}"><meta name="p:domain_verify" content="x">',
    ],
)
def test_html_scripts_and_bad_codes_are_refused(value):
    cleaned, problem = clean_verification_token(value)
    assert cleaned is None and problem


def test_setting_saves_only_the_code(seeded, as_role, client):
    api = as_role("super_admin")
    res = api.patch(
        "/api/v1/admin/settings",
        {
            "values": {
                "seo.pinterest_verification": '<meta name="p:domain_verify" content="abcd1234EF"/>'
            }
        },
    )
    assert res.status_code == 200, res.get_json()
    assert _site(client)["seo"]["pinterest_verification"] == "abcd1234EF"
    bad = api.patch(
        "/api/v1/admin/settings",
        {"values": {"seo.pinterest_verification": "<script>alert(1)</script>"}},
    )
    assert bad.status_code == 400
    assert "seo.pinterest_verification" in bad.get_json()["error"]["details"]
    assert _site(client)["seo"]["pinterest_verification"] == "abcd1234EF"
    cleared = api.patch("/api/v1/admin/settings", {"values": {"seo.pinterest_verification": ""}})
    assert cleared.status_code == 200
    assert _site(client)["seo"]["pinterest_verification"] is None


def test_ordinary_editors_cannot_change_it(seeded, as_role):
    api = as_role("editor")
    res = api.patch(
        "/api/v1/admin/settings", {"values": {"seo.pinterest_verification": "abcd1234EF"}}
    )
    assert res.status_code == 403


# ---- Media Kit buttons -------------------------------------------------------------------------


def test_media_kit_button_labels_are_editable_and_public(seeded, as_role, client):
    api = as_role("super_admin")
    draft = api.get("/api/v1/admin/media-kit").get_json()["data"]["draft"]
    assert draft["view_cta_label"] == "View Our Media Kit"
    assert draft["partnership_cta_label"] == "Discuss a Partnership"
    assert client.get("/api/v1/media-kit").status_code == 404  # not published: no button
    res = api.put(
        "/api/v1/admin/media-kit",
        {**draft, "view_cta_label": "See our media kit", "partnership_cta_label": ""},
    )
    assert res.status_code == 200, res.get_json()
    assert api.post("/api/v1/admin/media-kit/publish").status_code == 200
    public = client.get("/api/v1/media-kit").get_json()["data"]
    assert public["view_cta_label"] == "See our media kit"
    assert public["partnership_cta_label"] == "Discuss a Partnership"  # empty: the default
    bad = api.put("/api/v1/admin/media-kit", {**draft, "view_cta_label": "<b>x</b>"})
    assert bad.status_code == 400
