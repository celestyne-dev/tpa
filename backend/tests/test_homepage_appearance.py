"""Homepage section appearance (background, spacing, card style, alignment, visibility)
survives every step: save draft, reload, preview, publish, the public page and revisions."""

from sqlalchemy import select

from app.extensions import db
from app.models import PageRevision

from .test_page_builder import HOMEPAGE, PAGES, _public_home, _save, _sections_payload


def _by_key(sections, key):
    return next(s for s in sections if s["key"] == key)


def _change_appearance(api):
    home = api.get(HOMEPAGE).get_json()["data"]
    sections = _sections_payload(home)
    keys = [s["key"] for s in home["sections"]]
    featured = sections[keys.index("featured")]
    newsletter = sections[keys.index("newsletter")]
    quote = sections[keys.index("intro")]
    featured["design"] = {
        **featured["design"],
        "background": "sage_dark",
        "spacing": "lg",
        "card_style": "outline",
        "align": "center",
    }
    newsletter["design"] = {**newsletter["design"], "background": "charcoal"}
    quote["design"] = {**quote["design"], "align": "left", "background": "beige"}
    quote["visibility"] = {**quote["visibility"], "devices": "desktop"}
    saved = _save(api, home, sections)
    assert saved.status_code == 200, saved.get_json()
    return home, saved.get_json()["data"]


def test_appearance_survives_save_and_reload(seeded, as_role, client):
    api = as_role("website_manager")
    before, saved = _change_appearance(api)
    # A fresh load of the editor (what a browser refresh does) returns the chosen values.
    reloaded = api.get(HOMEPAGE).get_json()["data"]
    for detail in (saved, reloaded):
        featured = _by_key(detail["sections"], "featured")
        assert featured["design"] == {
            "background": "sage_dark",
            "spacing": "lg",
            "card_style": "outline",
            "align": "center",
        }
        assert _by_key(detail["sections"], "newsletter")["design"]["background"] == "charcoal"
        quote = _by_key(detail["sections"], "intro")
        assert quote["design"]["align"] == "left" and quote["design"]["background"] == "beige"
        assert quote["visibility"]["devices"] == "desktop"
    # Order, content and the other sections' appearance are untouched.
    assert [s["key"] for s in reloaded["sections"]] == [s["key"] for s in before["sections"]]
    for old, new in zip(before["sections"], reloaded["sections"], strict=True):
        assert new["content"] == old["content"] and new["variant"] == old["variant"]
        if old["key"] not in ("featured", "newsletter", "intro"):
            assert new["design"] == old["design"]
    # A draft is private: the live homepage keeps its published appearance.
    live = _by_key(_public_home(client)["sections"], "featured")
    assert live["design"]["background"] == "ivory"


def test_preview_and_publish_honour_stored_appearance(seeded, as_role, client):
    api = as_role("website_manager")
    home, saved = _change_appearance(api)
    revisions_before = api.get(f"{PAGES}/{home['id']}/revisions").get_json()["data"]

    # The saved-draft preview (no unsaved edits posted) renders the stored values.
    preview = api.post(f"{PAGES}/{home['id']}/preview").get_json()["data"]["page"]["sections"]
    assert _by_key(preview, "featured")["design"]["background"] == "sage_dark"
    assert _by_key(preview, "featured")["design"]["card_style"] == "outline"
    assert _by_key(preview, "newsletter")["design"]["background"] == "charcoal"
    assert _by_key(preview, "intro")["devices"] == "desktop"

    published = api.post(f"{PAGES}/{home['id']}/publish", {"lock_version": saved["lock_version"]})
    assert published.status_code == 200, published.get_json()
    assert not published.get_json()["data"]["has_unpublished_changes"]

    # The published representation (what the static rebuild and the website read).
    public = _public_home(client)["sections"]
    featured = _by_key(public, "featured")
    assert featured["design"] == {
        "background": "sage_dark",
        "spacing": "lg",
        "card_style": "outline",
        "align": "center",
    }
    assert _by_key(public, "newsletter")["design"]["background"] == "charcoal"
    quote = _by_key(public, "intro")
    assert quote["design"]["align"] == "left" and quote["devices"] == "desktop"
    # The same sections, except the digital-products section, which previews show while
    # the shop is switched off but the website leaves out.
    assert [s["key"] for s in public] == [s["key"] for s in preview if s["key"] != "products"]

    # Publishing adds a revision; the earlier ones are kept unchanged.
    revisions = api.get(f"{PAGES}/{home['id']}/revisions").get_json()["data"]
    assert len(revisions) == len(revisions_before) + 1
    assert [r["id"] for r in revisions[1:]] == [r["id"] for r in revisions_before]
    with seeded.app_context():
        latest = db.session.get(PageRevision, revisions[0]["id"])
        snap = {s["key"]: s for s in latest.snapshot["sections"]}
        assert snap["featured"]["design"]["background"] == "sage_dark"
        first = db.session.scalar(
            select(PageRevision).where(PageRevision.id == revisions_before[-1]["id"])
        )
        old = {s["key"]: s for s in first.snapshot["sections"]}
        assert old["featured"]["design"]["background"] == "ivory"


def test_unchanged_save_keeps_existing_appearance(seeded, as_role):
    """Saving other edits never resets appearance values to the section defaults."""
    api = as_role("website_manager")
    _, saved = _change_appearance(api)
    sections = _sections_payload(saved)
    sections[0]["content"]["heading"] = "A new heading"
    again = _save(api, saved, sections).get_json()["data"]
    assert _by_key(again["sections"], "featured")["design"]["background"] == "sage_dark"
    assert _by_key(again["sections"], "newsletter")["design"]["background"] == "charcoal"
    assert again["sections"][0]["content"]["heading"] == "A new heading"
