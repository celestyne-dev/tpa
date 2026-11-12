"""Header topics, inline bold/italic and numbered-list continuation."""

from __future__ import annotations

import pytest
from sqlalchemy import insert, select

from app.cms.blocks import blocks_word_count, strip_inline_links, validate_blocks
from app.extensions import db
from app.models import Article, Topic
from app.models.content import article_topics
from app.utils.errors import ValidationError

from .test_admin_content import _draft
from .test_navigation_architecture import _drop_saved_menus, _nav

# ---- 1. topics in the header ------------------------------------------------------------------


def _topic(app, slug, name, *, featured, with_article=True):
    with app.app_context():
        topic = Topic(slug=slug, name=name, status="active", featured=featured)
        db.session.add(topic)
        db.session.flush()
        if with_article:
            article_id = db.session.scalar(
                select(Article.id).where(Article.status == "published").limit(1)
            )
            db.session.execute(
                insert(article_topics).values(article_id=article_id, topic_id=topic.id)
            )
        db.session.commit()


def _header_topics(client):
    return {
        child["url"]: group["label"]
        for group in _nav(client)["primary"]
        for child in group.get("children") or []
        if child["url"].startswith("/topics/")
    }


def test_featured_topics_reach_the_default_header_once(seeded, app, client):
    _drop_saved_menus(app)
    before = _header_topics(client)
    _topic(app, "faith-and-hope", "Faith and Hope", featured=True)  # matches no group keyword
    _topic(app, "gratitude-practice", "Gratitude Practice", featured=True)  # "gratitude"
    _topic(app, "quiet-hobbies", "Quiet Hobbies", featured=False)
    _topic(app, "new-empty", "New Empty", featured=True, with_article=False)
    after = _header_topics(client)
    assert "/topics/faith-and-hope" in after
    assert after["/topics/gratitude-practice"] == "Mindset"
    assert "/topics/quiet-hobbies" not in after  # not configured for the header
    assert "/topics/new-empty" not in after  # nothing to read yet
    # Existing links are kept, nothing is listed twice and "All articles" stays last.
    assert set(before) <= set(after)
    nav = _nav(client)["primary"]
    urls = [c["url"] for g in nav for c in g.get("children") or [] if c["url"] != "/articles"]
    assert len(urls) == len(set(urls))
    for group in nav:
        children = group.get("children") or []
        if any(c["url"] == "/articles" for c in children):
            assert children[-1]["url"] == "/articles"


def test_a_header_saved_in_admin_navigation_is_shown_as_arranged(seeded, app, client):
    before = _header_topics(client)
    _topic(app, "faith-and-hope", "Faith and Hope", featured=True)
    assert _header_topics(client) == before  # the editor adds it in Admin › Navigation


def test_a_featured_topic_already_in_the_menu_is_not_repeated(seeded, app, client):
    _drop_saved_menus(app)
    linked = next(iter(_header_topics(client)))
    with app.app_context():
        topic = db.session.scalar(select(Topic).where(Topic.slug == linked.split("/")[-1]))
        topic.featured = True
        db.session.commit()
    urls = [c["url"] for g in _nav(client)["primary"] for c in g.get("children") or []]
    assert urls.count(linked) == 1


# ---- 2. bold and italic ------------------------------------------------------------------------


def test_inline_emphasis_is_kept_in_storage_and_stripped_for_plain_text():
    text = "Be **kind** to *yourself* and _others_, see [**this**](/topics/calm). snake_case 2*3"
    [block] = validate_blocks([{"type": "paragraph", "text": text}])
    assert block["text"] == text  # stored exactly as written
    assert strip_inline_links(text) == "Be kind to yourself and others, see this. snake_case 2*3"
    assert blocks_word_count([block]) == len(strip_inline_links(text).split())


def test_formatting_survives_publishing_to_the_public_api(seeded, as_role, client):
    api = as_role("editor")
    body = [
        {"type": "paragraph", "text": "A **bold** and *italic* start with [a link](/articles)."},
        {"type": "list", "ordered": True, "items": ["**One**", "*Two*"]},
    ]
    article = _draft(api, seeded, body=body)
    assert api.post(f"/api/v1/admin/articles/{article['id']}/publish").status_code == 200
    public = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert public["body"][0]["text"] == body[0]["text"]
    assert public["body"][1]["items"] == ["**One**", "*Two*"]


# ---- 3. numbered lists that continue -----------------------------------------------------------


def test_numbered_lists_can_continue_from_a_start_number():
    blocks = validate_blocks(
        [
            {"type": "list", "ordered": True, "items": [str(i) for i in range(1, 11)]},
            {"type": "paragraph", "text": "A pause."},
            {"type": "list", "ordered": True, "start": 11, "items": ["Eleven", "Twelve"]},
            {"type": "list", "ordered": True, "items": ["Independent"]},
            {"type": "list", "ordered": False, "start": 5, "items": ["Bullet"]},
            {"type": "list", "ordered": True, "start": 1, "items": ["Default"]},
        ]
    )
    assert "start" not in blocks[0]
    assert blocks[2]["start"] == 11
    assert "start" not in blocks[3]  # independent lists are not continued automatically
    assert "start" not in blocks[4]  # bullets have no numbers
    assert "start" not in blocks[5]
    for bad in (0, -1, 10001, "11", True, 1.5):
        with pytest.raises(ValidationError):
            validate_blocks([{"type": "list", "ordered": True, "start": bad, "items": ["x"]}])


def test_list_start_survives_publishing(seeded, as_role, client):
    api = as_role("editor")
    body = [
        {"type": "list", "ordered": True, "items": ["One", "Two"]},
        {"type": "paragraph", "text": "Between."},
        {"type": "list", "ordered": True, "start": 3, "items": ["Three"]},
    ]
    article = _draft(api, seeded, body=body)
    assert api.post(f"/api/v1/admin/articles/{article['id']}/publish").status_code == 200
    public = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert public["body"][2]["start"] == 3 and "start" not in public["body"][0]
