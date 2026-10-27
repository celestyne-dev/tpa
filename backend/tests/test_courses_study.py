"""Batch 09.1: lesson drafts and revisions, and learners' private study tools (notes,
highlights with stable anchors, bookmarks, saved checklists, reading position,
preferences, notebook and export), course search authorization and privacy."""

from __future__ import annotations

from app.extensions import db
from app.models import (
    AuditLog,
    CourseLesson,
    Customer,
    Entitlement,
    LearnerBookmark,
    LearnerHighlight,
    LearnerNote,
    LearnerPreference,
)

from .conftest import PASSWORD, register_customer
from .test_courses_admin import COURSES, add_lesson, add_module, create_course, lesson_body
from .test_courses_learning import premium  # noqa: F401  (fixture)

LEARN = "/api/v1/account/learning"
STUDY = "/api/v1/account/study"
PASSAGE = "Most people reach for their phone before they are fully awake."
TEXT = f"Mornings shape the day. {PASSAGE} A short pause changes that."


def _course(editor, title="Study Course", body=None, **lesson_extra):
    course = create_course(editor, title)
    module = add_module(editor, course["id"])
    lesson = add_lesson(
        editor,
        course["id"],
        module["id"],
        "First light",
        body=body if body is not None else lesson_body(text=TEXT),
        **lesson_extra,
    )
    second = add_lesson(editor, course["id"], module["id"], "Second light")
    res = editor.post(f"{COURSES}/{course['id']}/publish", {})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"], module, lesson, second


def _learner(app, email="reader@example.com", slug="study-course"):
    learner = register_customer(app, email, verify=True)
    assert learner.post(f"{LEARN}/{slug}/enroll").status_code in (200, 201)
    return learner


def _lesson(learner, slug="study-course", lesson="first-light"):
    res = learner.get(f"{LEARN}/{slug}/lessons/{lesson}")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _block(data, kind="paragraph"):
    return next(b for b in data["lesson"]["body"] if b["type"] == kind)


