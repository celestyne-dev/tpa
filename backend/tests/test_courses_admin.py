"""Batch 09 courses, admin side: creation, curriculum, reordering, publishing, previews,
scheduling, RBAC, answer-key visibility, public catalogue and SEO."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import AuditLog, Course, CourseLesson

COURSES = "/api/v1/admin/courses"


def lesson_body(text="Breathe in slowly and notice three things you can see.", **extra):
    return [
        {"type": "heading", "text": "Why it matters", "level": 2},
        {"type": "paragraph", "text": text},
        {"type": "key_points", "title": "Remember", "items": ["Slow down", "Notice"]},
        *extra.get("blocks", []),
    ]


def create_course(api, title="Calm Foundations", **extra):
    res = api.post(COURSES, {"title": title, "summary": "A short, practical course.", **extra})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def add_module(api, course_id, title="Getting started"):
    res = api.post(f"{COURSES}/{course_id}/modules", {"title": title})
    assert res.status_code == 201, res.get_json()
    return [m for m in res.get_json()["data"] if m["title"] == title][-1]


def add_lesson(
    api, course_id, module_id, title="Your first pause", body=None, publish=True, **extra
):
    res = api.post(
        f"{COURSES}/{course_id}/modules/{module_id}/lessons",
        {"title": title, "body": body if body is not None else lesson_body(), **extra},
    )
    assert res.status_code == 201, res.get_json()
    lesson = res.get_json()["data"]
    if publish:
        res = api.post(
            f"{COURSES}/{course_id}/lessons/{lesson['id']}/status", {"status": "published"}
        )
        assert res.status_code == 200, res.get_json()
        lesson = res.get_json()["data"]
    return lesson


def ready_course(api, title="Calm Foundations", lessons=2, **extra):
    """A published free course with one module and ``lessons`` published lessons."""
    course = create_course(api, title, outcomes=["Pause before reacting"], **extra)
    module = add_module(api, course["id"])
    made = [
        add_lesson(api, course["id"], module["id"], title=f"Lesson {i + 1}") for i in range(lessons)
    ]
    res = api.post(f"{COURSES}/{course['id']}/publish", {})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"], module, made


# ---- creation, publication and public visibility -------------------------------------------


def test_course_lifecycle_and_public_visibility(seeded, as_role, client):
    editor = as_role("editor")
    course = create_course(editor, "Calm Foundations", subtitle="Two weeks to a calmer start")
    assert course["status"] == "draft" and course["slug"] == "calm-foundations"
    assert client.get("/api/v1/courses/calm-foundations").status_code == 404
    assert client.get("/api/v1/courses").get_json()["data"] == []

    # Not publishable without published lessons.
    res = editor.post(f"{COURSES}/{course['id']}/publish", {})
    assert (
        res.status_code == 400
        and "Publish at least one lesson." in res.get_json()["error"]["details"]["readiness"]
    )

    module = add_module(editor, course["id"], "Week one")
    first = add_lesson(editor, course["id"], module["id"], "Notice the pause")
    draft = add_lesson(
        editor,
        course["id"],
        module["id"],
        "Unfinished lesson",
        body=lesson_body("SECRET DRAFT TEXT"),
        publish=False,
    )
    res = editor.post(f"{COURSES}/{course['id']}/publish", {})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "published"

    public = client.get("/api/v1/courses/calm-foundations").get_json()["data"]
    titles = [lesson["title"] for m in public["syllabus"] for lesson in m["lessons"]]
    assert titles == ["Notice the pause"]  # drafts never listed
    raw = client.get("/api/v1/courses/calm-foundations").get_data(as_text=True)
    assert "SECRET DRAFT TEXT" not in raw and "Breathe in slowly" not in raw  # no lesson content
    assert public["is_free"] and public["lesson_count"] == 1 and public["outcomes"] == []
    listing = client.get("/api/v1/courses").get_json()
    assert [c["slug"] for c in listing["data"]] == ["calm-foundations"]

    # Private preview shows drafts to staff only.
    preview = editor.get(f"{COURSES}/{course['id']}/preview").get_json()["data"]
    assert [lesson["title"] for lesson in preview["syllabus"][0]["lessons"]] == [
        "Notice the pause",
        "Unfinished lesson",
    ]
    assert client.get(f"{COURSES}/{course['id']}/preview").status_code == 401

    # Sitemap and known internal links include the course page; lessons never appear.
    sitemap = client.get("/api/v1/sitemap").get_json()["data"]
    paths = [e["path"] for e in sitemap]
    assert "/courses/calm-foundations" in paths and "/courses" in paths
    assert not any(p.startswith("/learn") for p in paths)

    # Published courses keep their address.
    res = editor.patch(f"{COURSES}/{course['id']}", {"slug": "renamed"})
    assert res.status_code == 400 and "slug" in res.get_json()["error"]["details"]

    res = editor.post(f"{COURSES}/{course['id']}/unpublish", {})
    assert res.status_code == 200
    assert client.get("/api/v1/courses/calm-foundations").status_code == 404
    with seeded.app_context():
        actions = set(
            db.session.scalars(db.select(AuditLog.action).where(AuditLog.resource_type == "course"))
        )
    assert {
        "course.created",
        "course.published",
        "course.unpublished",
        "course.lesson_created",
    } <= actions
    assert first["status"] == "published" and draft["status"] == "draft"


def test_scheduled_publication_uses_the_existing_scheduler(seeded, as_role, client):
    from app.services.publication_service import publish_due_scheduled

    editor = as_role("editor")
    course = create_course(editor, "Scheduled Course")
    module = add_module(editor, course["id"])
    add_lesson(editor, course["id"], module["id"])
    when = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    res = editor.post(f"{COURSES}/{course['id']}/publish", {"publish_at": when})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "scheduled"
    assert client.get("/api/v1/courses/scheduled-course").status_code == 404
    with seeded.app_context():
        assert publish_due_scheduled()["published"] == []
        result = publish_due_scheduled(datetime.now(UTC) + timedelta(days=2))
        db.session.commit()
    assert "scheduled-course" in result["published"]
    assert client.get("/api/v1/courses/scheduled-course").status_code == 200


def test_details_validation_media_authors_and_products(seeded, as_role):
    editor = as_role("editor")
    res = editor.post(COURSES, {"title": ""})
    assert res.status_code == 400
    course = create_course(editor, "Validated Course")
    bad = editor.patch(
        f"{COURSES}/{course['id']}",
        {
            "level": "expert",
            "access_type": "vip",
            "outcomes": ["<b>bold</b>"],
            "cover_media_id": 99999,
            "author_id": 99999,
            "access_days": 0,
            "description": [{"type": "video", "url": "https://youtu.be/x"}],
            "unknown": 1,
        },
    )
    details = bad.get_json()["error"]["details"]
    assert bad.status_code == 400
    assert {
        "level",
        "access_type",
        "outcomes",
        "cover_media_id",
        "author_id",
        "access_days",
        "_unknown",
    } <= set(details)
    # A product of another type can't be linked; only "Online course" products.
    from .test_commerce_catalogue import _create

    admin = as_role("super_admin", email="boss@example.org")
    workbook = _create(admin, "Workbook", product_type="workbook")
    res = editor.patch(f"{COURSES}/{course['id']}", {"product_id": workbook["id"]})
    assert res.status_code == 400 and "product_id" in res.get_json()["error"]["details"]
    product = _create(admin, "Course access", product_type="course")
    res = editor.patch(
        f"{COURSES}/{course['id']}", {"product_id": product["id"], "access_type": "premium"}
    )
    assert res.status_code == 200
    other = create_course(editor, "Second Course")
    res = editor.patch(f"{COURSES}/{other['id']}", {"product_id": product["id"]})
    assert res.status_code == 400  # one product, one course
    # Edit conflicts are detected.
    stale = editor.patch(f"{COURSES}/{course['id']}", {"subtitle": "x", "lock_version": 1})
    assert stale.status_code == 409


# ---- curriculum ---------------------------------------------------------------------------


def test_curriculum_reordering_is_validated_server_side(seeded, as_role):
    editor = as_role("editor")
    course = create_course(editor)
    m1 = add_module(editor, course["id"], "One")
    m2 = add_module(editor, course["id"], "Two")
    a = add_lesson(editor, course["id"], m1["id"], "A", publish=False)
    b = add_lesson(editor, course["id"], m1["id"], "B", publish=False)
    c = add_lesson(editor, course["id"], m2["id"], "C", publish=False)
    url = f"{COURSES}/{course['id']}/curriculum"
    # Move B to module two (first), swap the modules.
    layout = [
        {"module_id": m2["id"], "lesson_ids": [b["id"], c["id"]]},
        {"module_id": m1["id"], "lesson_ids": [a["id"]]},
    ]
    res = editor.put(url, {"layout": layout})
    assert res.status_code == 200, res.get_json()
    modules = res.get_json()["data"]
    assert [m["title"] for m in modules] == ["Two", "One"]
    assert [lesson["title"] for lesson in modules[0]["lessons"]] == ["B", "C"]
    assert [lesson["position"] for lesson in modules[0]["lessons"]] == [0, 1]
    for broken in (
        [{"module_id": m2["id"], "lesson_ids": [b["id"], c["id"]]}],  # module missing
        [
            {"module_id": m2["id"], "lesson_ids": [b["id"], b["id"], c["id"]]},
            {"module_id": m1["id"], "lesson_ids": [a["id"]]},
        ],  # duplicate lesson
        [
            {"module_id": m2["id"], "lesson_ids": [c["id"]]},
            {"module_id": m1["id"], "lesson_ids": [a["id"]]},
        ],  # lesson missing
        [
            {"module_id": 99999, "lesson_ids": [a["id"], b["id"], c["id"]]},
            {"module_id": m1["id"], "lesson_ids": []},
        ],  # foreign module
    ):
        assert editor.put(url, {"layout": broken}).status_code == 400
    # Another course's lesson can't be addressed through this course.
    other = create_course(editor, "Other")
    assert editor.get(f"{COURSES}/{other['id']}/lessons/{a['id']}").status_code == 404
    with seeded.app_context():
        positions = db.session.execute(
            db.select(CourseLesson.module_id, CourseLesson.position).where(
                CourseLesson.course_id == course["id"]
            )
        ).all()
    assert len(positions) == len(set(positions)) == 3


def test_lesson_content_blocks_are_text_only(seeded, as_role):
    editor = as_role("editor")
    course = create_course(editor)
    module = add_module(editor, course["id"])
    url = f"{COURSES}/{course['id']}/modules/{module['id']}/lessons"
    video = editor.post(
        url, {"title": "Video", "body": [{"type": "video", "url": "https://youtu.be/dQw4w9WgXcQ"}]}
    )
    assert video.status_code == 400
    html = editor.post(
        url, {"title": "HTML", "body": [{"type": "paragraph", "text": "<script>x</script>"}]}
    )
    assert html.status_code == 400
    rich = [
        {
            "type": "example",
            "title": "Maya's morning",
            "text": "Maya paused before replying.",
            "variant": "case_study",
        },
        {
            "type": "exercise",
            "id": "notice-three",
            "prompt": "Write three things you noticed.",
            "required": True,
        },
        {"type": "checklist", "title": "Before bed", "items": ["Phone away", "Lights low"]},
        {
            "type": "further_reading",
            "items": [
                {"label": "Our guide to rest", "href": "/articles/rest", "note": "Five minutes"}
            ],
        },
        {"type": "quote", "text": "Slow is smooth.", "cite": "Proverb"},
    ]
    res = editor.post(url, {"title": "Rich lesson", "body": rich})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["reading_minutes"] >= 1
    dup = editor.post(url, {"title": "Dup", "body": [rich[1], rich[1]]})
    assert dup.status_code == 400
    download = editor.post(url, {"title": "DL", "body": [{"type": "download", "file_id": "abc"}]})
    assert download.status_code == 400  # no course product, so no worksheets yet
    # Lesson slugs are unique within a course.
    first = editor.post(url, {"title": "Same title"}).get_json()["data"]
    second = editor.post(url, {"title": "Same title"}).get_json()["data"]
    assert first["slug"] != second["slug"]


def test_deleting_curriculum_with_learner_progress_is_blocked(seeded, as_role):
    from .conftest import register_customer

    editor = as_role("editor")
    course, module, lessons = ready_course(editor, "Kept Course")
    learner = register_customer(seeded)
    assert learner.post("/api/v1/account/learning/kept-course/enroll").status_code == 201
    assert (
        learner.get(
            f"/api/v1/account/learning/kept-course/lessons/{lessons[0]['slug']}"
        ).status_code
        == 200
    )
    res = editor.delete(f"{COURSES}/{course['id']}/lessons/{lessons[0]['id']}")
    assert res.status_code == 409
    assert editor.delete(f"{COURSES}/{course['id']}/modules/{module['id']}").status_code == 409
    # A lesson nobody opened can go.
    assert editor.delete(f"{COURSES}/{course['id']}/lessons/{lessons[1]['id']}").status_code == 200
    # Published courses (and courses with learners) are archived, not deleted.
    assert editor.delete(f"{COURSES}/{course['id']}").status_code == 409


def test_duplicate_archive_restore(seeded, as_role, client):
    editor = as_role("editor")
    course, _, _ = ready_course(editor, "Original Course")
    quiz = editor.post(
        f"{COURSES}/{course['id']}/assessments", {"title": "Check-in", "kind": "quiz"}
    ).get_json()["data"]
    editor.post(
        f"{COURSES}/{course['id']}/assessments/{quiz['id']}/questions",
        {"kind": "true_false", "prompt": "Pausing helps.", "correct": [True]},
    )
    res = editor.post(f"{COURSES}/{course['id']}/duplicate", {})
    assert res.status_code == 201
    copy = res.get_json()["data"]
    assert copy["status"] == "draft" and copy["slug"] == "original-course-copy"
    assert copy["lesson_count"] == 2 and copy["published_lesson_count"] == 0
    assert copy["assessments"][0]["question_count"] == 1 and copy["product"] is None
    assert editor.post(f"{COURSES}/{course['id']}/archive", {}).status_code == 200
    assert client.get("/api/v1/courses/original-course").status_code == 404
    assert editor.patch(f"{COURSES}/{course['id']}", {"subtitle": "x"}).status_code == 409
    assert (
        editor.post(f"{COURSES}/{course['id']}/restore", {}).get_json()["data"]["status"] == "draft"
    )
    # A never-published draft without learners can be deleted.
    assert editor.delete(f"{COURSES}/{copy['id']}").status_code == 200


# ---- permissions --------------------------------------------------------------------------


def test_course_permissions_are_enforced_by_the_api(seeded, as_role):
    editor = as_role("editor")
    course, _, _ = ready_course(editor, "Guarded Course")
    cid = course["id"]

    moderator = as_role("moderator")
    assert moderator.get(COURSES).status_code == 403

    analyst = as_role("analyst")
    assert analyst.get(COURSES).status_code == 200
    assert analyst.get("/api/v1/admin/courses/reports").status_code == 200
    assert analyst.post(COURSES, {"title": "Nope"}).status_code == 403
    assert analyst.patch(f"{COURSES}/{cid}", {"subtitle": "x"}).status_code == 403
    assert analyst.get(f"{COURSES}/{cid}/enrollments").status_code == 403

    writer = as_role("content_editor")
    assert writer.post(COURSES, {"title": "Writer course", "summary": "s"}).status_code == 201
    assert writer.post(f"{COURSES}/{cid}/unpublish", {}).status_code == 403
    assert writer.post(f"{COURSES}/{cid}/archive", {}).status_code == 403
    assert writer.get("/api/v1/admin/courses/reports").status_code == 403

    support = as_role("customer_support")
    assert support.get(f"{COURSES}/{cid}/enrollments").status_code == 200
    assert support.patch(f"{COURSES}/{cid}", {"subtitle": "x"}).status_code == 403
    assert support.post(f"{COURSES}/{cid}/modules", {"title": "x"}).status_code == 403

    assert editor.get(f"{COURSES}/{cid}/enrollments").status_code == 403
    assert editor.get("/api/v1/admin/courses/reports").status_code == 403

    # Answer keys: only roles that manage assessments see them.
    quiz = editor.post(
        f"{COURSES}/{cid}/assessments", {"title": "Quiz", "kind": "quiz"}
    ).get_json()["data"]
    editor.post(
        f"{COURSES}/{cid}/assessments/{quiz['id']}/questions",
        {
            "kind": "single_choice",
            "prompt": "Pick one",
            "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "correct": ["b"],
            "explanation": "B is right.",
        },
    )
    seen = analyst.get(f"{COURSES}/{cid}/assessments/{quiz['id']}").get_json()["data"]
    assert seen["answer_key_visible"] is False and "correct" not in seen["questions"][0]
    assert "explanation" not in seen["questions"][0]
    full = editor.get(f"{COURSES}/{cid}/assessments/{quiz['id']}").get_json()["data"]
    assert full["questions"][0]["correct"] == ["b"]


def test_categories_topics_search_filters_and_related(seeded, as_role, client):
    editor = as_role("editor")
    cat = editor.post("/api/v1/admin/course-categories", {"name": "Mindset"})
    assert cat.status_code == 201
    category = cat.get_json()["data"]
    options = editor.get("/api/v1/admin/courses/options").get_json()["data"]
    topic_id = options["topics"][0]["id"]
    a, _, _ = ready_course(
        editor, "Resilience Basics", category_id=category["id"], topic_ids=[topic_id]
    )
    b, _, _ = ready_course(editor, "Resilience Deep Dive", category_id=category["id"])
    ready_course(editor, "Sleep Better", level="beginner")
    assert len(client.get("/api/v1/courses").get_json()["data"]) == 3
    found = client.get("/api/v1/courses?q=resilience").get_json()
    assert {c["slug"] for c in found["data"]} == {"resilience-basics", "resilience-deep-dive"}
    assert found["meta"]["categories"] == [{"slug": "mindset", "name": "Mindset"}]
    by_cat = client.get("/api/v1/courses?category=mindset&sort=title").get_json()["data"]
    assert [c["slug"] for c in by_cat] == ["resilience-basics", "resilience-deep-dive"]
    topic_slug = found["meta"]["topics"][0]["slug"]
    assert [
        c["slug"] for c in client.get(f"/api/v1/courses?topic={topic_slug}").get_json()["data"]
    ] == ["resilience-basics"]
    assert client.get("/api/v1/courses?access=premium").get_json()["data"] == []
    assert [c["slug"] for c in client.get("/api/v1/courses?level=beginner").get_json()["data"]] == [
        "sleep-better"
    ]
    detail = client.get("/api/v1/courses/resilience-basics").get_json()["data"]
    assert detail["related"][0]["slug"] == "resilience-deep-dive"
    # Categories in use can't be deleted.
    assert editor.delete(f"/api/v1/admin/course-categories/{category['id']}").status_code == 409
    assert a["category"]["name"] == "Mindset" and b["status"] == "published"


def test_preview_lessons_are_public_but_nothing_else(seeded, as_role, client):
    editor = as_role("editor")
    course = create_course(editor, "Sampled Course")
    module = add_module(editor, course["id"])
    sample = add_lesson(editor, course["id"], module["id"], "Free sample", is_preview=True)
    locked = add_lesson(editor, course["id"], module["id"], "Members only")
    editor.post(f"{COURSES}/{course['id']}/publish", {})
    ok = client.get(f"/api/v1/courses/sampled-course/preview/{sample['slug']}")
    assert ok.status_code == 200 and ok.get_json()["data"]["lesson"]["body"]
    assert client.get(f"/api/v1/courses/sampled-course/preview/{locked['slug']}").status_code == 404
    assert (
        client.get(f"/api/v1/account/learning/sampled-course/lessons/{locked['slug']}").status_code
        == 401
    )
    syllabus = client.get("/api/v1/courses/sampled-course").get_json()["data"]["syllabus"][0][
        "lessons"
    ]
    assert [lesson["slug"] for lesson in syllabus] == [sample["slug"], None]  # locked slugs hidden


def test_reserved_slugs_and_static_paths(seeded, as_role):
    api = as_role("website_manager")
    for slug in ("courses", "learn", "certificates"):
        res = api.post(
            "/api/v1/admin/pages", {"title": slug.title(), "slug": slug, "template": "standard"}
        )
        assert res.status_code == 400, slug


def test_media_used_by_a_course_is_tracked(seeded, as_role):
    from app.services.admin.media_admin import usage_index

    editor = as_role("editor")
    with seeded.app_context():
        from app.models import MediaAsset

        media_id = db.session.scalar(
            db.select(MediaAsset.id).where(MediaAsset.visibility == "public")
        )
    course = create_course(editor, "Covered Course", cover_media_id=media_id)
    assert course["cover"] is not None or media_id is None
    with seeded.app_context():
        uses = usage_index().get(media_id, [])
        assert any(u["type"] == "course" for u in uses)
        assert db.session.get(Course, course["id"]).cover_media_id == media_id
