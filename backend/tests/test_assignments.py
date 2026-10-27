"""Batch 09.2 phase 1: written assignments, submissions, supporting documents, rubrics,
grading, resubmissions, completion/certificates, permissions, privacy and access."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AssignmentAttempt,
    AssignmentFile,
    AssignmentGrade,
    AuditLog,
    CourseCertificate,
    CourseEnrollment,
    PermissionDefinition,
    Role,
)

from .conftest import PASSWORD, make_user, minimal_pdf, register_customer
from .test_courses_admin import COURSES, ready_course
from .test_vps_storage import ooxml

LEARN = "/api/v1/account/learning"
ADMIN = "/api/v1/admin"
ESSAY = "Reflection " + "word " * 60
RUBRIC = {
    "criteria": [
        {
            "title": "Insight",
            "description": "Depth of reflection",
            "max_points": 10,
            "descriptors": [{"label": "Excellent", "points": 10}, {"label": "Basic", "points": 4}],
        },
        {"title": "Clarity", "max_points": 5},
    ],
    "passing_percent": 60,
    "feedback_required": True,
}


def _key() -> str:
    return uuid.uuid4().hex


def _setup(editor, title="Writing Course", lessons=1, **assignment):
    course, _, made = ready_course(editor, title, lessons=lessons)
    payload = {
        "title": "Morning reflection",
        "kind": "reflection",
        "prompts": [{"id": "p1", "text": "What did you notice?"}],
        "requirements": {"min_words": 20, "files": "optional", "max_files": 2},
        **assignment,
    }
    res = editor.post(f"{COURSES}/{course['id']}/assignments", payload)
    assert res.status_code == 201, res.get_json()
    return course, made, res.get_json()["data"]


def _base(course, assignment):
    return f"{COURSES}/{course['id']}/assignments/{assignment['id']}"


def _rubric(editor, course, assignment, rubric=None):
    current = editor.get(_base(course, assignment)).get_json()["data"]
    res = editor.put(
        f"{_base(course, assignment)}/rubric",
        {**(rubric or RUBRIC), "lock_version": current["lock_version"]},
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _publish(editor, course, assignment):
    res = editor.post(f"{_base(course, assignment)}/status", {"status": "published"})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _ready(editor, **kw):
    course, made, assignment = _setup(editor, **kw)
    _rubric(editor, course, assignment)
    _publish(editor, course, assignment)
    return course, made, assignment


def _learner(app, slug="writing-course", email="writer@example.com"):
    learner = register_customer(app, email, verify=True)
    assert learner.post(f"{LEARN}/{slug}/enroll").status_code in (200, 201)
    return learner


def _learn_url(assignment, slug="writing-course"):
    return f"{LEARN}/{slug}/assignments/{assignment['id']}"


def _submit(learner, assignment, text=ESSAY, slug="writing-course"):
    url = _learn_url(assignment, slug)
    view = learner.get(url).get_json()["data"]
    lock = view["draft"]["lock_version"] if view["draft"] else None
    body = {"responses": {"p1": text}}
    if lock:
        body["lock_version"] = lock
    saved = learner.put(f"{url}/draft", body)
    assert saved.status_code == 200, saved.get_json()
    draft = saved.get_json()["data"]["draft"]
    res = learner.post(
        f"{url}/submit", {"idempotency_key": _key(), "lock_version": draft["lock_version"]}
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _submission_id(editor, course, assignment):
    rows = editor.get(f"{_base(course, assignment)}/submissions").get_json()["data"]
    return rows[0]["id"]


def _staff_detail(api, submission_id):
    res = api.get(f"{ADMIN}/assignment-submissions/{submission_id}")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _grade(api, attempt_id, **body):
    return api.put(f"{ADMIN}/assignment-attempts/{attempt_id}/grade", body)


def _release(api, attempt_id, lock, outcome="graded"):
    return api.post(
        f"{ADMIN}/assignment-attempts/{attempt_id}/grade/publish",
        {"lock_version": lock, "outcome": outcome},
    )


def _grade_and_release(editor, course, assignment, insight=8, clarity=4, outcome="graded"):
    sid = _submission_id(editor, course, assignment)
    attempt = _staff_detail(editor, sid)["attempts"][0]
    grade = _grade(
        editor,
        attempt["id"],
        scores={
            c: v
            for c, v in zip(_criteria(editor, course, assignment), (insight, clarity), strict=True)
        },
        feedback="Thoughtful work.",
        private_notes="Staff only: compare with cohort.",
        **({"lock_version": attempt["grade"]["lock_version"]} if attempt["grade"] else {}),
    )
    assert grade.status_code == 200, grade.get_json()
    res = _release(editor, attempt["id"], grade.get_json()["data"]["lock_version"], outcome)
    assert res.status_code == 200, res.get_json()
    return sid, attempt["id"], res.get_json()["data"]


def _criteria(api, course, assignment):
    data = api.get(_base(course, assignment)).get_json()["data"]
    return [c["id"] for c in data["rubric"]["criteria"]]


# ---- definitions and publication ---------------------------------------------------------------


def test_assignment_lifecycle_publication_and_learner_visibility(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _setup(editor)
    learner = _learner(seeded)
    assert learner.get(f"{LEARN}/writing-course/assignments").get_json()["data"] == []
    assert learner.get(_learn_url(assignment)).status_code == 404  # drafts never exposed

    res = editor.post(f"{_base(course, assignment)}/status", {"status": "published"})
    assert res.status_code == 400 and "readiness" in res.get_json()["error"]["details"]
    rubric = _rubric(editor, course, assignment)
    assert rubric["rubric"]["version"] == 1 and rubric["rubric"]["total_points"] == 15
    published = _publish(editor, course, assignment)
    assert published["status"] == "published" and published["required_since"]
    listed = learner.get(f"{LEARN}/writing-course/assignments").get_json()["data"]
    assert [a["status"] for a in listed] == ["not_started"]
    view = learner.get(_learn_url(assignment)).get_json()["data"]
    assert view["can_submit"] is True and "lock_version" not in view["assignment"]

    # Deadlines need an explicit timezone and are stored in UTC.
    current = editor.get(_base(course, assignment)).get_json()["data"]
    naive = editor.patch(
        _base(course, assignment),
        {"due_at": "2030-01-01T00:00:00", "lock_version": current["lock_version"]},
    )
    assert naive.status_code == 400 and "due_at" in naive.get_json()["error"]["details"]
    eastern = editor.patch(
        _base(course, assignment),
        {"due_at": "2030-01-01T00:00:00-05:00", "lock_version": current["lock_version"]},
    )
    assert eastern.get_json()["data"]["due_at"] == "2030-01-01T05:00:00.000Z"
    stale = editor.patch(
        _base(course, assignment), {"title": "x", "lock_version": current["lock_version"]}
    )
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "edit_conflict"

    _submit(learner, assignment)
    assert (
        editor.post(f"{_base(course, assignment)}/status", {"status": "draft"}).status_code == 409
    )
    assert editor.delete(_base(course, assignment)).status_code == 409
    archived = editor.post(f"{_base(course, assignment)}/status", {"status": "archived"})
    assert archived.status_code == 200
    assert learner.get(_learn_url(assignment)).status_code == 404
    with seeded.app_context():
        actions = {a.action for a in db.session.scalars(select(AuditLog))}
    assert {
        "assignment.created",
        "assignment.rubric_saved",
        "assignment.published",
        "assignment.archived",
    } <= actions


def test_rbac_restrictions(seeded, as_role, client):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    base = f"{COURSES}/{course['id']}/assignments"
    analyst = as_role("analyst", email="analyst@example.org")
    assert analyst.get(base).status_code == 200
    assert analyst.post(base, {"title": "Nope"}).status_code == 403
    assert analyst.get(f"{_base(course, assignment)}/report").status_code == 200
    assert analyst.get(f"{_base(course, assignment)}/submissions").status_code == 403
    support = as_role("customer_support", email="support@example.org")
    assert support.get(f"{_base(course, assignment)}/submissions").status_code == 403
    assert support.get(f"{_base(course, assignment)}/exceptions").status_code == 200
    assert editor.get(f"{_base(course, assignment)}/exceptions").status_code == 403
    moderator = as_role("moderator", email="mod@example.org")
    assert moderator.get(base).status_code == 403
    assert client.get(base).status_code == 401
    learner = _learner(seeded)
    assert learner.get(base).status_code == 401  # customer sessions never reach staff APIs


def test_assessor_scope_beyond_the_permission(seeded, as_role, app):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    _submit(learner, assignment)
    with app.app_context():
        keys = ["assignments.view", "assignments.view_submissions", "assignments.grade"]
        perms = db.session.scalars(
            select(PermissionDefinition).where(PermissionDefinition.key.in_(keys))
        ).all()
        db.session.add(
            Role(name="course_assessor", label="Course assessor", kind="custom", permissions=perms)
        )
        db.session.commit()
    uid = make_user(app, "assessor@example.org", ["course_assessor"])
    from .conftest import Api, login

    client = app.test_client()
    assert login(client, "assessor@example.org", PASSWORD).status_code == 200
    assessor = Api(client)
    url = f"{_base(course, assignment)}/submissions"
    assert assessor.get(url).status_code == 403  # the permission alone isn't enough
    nobody = make_user(app, "plain@example.org", [])
    res = editor.put(f"{COURSES}/{course['id']}/assessors", {"user_ids": [nobody]})
    assert res.status_code == 400
    res = editor.put(f"{COURSES}/{course['id']}/assessors", {"user_ids": [uid]})
    assert res.status_code == 200 and res.get_json()["data"][0]["user_id"] == uid
    assert assessor.get(url).status_code == 200
    sid = assessor.get(url).get_json()["data"][0]["id"]
    attempt = _staff_detail(assessor, sid)["attempts"][0]
    ok = _grade(assessor, attempt["id"], feedback="Draft feedback")
    assert ok.status_code == 200
    assert (
        _release(assessor, attempt["id"], ok.get_json()["data"]["lock_version"]).status_code == 403
    )


# ---- learner drafts, submission and duplicates ------------------------------------------------------


def test_drafts_submission_history_and_duplicate_requests(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    url = _learn_url(assignment)
    first = learner.put(f"{url}/draft", {"responses": {"p1": "Short start"}}).get_json()["data"]
    lock = first["draft"]["lock_version"]
    assert (
        first["submission"]["status"] == "draft"
        and first["draft"]["responses"]["p1"] == "Short start"
    )
    stale = learner.put(
        f"{url}/draft", {"responses": {"p1": "Other tab"}, "lock_version": lock - 1}
    )
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "edit_conflict"
    assert (
        learner.put(f"{url}/draft", {"responses": {"zz": "x"}, "lock_version": lock}).status_code
        == 400
    )
    incomplete = learner.post(f"{url}/submit", {"idempotency_key": _key(), "lock_version": lock})
    assert (
        incomplete.status_code == 400
        and "requirements" in incomplete.get_json()["error"]["details"]
    )
    saved = learner.put(
        f"{url}/draft", {"responses": {"p1": ESSAY}, "lock_version": lock}
    ).get_json()["data"]
    key = _key()
    body = {"idempotency_key": key, "lock_version": saved["draft"]["lock_version"]}
    created = learner.post(f"{url}/submit", body)
    assert created.status_code == 201
    retry = learner.post(f"{url}/submit", body)  # a retried request
    assert retry.status_code == 200
    data = retry.get_json()["data"]
    assert (
        data["submission"]["status"] == "pending_review"
        and data["submission"]["attempts_used"] == 1
    )
    assert data["history"][0]["latest"] is True and data["history"][0]["responses"]["p1"] == ESSAY
    assert data["can_submit"] is False and data["blocked_reason"] == "awaiting_review"
    with seeded.app_context():
        attempts = db.session.scalars(select(AssignmentAttempt)).all()
        assert [a.status for a in attempts] == ["submitted"] and attempts[0].content_sha256
    # Staff never see drafts; the submitted attempt is a frozen record.
    sid = _submission_id(editor, course, assignment)
    detail = _staff_detail(editor, sid)
    assert len(detail["attempts"]) == 1 and detail["attempts"][0]["status"] == "submitted"


# ---- supporting documents ---------------------------------------------------------------------------


def _upload(learner, assignment, data, name):
    return learner.c.post(
        f"{_learn_url(assignment)}/files",
        data={"file": (io.BytesIO(data), name)},
        headers=learner.headers(),
        content_type="multipart/form-data",
    )


def test_supporting_documents_are_validated_private_and_access_controlled(seeded, as_role, app):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    other = _learner(seeded, email="other@example.com")
    ok = _upload(learner, assignment, minimal_pdf(), "My essay (final).pdf")
    assert ok.status_code == 201, ok.get_json()
    files = ok.get_json()["data"]["draft"]["files"]
    assert files[0]["filename"] == "My essay (final).pdf" and "storage_key" not in str(
        ok.get_json()
    )
    rejected = [
        (ooxml(extra={"word/vbaProject.bin": "macro"}), "essay.docx"),
        (b"MZ\x90\x00 fake executable", "essay.pdf"),
        (minimal_pdf(b"/JavaScript (app.alert(1))\n"), "essay.pdf"),
        (minimal_pdf(), "essay.docx"),
        (b"plain text", "notes.txt"),
        (ooxml("xlsx"), "sheet.xlsx"),  # not an approved submission format
    ]
    for data, name in rejected:
        res = _upload(learner, assignment, data, name)
        assert res.status_code == 400, (name, res.get_json())
    assert _upload(learner, assignment, ooxml(), "notes.docx").status_code == 201
    over = _upload(learner, assignment, minimal_pdf(), "third.pdf")
    assert over.status_code == 400  # max_files = 2
    app.config["SUBMISSION_FILE_MAX_MB"] = 1
    try:
        big = minimal_pdf(b"%" + b"x" * (1024 * 1024 + 10) + b"\n")
        view = learner.get(_learn_url(assignment)).get_json()["data"]
        learner.c.delete(
            f"/api/v1/account/assignment-files/{view['draft']['files'][1]['id']}",
            headers=learner.headers(),
        )
        assert _upload(learner, assignment, big, "big.pdf").status_code == 400
    finally:
        app.config["SUBMISSION_FILE_MAX_MB"] = 20
    with app.app_context():
        stored = db.session.scalars(select(AssignmentFile)).all()
        root = Path(app.config["PRODUCT_FILES_ROOT"]).resolve()
        assert len(stored) == 1 and stored[0].storage_key.startswith("submissions/")
        path = root / stored[0].storage_key
        assert path.is_file() and Path(app.config["MEDIA_ROOT"]).resolve() not in path.parents
        file_id = stored[0].public_id
    dl = learner.get(f"/api/v1/account/assignment-files/{file_id}/download")
    assert dl.status_code == 200 and dl.headers["Cache-Control"] == "private, no-store"
    assert dl.data.startswith(b"%PDF")
    assert other.get(f"/api/v1/account/assignment-files/{file_id}/download").status_code == 404
    assert editor.get(f"{ADMIN}/assignment-files/{file_id}/download").status_code == 404  # draft
    _submit(learner, assignment)
    staff = editor.get(f"{ADMIN}/assignment-files/{file_id}/download")
    assert staff.status_code == 200 and staff.data.startswith(b"%PDF")
    gone = learner.c.delete(
        f"/api/v1/account/assignment-files/{file_id}", headers=learner.headers()
    )
    assert gone.status_code == 409  # submitted documents are kept
    with seeded.app_context():
        actions = [a.action for a in db.session.scalars(select(AuditLog))]
    assert (
        actions.count("assignment.file_downloaded") == 2 and "assignment.file_rejected" in actions
    )


def test_files_can_be_disabled_or_required(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor, requirements={"files": "none"})
    learner = _learner(seeded)
    assert _upload(learner, assignment, minimal_pdf(), "a.pdf").status_code == 400


# ---- grading, feedback visibility and rubric versions --------------------------------------------------


def test_grading_visibility_and_rubric_versions(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    _submit(learner, assignment)
    writer = as_role("content_editor", email="writer@example.org")
    sid = _submission_id(editor, course, assignment)
    attempt = _staff_detail(writer, sid)["attempts"][0]
    criteria = _criteria(editor, course, assignment)
    bad = _grade(writer, attempt["id"], scores={criteria[0]: 11})
    assert bad.status_code == 400
    draft = _grade(
        writer, attempt["id"], scores={criteria[0]: 8}, private_notes="Secret staff note"
    )
    assert draft.status_code == 200 and draft.get_json()["data"]["status"] == "draft"
    assert _staff_detail(editor, sid)["status"] == "under_review"
    assert learner.get(_learn_url(assignment)).get_json()["data"]["history"][0]["grade"] is None
    lock = draft.get_json()["data"]["lock_version"]
    assert _release(writer, attempt["id"], lock).status_code == 403  # can't publish grades
    incomplete = _release(editor, attempt["id"], lock)
    assert incomplete.status_code == 400  # not every criterion scored
    scored = _grade(
        editor, attempt["id"], scores={criteria[0]: 8, criteria[1]: 4}, lock_version=lock
    )
    lock = scored.get_json()["data"]["lock_version"]
    no_feedback = _release(editor, attempt["id"], lock)
    assert no_feedback.status_code == 400  # this rubric requires feedback
    scored = _grade(editor, attempt["id"], feedback="Clear and honest.", lock_version=lock)
    released = _release(editor, attempt["id"], scored.get_json()["data"]["lock_version"])
    assert released.status_code == 200 and released.get_json()["data"]["percent"] == 80
    view = learner.get(_learn_url(assignment)).get_json()["data"]
    grade = view["history"][0]["grade"]
    assert (
        grade["percent"] == 80
        and grade["passed"] is True
        and grade["feedback"] == "Clear and honest."
    )
    raw = learner.get(_learn_url(assignment)).get_data(as_text=True)
    assert "Secret staff note" not in raw and "private_notes" not in raw and "grader" not in raw
    assert view["submission"]["status"] == "completed"

    # A later rubric edit creates version 2; the released grade keeps version 1.
    new = {
        **RUBRIC,
        "criteria": [{"title": "Only criterion", "max_points": 20}],
        "passing_percent": 90,
    }
    assert _rubric(editor, course, assignment, new)["rubric"]["version"] == 2
    detail = _staff_detail(editor, sid)["attempts"][0]["grade"]
    assert detail["rubric"]["version"] == 1 and detail["percent"] == 80
    assert (
        learner.get(_learn_url(assignment)).get_json()["data"]["history"][0]["grade"]["rubric"][
            "version"
        ]
        == 1
    )
    history = editor.get(f"{_base(course, assignment)}/rubric").get_json()["data"]
    assert [r["version"] for r in history] == [2, 1]
    with seeded.app_context():
        grade_row = db.session.scalar(select(AssignmentGrade))
        assert grade_row.grader_id and grade_row.published_by_id and grade_row.published_at
        actions = [a.action for a in db.session.scalars(select(AuditLog))]
    assert "assignment.grade_published" in actions


def test_concurrent_grading_and_retraction(seeded, as_role):
    editor = as_role("editor")
    chief = as_role("editor_in_chief", email="chief@example.org")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    _submit(learner, assignment)
    sid = _submission_id(editor, course, assignment)
    attempt = _staff_detail(editor, sid)["attempts"][0]
    first = _grade(editor, attempt["id"], feedback="One")
    lock = first.get_json()["data"]["lock_version"]
    assert _grade(chief, attempt["id"], feedback="Two", lock_version=lock).status_code == 200
    stale = _grade(editor, attempt["id"], feedback="Three", lock_version=lock)
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "edit_conflict"
    _, attempt_id, released = _grade_and_release(chief, course, assignment)
    res = chief.post(
        f"{ADMIN}/assignment-attempts/{attempt_id}/grade/retract",
        {"lock_version": released["lock_version"], "reason": "Scored the wrong rubric row"},
    )
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "retracted"
    assert learner.get(_learn_url(assignment)).get_json()["data"]["history"][0]["grade"] is None
    assert _staff_detail(editor, sid)["status"] == "under_review"
    with seeded.app_context():
        assert "assignment.grade_retracted" in [
            a.action for a in db.session.scalars(select(AuditLog))
        ]


# ---- resubmissions, attempts, deadlines and exceptions --------------------------------------------------


def test_resubmissions_follow_policy_attempts_and_exceptions(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor, max_attempts=2, resubmission_policy="on_request")
    learner = _learner(seeded)
    _submit(learner, assignment)
    sid, attempt1, _ = _grade_and_release(editor, course, assignment, outcome="changes_requested")
    view = learner.get(_learn_url(assignment)).get_json()["data"]
    assert view["submission"]["status"] == "changes_requested" and view["can_submit"] is True
    assert view["history"][0]["grade"]["outcome"] == "changes_requested"
    _submit(learner, assignment, ESSAY + " revised")
    detail = _staff_detail(editor, sid)
    assert detail["status"] == "resubmitted" and [a["number"] for a in detail["attempts"]] == [2, 1]
    assert detail["attempts"][0]["latest"] is True and detail["attempts"][1]["latest"] is False
    old = _grade(editor, attempt1, feedback="late edit", lock_version=1)
    assert old.status_code == 409  # history isn't regraded
    _grade_and_release(editor, course, assignment, outcome="changes_requested")
    view = learner.get(_learn_url(assignment)).get_json()["data"]
    assert view["can_submit"] is False and view["blocked_reason"] == "attempts_exhausted"
    support = as_role("customer_support", email="support@example.org")
    with seeded.app_context():
        enrollment_id = db.session.scalar(select(CourseEnrollment.id))
    granted = support.post(
        f"{_base(course, assignment)}/exceptions",
        {"enrollment_id": enrollment_id, "extra_attempts": 1, "reason": "Illness"},
    )
    assert granted.status_code == 201
    assert learner.get(_learn_url(assignment)).get_json()["data"]["can_submit"] is True
    _submit(learner, assignment, ESSAY + " third")


def test_failed_grade_without_resubmission_policy_is_final(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor, resubmission_policy="on_request")
    learner = _learner(seeded)
    _submit(learner, assignment)
    _grade_and_release(editor, course, assignment, insight=2, clarity=1)
    view = learner.get(_learn_url(assignment)).get_json()["data"]
    assert (
        view["submission"]["status"] == "graded" and view["history"][0]["grade"]["passed"] is False
    )
    assert view["blocked_reason"] == "resubmission_not_allowed"


def test_deadlines_block_or_mark_late_and_exceptions_extend(seeded, as_role):
    editor = as_role("editor")
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    course, _, assignment = _ready(editor, due_at=past, late_policy="block")
    learner = _learner(seeded)
    url = _learn_url(assignment)
    saved = learner.put(f"{url}/draft", {"responses": {"p1": ESSAY}}).get_json()["data"]
    res = learner.post(
        f"{url}/submit", {"idempotency_key": _key(), "lock_version": saved["draft"]["lock_version"]}
    )
    assert res.status_code == 409 and res.get_json()["error"]["code"] == "deadline_passed"
    support = as_role("customer_support", email="support@example.org")
    with seeded.app_context():
        enrollment_id = db.session.scalar(select(CourseEnrollment.id))
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    support.post(
        f"{_base(course, assignment)}/exceptions",
        {"enrollment_id": enrollment_id, "due_at": future, "reason": "Approved extension"},
    )
    ok = learner.post(
        f"{url}/submit", {"idempotency_key": _key(), "lock_version": saved["draft"]["lock_version"]}
    )
    assert ok.status_code == 201 and ok.get_json()["data"]["history"][0]["is_late"] is False

    other_course, _, late_ok = _ready(editor, title="Late Course", due_at=past, late_policy="allow")
    late_learner = _learner(seeded, slug="late-course", email="late@example.com")
    data = _submit(late_learner, late_ok, slug="late-course")
    assert data["history"][0]["is_late"] is True


# ---- completion and certificates --------------------------------------------------------------------


def test_required_assignment_gates_completion_and_certificate(seeded, as_role):
    editor = as_role("editor")
    course, lessons, _ = _setup(editor)  # assignment still a draft
    early = _learner(seeded, email="early@example.com")
    assert (
        early.post(f"{LEARN}/writing-course/lessons/{lessons[0]['slug']}/complete").status_code
        == 200
    )
    assert early.get(f"{LEARN}/writing-course").get_json()["data"]["completed_at"]
    assignment = editor.get(f"{COURSES}/{course['id']}/assignments").get_json()["data"][0]
    _rubric(editor, course, assignment)
    _publish(editor, course, assignment)
    # Completed before the assignment was required: completion and certificate are kept.
    card = early.get(f"{LEARN}/writing-course").get_json()["data"]
    assert card["completed_at"] and card["certificate"]

    learner = _learner(seeded)
    learner.post(f"{LEARN}/writing-course/lessons/{lessons[0]['slug']}/complete")
    state = learner.get(f"{LEARN}/writing-course").get_json()["data"]
    assert state["completed_at"] is None and state["progress"]["required_assignments"] == 1
    assert (
        learner.post(f"{LEARN}/writing-course/certificate", {"name": "Writer"}).status_code == 409
    )
    _submit(learner, assignment)
    assert (
        learner.get(f"{LEARN}/writing-course").get_json()["data"]["completed_at"] is None
    )  # ungraded
    _grade_and_release(editor, course, assignment)
    state = learner.get(f"{LEARN}/writing-course").get_json()["data"]
    assert state["completed_at"] and state["progress"]["completed_assignments"] == 1
    code = state["certificate"]["code"]
    again = learner.post(f"{LEARN}/writing-course/certificate", {"name": "Writer"})
    assert again.get_json()["data"]["code"] == code
    with seeded.app_context():
        assert db.session.scalar(select(db.func.count(CourseCertificate.id))) == 2


def test_failing_grade_does_not_complete_the_course(seeded, as_role):
    editor = as_role("editor")
    course, lessons, assignment = _ready(editor)
    learner = _learner(seeded)
    learner.post(f"{LEARN}/writing-course/lessons/{lessons[0]['slug']}/complete")
    _submit(learner, assignment)
    _grade_and_release(editor, course, assignment, insight=3, clarity=2)
    assert learner.get(f"{LEARN}/writing-course").get_json()["data"]["completed_at"] is None


# ---- access, privacy, export and deletion --------------------------------------------------------------


def test_revoked_access_blocks_all_learner_operations(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    url = _learn_url(assignment)
    learner.put(f"{url}/draft", {"responses": {"p1": ESSAY}})
    file = _upload(learner, assignment, minimal_pdf(), "a.pdf").get_json()["data"]["draft"][
        "files"
    ][0]
    support = as_role("customer_support", email="support@example.org")
    enrollment = support.get(f"{COURSES}/{course['id']}/enrollments").get_json()["data"][0]
    support.post(
        f"{COURSES}/{course['id']}/enrollments/{enrollment['id']}/revoke", {"reason": "Refunded"}
    )
    assert learner.get(url).status_code == 403
    assert learner.put(f"{url}/draft", {"responses": {"p1": "x"}}).status_code == 403
    assert (
        learner.post(f"{url}/submit", {"idempotency_key": _key(), "lock_version": 2}).status_code
        == 403
    )
    assert _upload(learner, assignment, minimal_pdf(), "b.pdf").status_code == 403
    assert learner.get(f"/api/v1/account/assignment-files/{file['id']}/download").status_code == 403


def test_privacy_between_learners_export_and_account_deletion(seeded, as_role, app):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    other = _learner(seeded, email="other@example.com")
    _upload(learner, assignment, minimal_pdf(), "mine.pdf")
    _submit(learner, assignment, ESSAY + " private words")
    assert other.get(_learn_url(assignment)).get_json()["data"]["submission"] is None
    assert "private words" not in other.get(_learn_url(assignment)).get_data(as_text=True)
    _grade_and_release(editor, course, assignment)

    exported = learner.post("/api/v1/account/export", {"password": PASSWORD}).get_json()["data"]
    work = exported["assignments"][0]
    assert "private words" in work["attempts"][0]["responses"]["p1"]
    assert work["attempts"][0]["grade"]["feedback"] == "Thoughtful work."
    assert "Staff only" not in str(exported)

    with app.app_context():
        key = db.session.scalar(select(AssignmentFile.storage_key))
    path = Path(app.config["PRODUCT_FILES_ROOT"]).resolve() / key
    assert path.is_file()
    assert learner.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    with app.app_context():
        attempt = db.session.scalar(select(AssignmentAttempt))
        grade = db.session.scalar(select(AssignmentGrade))
        assert attempt.responses == {} and grade.feedback == "" and grade.private_notes == ""
        assert grade.percent == 80  # scores kept without content
        assert db.session.scalar(select(db.func.count(AssignmentFile.id))) == 0
    assert not path.exists()


def test_reports_count_statuses_and_pass_rate(seeded, as_role):
    editor = as_role("editor")
    course, _, assignment = _ready(editor)
    learner = _learner(seeded)
    _submit(learner, assignment)
    _grade_and_release(editor, course, assignment)
    data = editor.get(f"{_base(course, assignment)}/report").get_json()["data"]
    assert data["submissions"] == 1 and data["by_status"] == {"completed": 1}
    assert data["pass_rate"] == 100 and data["average_percent"] == 80