def _admin_lesson(editor, course_id, lesson_id):
    res = editor.get(f"{COURSES}/{course_id}/lessons/{lesson_id}")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _save(editor, course_id, lesson_id, **fields):
    current = _admin_lesson(editor, course_id, lesson_id)
    res = editor.patch(
        f"{COURSES}/{course_id}/lessons/{lesson_id}",
        {"lock_version": current["lock_version"], **fields},
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _publish(editor, course_id, lesson_id, note=""):
    res = editor.post(f"{COURSES}/{course_id}/lessons/{lesson_id}/publish", {"note": note})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _texts(blocks):
    return [b.get("text") for b in blocks if b["type"] == "paragraph"]


# ---- drafts, publication and revisions -------------------------------------------------------


def test_drafts_never_change_live_content_until_published(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    learner = _learner(seeded)
    assert _texts(_lesson(learner)["lesson"]["body"]) == [TEXT]

    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    body[1] = {**body[1], "text": "A rewritten paragraph that is still a draft."}
    draft = _save(editor, course["id"], lesson["id"], body=body, title="First light, revised")
    assert draft["has_draft_changes"] is True and draft["title"] == "First light, revised"
    assert draft["live"]["revision"] == 1 and draft["live"]["title"] == "First light"
    assert draft["draft_saved_by"] and draft["draft_saved_at"]

    # Learners (and the public outline) still get the published version.
    live = _lesson(learner)
    assert live["lesson"]["title"] == "First light" and _texts(live["lesson"]["body"]) == [TEXT]
    syllabus = learner.get("/api/v1/courses/study-course").get_json()["data"]["syllabus"]
    assert syllabus[0]["lessons"][0]["title"] == "First light"

    published = _publish(editor, course["id"], lesson["id"], note="Clearer opening")
    assert published["has_draft_changes"] is False and published["live"]["revision"] == 2
    live = _lesson(learner)
    assert live["lesson"]["title"] == "First light, revised"
    assert _texts(live["lesson"]["body"]) == ["A rewritten paragraph that is still a draft."]

    history = editor.get(f"{COURSES}/{course['id']}/lessons/{lesson['id']}/revisions")
    revisions = history.get_json()["data"]
    assert [(r["number"], r["action"], r["live"]) for r in revisions] == [
        (2, "published", True),
        (1, "published", False),
    ]
    assert revisions[0]["note"] == "Clearer opening"
    # Publishing again with nothing new doesn't create a revision.
    _publish(editor, course["id"], lesson["id"])
    assert (
        len(
            editor.get(f"{COURSES}/{course['id']}/lessons/{lesson['id']}/revisions").get_json()[
                "data"
            ]
        )
        == 2
    )
    with seeded.app_context():
        actions = [a.action for a in db.session.scalars(db.select(AuditLog))]
        assert (
            "course.lesson_draft_saved" in actions and actions.count("course.lesson_published") >= 2
        )


def test_compare_and_restore_revisions(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    base = f"{COURSES}/{course['id']}/lessons/{lesson['id']}"
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    new_body = [b for b in body if b["type"] != "key_points"]
    new_body[1] = {**new_body[1], "text": "Changed text."}
    new_body.append({"type": "paragraph", "text": "A new closing paragraph."})
    _save(editor, course["id"], lesson["id"], body=new_body, summary="Updated summary")

    diff = editor.get(f"{base}/compare?left=live&right=draft").get_json()["data"]
    assert diff["counts"] == {"added": 1, "removed": 1, "changed": 1} and not diff["identical"]
    assert {f["field"] for f in diff["fields"]} == {"summary"}
    changed = next(b for b in diff["blocks"] if b["status"] == "changed")
    assert changed["before"] == TEXT and changed["after"] == "Changed text."
    _publish(editor, course["id"], lesson["id"])
    assert editor.get(f"{base}/compare?left=1&right=2").get_json()["data"]["counts"]["added"] == 1
    assert editor.get(f"{base}/compare?left=1&right=9").status_code == 404

    detail = editor.get(f"{base}/revisions/1").get_json()["data"]
    assert _texts(detail["body"]) == [TEXT] and detail["preview_body"]

    current = _admin_lesson(editor, course["id"], lesson["id"])
    restored = editor.post(
        f"{base}/revisions/1/restore", {"lock_version": current["lock_version"]}
    ).get_json()["data"]
    assert restored["has_draft_changes"] is True and _texts(restored["body"]) == [TEXT]
    learner = _learner(seeded)
    assert _texts(_lesson(learner)["lesson"]["body"])[0] == "Changed text."  # not live yet

    current = _admin_lesson(editor, course["id"], lesson["id"])
    res = editor.post(
        f"{base}/revisions/1/restore", {"lock_version": current["lock_version"], "publish": True}
    )
    assert res.status_code == 200 and res.get_json()["data"]["live"]["revision"] == 3
    assert _texts(_lesson(learner)["lesson"]["body"]) == [TEXT]
    top = editor.get(f"{base}/revisions").get_json()["data"][0]
    assert top["action"] == "restored" and top["restored_from"] == 1
    with seeded.app_context():
        actions = [a.action for a in db.session.scalars(db.select(AuditLog))]
        assert actions.count("course.lesson_revision_restored") == 2

    # Discarding a draft returns the editor to the live version.
    _save(editor, course["id"], lesson["id"], title="Abandoned idea")
    current = _admin_lesson(editor, course["id"], lesson["id"])
    res = editor.post(f"{base}/discard-draft", {"lock_version": current["lock_version"]})
    data = res.get_json()["data"]
    assert data["has_draft_changes"] is False and data["title"] == "First light"


def test_concurrent_edits_are_refused_not_overwritten(seeded, as_role):
    editor = as_role("editor")
    other = as_role("editor_in_chief", email="chief@example.org")
    course, _, lesson, _ = _course(editor)
    url = f"{COURSES}/{course['id']}/lessons/{lesson['id']}"
    opened = _admin_lesson(editor, course["id"], lesson["id"])["lock_version"]
    assert other.patch(url, {"lock_version": opened, "title": "Chief's title"}).status_code == 200
    stale = editor.patch(url, {"lock_version": opened, "title": "Editor's title"})
    error = stale.get_json()["error"]
    assert stale.status_code == 409 and error["code"] == "edit_conflict"
    assert error["details"]["lock_version"] == opened + 1 and error["details"]["saved_by"]
    assert editor.patch(url, {"title": "No version"}).status_code == 400
    assert _admin_lesson(editor, course["id"], lesson["id"])["title"] == "Chief's title"
    # Restoring also needs the current version.
    res = editor.post(f"{url}/revisions/1/restore", {"lock_version": opened})
    assert res.status_code == 409


def test_draft_preview_publishing_and_revision_permissions(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    url = f"{COURSES}/{course['id']}/lessons/{lesson['id']}"
    _save(editor, course["id"], lesson["id"], title="Secret draft title")

    writer = as_role("content_editor", email="writer@example.org")
    draft = _admin_lesson(writer, course["id"], lesson["id"])
    assert draft["title"] == "Secret draft title"
    assert (
        writer.patch(url, {"lock_version": draft["lock_version"], "summary": "ok"}).status_code
        == 200
    )
    assert writer.post(f"{url}/publish", {}).status_code == 403
    assert writer.post(f"{url}/status", {"status": "draft"}).status_code == 403
    assert writer.get(f"{url}/revisions").status_code == 200
    current = _admin_lesson(writer, course["id"], lesson["id"])
    assert (
        writer.post(
            f"{url}/revisions/1/restore", {"lock_version": current["lock_version"]}
        ).status_code
        == 403
    )

    for role in ("analyst", "customer_support", "marketing_manager"):
        viewer = as_role(role, email=f"{role}@example.org")
        assert viewer.get(url).status_code == 403
        assert viewer.get(f"{url}/compare?left=live&right=draft").status_code == 403
        assert viewer.get(f"{url}/revisions").status_code == 403
        assert viewer.patch(url, {"lock_version": 1, "title": "x"}).status_code == 403
        # The course outline shows the live title, never the draft.
        outline = viewer.get(f"{COURSES}/{course['id']}").get_json()["data"]["modules"]
        assert outline[0]["lessons"][0]["title"] == "First light"
    # Customers can't reach staff endpoints at all.
    learner = _learner(seeded)
    assert learner.get(url).status_code == 401


def test_lesson_address_is_fixed_once_published(seeded, as_role):
    editor = as_role("editor")
    course, module, lesson, _ = _course(editor)
    url = f"{COURSES}/{course['id']}/lessons/{lesson['id']}"
    current = _admin_lesson(editor, course["id"], lesson["id"])
    res = editor.patch(url, {"lock_version": current["lock_version"], "slug": "renamed"})
    assert res.status_code == 400 and "slug" in res.get_json()["error"]["details"]
    fresh = add_lesson(editor, course["id"], module["id"], "Unpublished", publish=False)
    data = _admin_lesson(editor, course["id"], fresh["id"])
    res = editor.patch(
        f"{COURSES}/{course['id']}/lessons/{fresh['id']}",
        {"lock_version": data["lock_version"], "slug": "better-address"},
    )
    assert res.status_code == 200 and res.get_json()["data"]["slug"] == "better-address"


def test_blocks_and_checklist_items_keep_stable_ids_across_edits(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    uids = [b["uid"] for b in body]
    assert len(set(uids)) == len(uids) and all(uids)
    # An editor that drops the ids (e.g. a pasted copy) keeps them for unchanged blocks.
    stripped = [{k: v for k, v in b.items() if k != "uid"} for b in body]
    saved = _save(editor, course["id"], lesson["id"], body=stripped[::-1])
    assert [b["uid"] for b in saved["body"]] == uids[::-1]
    # Duplicate or invalid ids are replaced.
    dupes = [{**b, "uid": "same1"} for b in body]
    saved = _save(editor, course["id"], lesson["id"], body=dupes)
    assert len({b["uid"] for b in saved["body"]}) == len(body)
    bad = _save(editor, course["id"], lesson["id"], body=[{**body[0], "uid": "<script>"}])
    assert bad["body"][0]["uid"] != "<script>"


# ---- highlights and anchors -------------------------------------------------------------------


def _highlight(learner, block, quote=PASSAGE, color="yellow", lesson="first-light"):
    start = block["text"].find(quote)
    return learner.post(
        f"{LEARN}/study-course/lessons/{lesson}/highlights",
        {
            "anchor": {
                "block": block["uid"],
                "quote": quote,
                "prefix": block["text"][max(0, start - 20) : start],
                "suffix": block["text"][start + len(quote) : start + len(quote) + 20],
                "start": start,
            },
            "color": color,
        },
    )


def test_highlights_are_validated_and_never_change_lesson_content(seeded, as_role):
    editor = as_role("editor")
    _course(editor)
    learner = _learner(seeded)
    data = _lesson(learner)
    block = _block(data)
    with seeded.app_context():
        before = db.session.scalar(
            db.select(CourseLesson).where(CourseLesson.slug == "first-light")
        ).body
    res = _highlight(learner, block, color="green")
    assert res.status_code == 201, res.get_json()
    highlight = res.get_json()["data"]
    assert highlight["anchor"]["quote"] == PASSAGE and highlight["anchor"]["start"] == block[
        "text"
    ].find(PASSAGE)
    assert highlight["color"] == "green" and highlight["status"] == "anchored"
    with seeded.app_context():
        after = db.session.scalar(
            db.select(CourseLesson).where(CourseLesson.slug == "first-light")
        ).body
    assert after == before
    # The same passage twice updates the colour instead of stacking highlights.
    again = _highlight(learner, block, color="blue").get_json()["data"]
    assert again["id"] == highlight["id"] and again["color"] == "blue"
    # Text that isn't in the block, unknown blocks and bad colours are refused.
    assert _highlight(learner, block, quote="Words the lesson never says").status_code == 400
    assert _highlight(learner, {**block, "uid": "nope0"}).status_code == 400
    assert _highlight(learner, block, color="purple").status_code == 400
    key_points = _block(data, "key_points")
    assert (
        _highlight(learner, {**key_points, "text": "Slow down"}, quote="Slow down").status_code
        == 201
    )
    # It comes back with the lesson for the reader to paint.
    study = _lesson(learner)["study"]
    assert {h["anchor"]["quote"] for h in study["highlights"]} == {PASSAGE, "Slow down"}
    # Colour change and removal.
    url = f"{STUDY}/highlights/{highlight['id']}"
    assert learner.patch(url, {"color": "pink"}).get_json()["data"]["color"] == "pink"
    assert learner.c.delete(url, headers=learner.headers()).status_code == 200
    assert learner.c.delete(url, headers=learner.headers()).status_code == 404


def test_highlights_reanchor_after_edits_or_become_orphaned_excerpts(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    learner = _learner(seeded)
    block = _block(_lesson(learner))
    highlight = _highlight(learner, block).get_json()["data"]
    note = learner.post(
        f"{LEARN}/study-course/lessons/first-light/notes",
        {"body": "This is me every morning.", "anchor": {"block": block["uid"], "quote": PASSAGE}},
    ).get_json()["data"]

    # 1. Text added before the passage in the same paragraph: offsets move, still anchored.
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    body[1] = {**body[1], "text": "New first sentence here. " + TEXT}
    _save(editor, course["id"], lesson["id"], body=body)
    # Drafts don't touch anchors.
    assert (
        _lesson(learner)["study"]["highlights"][0]["anchor"]["start"]
        == highlight["anchor"]["start"]
    )
    _publish(editor, course["id"], lesson["id"])
    moved = _lesson(learner)["study"]["highlights"][0]
    assert moved["status"] == "anchored" and moved["anchor"]["block"] == block["uid"]
    assert moved["anchor"]["start"] == highlight["anchor"]["start"] + len(
        "New first sentence here. "
    )

    # 2. The paragraph is split: the passage now lives in a new block → relocated.
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    body[1] = {"type": "paragraph", "text": "Mornings shape the day."}
    body.insert(2, {"type": "paragraph", "text": f"{PASSAGE} A short pause changes that."})
    _save(editor, course["id"], lesson["id"], body=body)
    _publish(editor, course["id"], lesson["id"])
    data = _lesson(learner)
    relocated = data["study"]["highlights"][0]
    new_block = next(b for b in data["lesson"]["body"] if b.get("text", "").startswith(PASSAGE))
    assert relocated["status"] == "anchored" and relocated["anchor"]["block"] == new_block["uid"]
    assert data["study"]["notes"][0]["anchor"]["block"] == new_block["uid"]

    # 3. The passage is removed: kept as an orphaned excerpt, never moved elsewhere.
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    body = [b for b in body if not b.get("text", "").startswith(PASSAGE)]
    _save(editor, course["id"], lesson["id"], body=body)
    _publish(editor, course["id"], lesson["id"])
    study = _lesson(learner)["study"]
    assert study["highlights"][0]["status"] == "orphaned"
    assert study["highlights"][0]["anchor"]["quote"] == PASSAGE
    assert study["notes"][0]["anchor"]["status"] == "orphaned"
    assert study["notes"][0]["body"] == note["body"]

    # 4. Restoring the old revision brings the passage back and re-attaches it.
    current = _admin_lesson(editor, course["id"], lesson["id"])
    editor.post(
        f"{COURSES}/{course['id']}/lessons/{lesson['id']}/revisions/1/restore",
        {"lock_version": current["lock_version"], "publish": True},
    )
    assert _lesson(learner)["study"]["highlights"][0]["status"] == "anchored"


def test_ambiguous_short_quotes_are_not_guessed():
    from app.services.courses import anchors

    blocks = [
        {"uid": "aaaa1", "type": "paragraph", "text": "Pause. Breathe. Pause again."},
        {"uid": "bbbb1", "type": "paragraph", "text": "Then pause once more."},
    ]
    anchor = anchors.create(blocks, {"block": "aaaa1", "quote": "Pause", "start": 16})
    assert anchor["start"] == 16
    # Same block, both occurrences equally good after an edit → not matched.
    edited = [{"uid": "aaaa1", "type": "paragraph", "text": "x Pause y Pause z"}]
    assert anchors.resolve({**anchor, "prefix": "", "suffix": ""}, edited) is None
    # A short quote whose block disappeared is never relocated to another block.
    assert anchors.resolve(anchor, [blocks[1]]) is None


# ---- notes ---------------------------------------------------------------------------------


def test_notes_crud_privacy_and_staff_cannot_browse_them(seeded, as_role):
    editor = as_role("editor")
    course, _, _, _ = _course(editor)
    learner = _learner(seeded)
    other = _learner(seeded, "other@example.com")
    url = f"{LEARN}/study-course/lessons/first-light/notes"
    res = learner.post(url, {"body": "  Try the pause tomorrow.  "})
    assert res.status_code == 201
    note = res.get_json()["data"]
    assert note["body"] == "Try the pause tomorrow." and note["anchor"] is None
    assert note["lesson"]["slug"] == "first-light" and note["course"]["slug"] == "study-course"
    for bad in ({"body": ""}, {"body": "x" * 10_001}, {"body": "<b>bold</b>"}, {"body": 5}):
        assert learner.post(url, bad).status_code == 400

    patched = learner.patch(f"{STUDY}/notes/{note['id']}", {"body": "Tried it. It works."})
    assert (
        patched.status_code == 200 and patched.get_json()["data"]["body"] == "Tried it. It works."
    )
    # Another learner can neither read, change nor delete it.
    assert other.patch(f"{STUDY}/notes/{note['id']}", {"body": "mine now"}).status_code == 404
    assert other.c.delete(f"{STUDY}/notes/{note['id']}", headers=other.headers()).status_code == 404
    assert other.get(f"{STUDY}/notebook").get_json()["data"]["notes"] == []
    assert _lesson(other)["study"]["notes"] == []
    assert [n["body"] for n in learner.get(f"{STUDY}/notebook").get_json()["data"]["notes"]] == [
        "Tried it. It works."
    ]
    # Staff course-management endpoints never include learners' notes.
    support = as_role("customer_support", email="support@example.org")
    enrollments = support.get(f"{COURSES}/{course['id']}/enrollments").get_json()["data"]
    detail = support.get(f"{COURSES}/{course['id']}/enrollments/{enrollments[0]['id']}")
    assert "Tried it" not in detail.get_data(as_text=True)
    assert support.get(f"{STUDY}/notebook").status_code == 401
    # Mutations need the customer CSRF token.
    res = learner.c.patch(f"{STUDY}/notes/{note['id']}", json={"body": "no csrf"})
    assert res.status_code == 403
    assert (
        learner.c.delete(f"{STUDY}/notes/{note['id']}", headers=learner.headers()).status_code
        == 200
    )


# ---- bookmarks, checklists, position, preferences -------------------------------------------


def test_bookmarks_follow_course_access(seeded, premium, client):  # noqa: F811
    from .test_courses_learning import _pay

    buyer = register_customer(seeded, "buyer@example.com", verify=True)
    _pay(client, premium, buyer)
    lesson = premium["lesson"]["slug"]
    url = f"{LEARN}/resilience-course/lessons/{lesson}/bookmark"
    assert buyer.put(url, {"bookmarked": True}).get_json()["data"] == {"bookmarked": True}
    assert buyer.put(url, {"bookmarked": True}).status_code == 200  # idempotent
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(LearnerBookmark.id))) == 1
    marks = buyer.get(f"{STUDY}/notebook?course=resilience-course").get_json()["data"]["bookmarks"]
    assert marks[0]["lesson"]["slug"] == lesson and marks[0]["access"] == "active"
    assert _lesson(buyer, "resilience-course", lesson)["study"]["bookmarked"] is True

    # A refund/revocation ends access: the bookmark stays but opens nothing.
    with seeded.app_context():
        from app.services.commerce import entitlements as ent_service

        ent_service.revoke(db.session.scalar(db.select(Entitlement)), "Refunded", None)
        db.session.commit()
    marks = buyer.get(f"{STUDY}/notebook").get_json()["data"]["bookmarks"]
    assert marks[0]["access"] == "ended" and marks[0]["lesson"]["slug"] is None
    assert buyer.get(f"{LEARN}/resilience-course/lessons/{lesson}").status_code == 403
    assert buyer.put(url, {"bookmarked": False}).status_code == 403
    # Someone who never bought it can't bookmark it either.
    stranger = register_customer(seeded, "stranger@example.com", verify=True)
    assert stranger.put(url, {"bookmarked": True}).status_code == 403


CHECKLIST = {
    "type": "checklist",
    "title": "Before bed",
    "items": ["Phone in the kitchen", "Curtains open a little"],
    "required": True,
}


def test_checklists_save_per_learner_and_survive_edits(seeded, as_role):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor, body=lesson_body(text=TEXT, blocks=[CHECKLIST]))
    learner = _learner(seeded)
    other = _learner(seeded, "other@example.com")
    data = _lesson(learner)
    checklist = _block(data, "checklist")
    first, second = [item["id"] for item in checklist["items"]]
    assert data["state"]["required_checklist"] == sorted([first, second])
    base = f"{LEARN}/study-course/lessons/first-light"
    # A required checklist must be complete before the lesson can be completed.
    blocked = learner.post(f"{base}/complete")
    assert blocked.status_code == 400 and "checklist" in blocked.get_json()["error"]["details"]
    assert learner.put(f"{base}/checklist/{first}", {"checked": True}).get_json()["data"] == {
        "checklist": [first]
    }
    assert learner.put(f"{base}/checklist/unknown1", {"checked": True}).status_code == 404
    assert learner.put(f"{base}/checklist/{first}", {"checked": "yes"}).status_code == 400
    assert _lesson(learner)["study"]["checklist"] == [first]
    assert _lesson(other)["study"]["checklist"] == []  # independent per learner

    # Editing the lesson (items reordered, one added, text elsewhere changed) keeps ticks.
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    for block in body:
        if block["type"] == "checklist":
            block["items"] = [block["items"][1], block["items"][0], {"text": "Water by the bed"}]
    _save(editor, course["id"], lesson["id"], body=body)
    _publish(editor, course["id"], lesson["id"])
    assert _lesson(learner)["study"]["checklist"] == [first]
    learner.put(f"{base}/checklist/{second}", {"checked": True})
    new_item = _block(_lesson(learner), "checklist")["items"][2]["id"]
    assert learner.post(f"{base}/complete").status_code == 400  # the new item too
    learner.put(f"{base}/checklist/{new_item}", {"checked": True})
    assert learner.post(f"{base}/complete").status_code == 200
    # Optional checklists never block completion.
    other_body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    for block in other_body:
        if block["type"] == "checklist":
            block["required"] = False
    _save(editor, course["id"], lesson["id"], body=other_body)
    _publish(editor, course["id"], lesson["id"])
    assert other.post(f"{base}/complete").status_code == 200
    notebook = learner.get(f"{STUDY}/notebook").get_json()["data"]["checklists"]
    assert notebook[0]["lists"][0]["done"] == 3 and notebook[0]["lists"][0]["total"] == 3


def test_reading_position_is_saved_and_restored_without_completing(seeded, as_role):
    editor = as_role("editor")
    _course(editor)
    learner = _learner(seeded)
    data = _lesson(learner)
    block = _block(data)
    url = f"{LEARN}/study-course/lessons/first-light/position"
    res = learner.put(url, {"block": block["uid"], "percent": 62.345})
    assert res.status_code == 200 and res.get_json()["data"]["position"] == {
        "block": block["uid"],
        "percent": 62.3,
    }
    for bad in ({"block": "nope1", "percent": 10}, {"percent": 101}, {"percent": "x"}, {"x": 1}):
        assert learner.put(url, bad).status_code == 400
    again = _lesson(learner)
    assert (
        again["study"]["position"]["block"] == block["uid"] and again["state"]["completed"] is False
    )
    card = learner.get(LEARN).get_json()["data"]["enrollments"][0]
    assert card["resume"]["slug"] == "first-light" and card["resume"]["percent"] == 62.3
    assert card["progress"]["completed_lessons"] == 0


def test_reading_preferences_persist_per_account(seeded, as_role):
    learner = register_customer(seeded, "prefs@example.com", verify=True)
    url = f"{STUDY}/preferences"
    assert learner.get(url).get_json()["data"] == {
        "font_size": "medium",
        "line_spacing": "standard",
        "width": "standard",
        "theme": "light",
    }
    saved = learner.put(url, {"theme": "dark", "font_size": "large"}).get_json()["data"]
    assert (
        saved["theme"] == "dark" and saved["font_size"] == "large" and saved["width"] == "standard"
    )
    assert learner.put(url, {"theme": "neon"}).status_code == 400
    assert learner.put(url, {"zoom": "200%"}).status_code == 400
    learner.put(url, {"width": "wide"})
    # A new session for the same account sees the same preferences.
    fresh = register_customer.__globals__["Shopper"](seeded.test_client())
    fresh.c.post("/api/v1/account/login", json={"email": "prefs@example.com", "password": PASSWORD})
    prefs = fresh.get(url).get_json()["data"]
    assert prefs["theme"] == "dark" and prefs["width"] == "wide"
    assert learner.c.put(url, json={"theme": "warm"}).status_code == 403  # CSRF required


# ---- search ----------------------------------------------------------------------------------


def test_search_is_filtered_by_access_and_publication(seeded, premium, client, as_role):  # noqa: F811
    editor = as_role("editor")
    course, module, lesson, _ = _course(
        editor, body=lesson_body(text="Gentle breathing with a lighthouse image.")
    )
    preview = add_lesson(
        editor,
        course["id"],
        module["id"],
        "Sample chapter",
        body=lesson_body(text="A free sample about tidepools."),
        is_preview=True,
    )
    assert preview["status"] == "published"
    search = "/api/v1/learning/search?q="
    anonymous = client.get(f"{search}study").get_json()["data"]
    assert [c["slug"] for c in anonymous["courses"]] == ["study-course"]
    assert client.get(f"{search}lighthouse").get_json()["data"]["lessons"] == []
    tide = client.get(f"{search}tidepools").get_json()["data"]["lessons"]
    assert [(r["slug"], r["access"]) for r in tide] == [("sample-chapter", "preview")]
    assert "tidepools" in tide[0]["snippet"]
    # Premium lesson text stays hidden from visitors who haven't bought the course.
    assert all(
        r["course"]["slug"] != "resilience-course"
        for r in client.get(f"{search}Bounce").get_json()["data"]["lessons"]
    )

    learner = _learner(seeded)
    found = learner.get(f"{search}lighthouse").get_json()["data"]["lessons"]
    assert [(r["slug"], r["access"]) for r in found] == [("first-light", "enrolled")]
    # Drafts are not searchable until published; unpublished lessons disappear.
    body = _admin_lesson(editor, course["id"], lesson["id"])["body"]
    body[1] = {**body[1], "text": "Now about zebras."}
    _save(editor, course["id"], lesson["id"], body=body)
    assert learner.get(f"{search}zebras").get_json()["data"]["lessons"] == []
    _publish(editor, course["id"], lesson["id"])
    assert len(learner.get(f"{search}zebras").get_json()["data"]["lessons"]) == 1
    editor.post(f"{COURSES}/{course['id']}/lessons/{lesson['id']}/status", {"status": "draft"})
    assert learner.get(f"{search}zebras").get_json()["data"]["lessons"] == []
    # Notes are never searched publicly, and short or empty queries are refused.
    learner.post(f"{LEARN}/study-course/lessons/second-light/notes", {"body": "secretword"})
    assert client.get(f"{search}secretword").get_json()["data"]["lessons"] == []
    assert client.get(f"{search}a").status_code == 400
    assert client.get("/api/v1/learning/search").status_code == 400
    res = learner.get(f"{search}lighthouse")
    assert res.headers["Cache-Control"] == "no-store"


def test_search_never_returns_answer_keys(seeded, as_role, client):
    editor = as_role("editor")
    course, _, lesson, _ = _course(editor)
    quiz = editor.post(
        f"{COURSES}/{course['id']}/assessments", {"title": "Check", "kind": "quiz"}
    ).get_json()["data"]
    editor.post(
        f"{COURSES}/{course['id']}/assessments/{quiz['id']}/questions",
        {
            "kind": "single_choice",
            "prompt": "Pick one",
            "options": [{"id": "a", "text": "Aardvarkish"}, {"id": "b", "text": "Other"}],
            "correct": ["a"],
            "explanation": "Platypusology explains it.",
        },
    )
    learner = _learner(seeded)
    for word in ("Aardvarkish", "Platypusology"):
        assert learner.get(f"/api/v1/learning/search?q={word}").get_json()["data"]["lessons"] == []


# ---- notebook, export, account export and deletion -------------------------------------------


def test_notebook_filters_export_and_hides_excerpts_after_access_ends(seeded, as_role):
    editor = as_role("editor")
    course, _, _, _ = _course(editor)
    _course(editor, "Second Course")
    learner = _learner(seeded)
    assert learner.post(f"{LEARN}/second-course/enroll").status_code == 201
    block = _block(_lesson(learner))
    _highlight(learner, block)
    learner.post(f"{LEARN}/study-course/lessons/first-light/notes", {"body": "Pause first."})
    learner.post(f"{LEARN}/second-course/lessons/first-light/notes", {"body": "Other course note."})
    learner.put(f"{LEARN}/study-course/lessons/second-light/bookmark", {"bookmarked": True})

    book = learner.get(f"{STUDY}/notebook").get_json()["data"]
    assert {c["slug"] for c in book["courses"]} == {"study-course", "second-course"}
    assert len(book["notes"]) == 2 and len(book["highlights"]) == 1 and len(book["bookmarks"]) == 1
    only = learner.get(f"{STUDY}/notebook?course=second-course").get_json()["data"]
    assert [n["body"] for n in only["notes"]] == ["Other course note."] and only["highlights"] == []
    keyword = learner.get(f"{STUDY}/notebook?q=reach for their phone").get_json()["data"]
    assert keyword["notes"] == [] and len(keyword["highlights"]) == 1

    text = learner.get(f"{STUDY}/export?format=txt")
    assert text.status_code == 200 and text.headers["Content-Type"].startswith("text/plain")
    assert "attachment" in text.headers["Content-Disposition"]
    body = text.get_data(as_text=True)
    assert PASSAGE in body and "Pause first." in body and "Bookmarked lesson: Second light" in body
    assert "Mornings shape the day." not in body  # only the learner's own excerpt
    pdf = learner.get(f"{STUDY}/export?format=pdf")
    assert pdf.get_data()[:5] == b"%PDF-" and pdf.headers["Cache-Control"] == "private, no-store"
    assert learner.get(f"{STUDY}/export?format=docx").status_code == 400

    # Staff end the enrolment: notes stay for the owner, excerpts are hidden.
    support = as_role("customer_support", email="support@example.org")
    enrollment = next(
        e for e in support.get(f"{COURSES}/{course['id']}/enrollments").get_json()["data"]
    )
    support.post(
        f"{COURSES}/{course['id']}/enrollments/{enrollment['id']}/revoke", {"reason": "Requested"}
    )
    book = learner.get(f"{STUDY}/notebook?course=study-course").get_json()["data"]
    assert book["notes"][0]["body"] == "Pause first."
    assert book["highlights"][0]["anchor"] == {"hidden": True, "status": "anchored"}
    assert book["highlights"][0]["lesson"]["slug"] is None
    exported = learner.get(f"{STUDY}/export?format=txt").get_data(as_text=True)
    assert PASSAGE not in exported and "Pause first." in exported
    # Owners can still tidy up their own notes and highlights.
    note_id = book["notes"][0]["id"]
    assert learner.patch(f"{STUDY}/notes/{note_id}", {"body": "Edited later."}).status_code == 200
    assert (
        learner.post(f"{LEARN}/study-course/lessons/first-light/notes", {"body": "new"}).status_code
        == 403
    )


def test_account_export_and_deletion_cover_study_records(seeded, as_role):
    editor = as_role("editor")
    _course(editor)
    learner = _learner(seeded)
    block = _block(_lesson(learner))
    _highlight(learner, block)
    learner.post(f"{LEARN}/study-course/lessons/first-light/notes", {"body": "Keep this."})
    learner.put(f"{LEARN}/study-course/lessons/first-light/bookmark", {"bookmarked": True})
    learner.put(f"{STUDY}/preferences", {"theme": "warm"})
    learner.put(
        f"{LEARN}/study-course/lessons/first-light/position", {"block": block["uid"], "percent": 40}
    )

    exported = learner.post("/api/v1/account/export", {"password": PASSWORD})
    export = exported.get_json()["data"]["study"]
    assert (
        export["notes"][0]["body"] == "Keep this." and export["highlights"][0]["passage"] == PASSAGE
    )
    assert len(export["bookmarks"]) == 1 and export["reading_preferences"]["theme"] == "warm"

    assert learner.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    with seeded.app_context():
        for model in (LearnerNote, LearnerHighlight, LearnerBookmark, LearnerPreference):
            assert db.session.scalar(db.select(db.func.count(model.id))) == 0
        from app.models import LessonProgress

        rows = db.session.scalars(db.select(LessonProgress)).all()
        assert all(r.position is None and r.checklist == [] for r in rows)
        assert (
            db.session.scalar(db.select(Customer).where(Customer.email == "reader@example.com"))
            is None
        )


def test_search_is_a_reserved_course_address(seeded, as_role):
    editor = as_role("editor")
    res = editor.post(COURSES, {"title": "Anything", "slug": "search"})
    assert res.status_code == 400 and "slug" in res.get_json()["error"]["details"]
    assert create_course(editor, "Search")["slug"] != "search"
