"""Batch 09.2 phase 2: reusable question banks, practice exams, random draws, timed and
untimed started attempts, deadlines, attempt limits, answer-key secrecy, deterministic
snapshots, assessment history and preservation of existing attempts and completion."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import Assessment, AssessmentAttempt, PermissionDefinition, Role

from .conftest import PASSWORD, Api, login, make_user, register_customer
from .test_courses_admin import COURSES, ready_course

LEARN = "/api/v1/account/learning"
BANKS = "/api/v1/admin/question-banks"


def _bank(editor, title="Breathing basics", *, breath=3, sleep=2):
    bank = editor.post(BANKS, {"title": title, "description": "Shared quiz questions"})
    assert bank.status_code == 201, bank.get_json()
    bank = bank.get_json()["data"]
    made = []
    for i in range(breath + sleep):
        tag = "breath" if i < breath else "sleep"
        res = editor.post(
            f"{BANKS}/{bank['id']}/questions",
            {
                "kind": "single_choice",
                "prompt": f"{tag.title()} question {i + 1}?",
                "options": [{"id": "a", "text": "Wrong"}, {"id": "b", "text": "Right"}],
                "correct": ["b"],
                "explanation": f"Secret explanation {i + 1}.",
                "tags": [tag.upper()],
            },
        )
        assert res.status_code == 201, res.get_json()
        made.append(res.get_json()["data"])
    return bank, made


def _learner(app, slug, email="reader@example.com"):
    learner = register_customer(app, email, verify=True)
    assert learner.post(f"{LEARN}/{slug}/enroll").status_code in (200, 201)
    return learner


def _quiz(editor, course, **fields):
    payload = {"title": "Practice exam", "kind": "quiz", "passing_score": 50, **fields}
    res = editor.post(f"{COURSES}/{course['id']}/assessments", payload)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _publish(editor, course, quiz):
    return editor.post(
        f"{COURSES}/{course['id']}/assessments/{quiz['id']}/status", {"status": "published"}
    )


def _custom_user(app, email, keys):
    with app.app_context():
        perms = db.session.scalars(
            select(PermissionDefinition).where(PermissionDefinition.key.in_(keys))
        ).all()
        name = email.split("@")[0].replace(".", "_")
        db.session.add(Role(name=name, label=name, kind="custom", permissions=perms))
        db.session.commit()
    make_user(app, email, [name])
    client = app.test_client()
    assert login(client, email, PASSWORD).status_code == 200
    return Api(client)


# ---- banks: permissions and answer-key secrecy --------------------------------------------------


def test_bank_permissions_and_answer_key_secrecy(seeded, as_role, app):
    editor = as_role("editor")
    bank, questions = _bank(editor)
    assert questions[0]["tags"] == ["breath"] and questions[0]["correct"] == ["b"]

    for role in ("analyst", "customer_support"):
        api = as_role(role)
        assert api.get(BANKS).status_code == 403
        assert api.post(BANKS, {"title": "Nope"}).status_code == 403

    viewer = _custom_user(app, "bank.viewer@example.org", ["question_banks.view"])
    listed = viewer.get(BANKS).get_json()["data"]
    assert [b["id"] for b in listed] == [bank["id"]]
    assert listed[0]["question_counts"] == {"active": 5, "retired": 0}
    raw = viewer.get(f"{BANKS}/{bank['id']}/questions").get_data(as_text=True)
    assert "Secret explanation" not in raw and '"correct"' not in raw
    assert viewer.get(f"{BANKS}/{bank['id']}").get_json()["data"]["answer_key_visible"] is False
    # Viewing isn't managing.
    assert viewer.post(BANKS, {"title": "Mine"}).status_code == 403
    assert (
        viewer.patch(
            f"{BANKS}/{bank['id']}/questions/{questions[0]['id']}",
            {"prompt": "Changed?", "lock_version": questions[0]["lock_version"]},
        ).status_code
        == 403
    )

    managed = editor.get(f"{BANKS}/{bank['id']}/questions?tag=sleep").get_json()
    assert managed["meta"]["total"] == 2 and managed["data"][0]["correct"] == ["b"]

    # Validation reuses the assessment question rules; edits need the current version.
    bad = editor.post(
        f"{BANKS}/{bank['id']}/questions",
        {"kind": "single_choice", "prompt": "?", "options": [{"id": "a", "text": "x"}]},
    )
    assert bad.status_code == 400
    stale = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{questions[0]['id']}",
        {"prompt": "Changed?", "lock_version": 99},
    )
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "edit_conflict"
    edited = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{questions[0]['id']}",
        {"prompt": "Changed?", "lock_version": questions[0]["lock_version"]},
    ).get_json()["data"]
    assert edited["version"] == 2
    tagged = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{questions[0]['id']}",
        {"tags": ["breath", "intro"], "lock_version": edited["lock_version"]},
    ).get_json()["data"]
    assert tagged["version"] == 2  # tags don't change the question itself


# ---- practice exams with random draws ----------------------------------------------------------


def test_practice_exam_draws_snapshot_and_history(seeded, as_role, app):
    editor = as_role("editor")
    bank, questions = _bank(editor)
    course, _, lessons = ready_course(editor, "Practice Course", lessons=1)
    quiz = _quiz(
        editor,
        course,
        practice=True,
        max_attempts=2,
        show_answers="after_submit",
        selection=[{"bank_id": bank["id"], "count": 2, "tags": ["breath"]}],
        shuffle_options=True,
    )
    assert quiz["practice"] is True and quiz["required_for_completion"] is False
    assert quiz["requires_start"] is True and quiz["drawn_question_count"] == 2
    assert _publish(editor, course, quiz).status_code == 200

    learner = _learner(seeded, "practice-course")
    url = f"{LEARN}/practice-course/assessments/{quiz['id']}"
    view = learner.get(url)
    data = view.get_json()["data"]["assessment"]
    assert data["questions"] == [] and data["question_count"] == 2 and data["practice"] is True
    assert "Secret explanation" not in view.get_data(as_text=True)

    # Drawn assessments can't be answered in one step.
    one_shot = learner.post(f"{url}/attempts", {"answers": {}})
    assert one_shot.status_code == 409
    assert one_shot.get_json()["error"]["code"] == "attempt_not_started"

    started = learner.post(f"{url}/attempts/start")
    assert started.status_code == 201
    raw = started.get_data(as_text=True)
    assert "Secret explanation" not in raw and '"correct"' not in raw
    attempt = started.get_json()["data"]["attempt"]
    assert attempt["status"] == "in_progress" and attempt["deadline_at"] is None
    drawn = attempt["questions"]
    assert len(drawn) == 2 and all(q["id"].startswith("b") for q in drawn)
    assert all(q["prompt"].startswith("Breath") for q in drawn)
    # Starting again returns the open attempt (idempotent).
    again = learner.post(f"{url}/attempts/start")
    assert again.status_code == 200 and again.get_json()["data"]["attempt"]["id"] == attempt["id"]

    # Editing the bank after the start doesn't change this attempt.
    by_prompt = {q["prompt"]: q for q in questions}
    first = by_prompt[drawn[0]["prompt"]]
    res = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{first['id']}",
        {"prompt": "Rewritten?", "correct": ["a"], "lock_version": first["lock_version"]},
    )
    assert res.status_code == 200 and res.get_json()["data"]["version"] == 2
    detail = learner.get(f"{url}/attempts/{attempt['id']}").get_json()["data"]["attempt"]
    assert [q["prompt"] for q in detail["questions"]] == [q["prompt"] for q in drawn]

    # Autosave: validated against the snapshot, merged, null clears.
    put = f"{url}/attempts/{attempt['id']}"
    assert learner.put(put, {"answers": {drawn[0]["id"]: "zzz"}}).status_code == 400
    assert learner.put(put, {"answers": {"b999999": "a"}}).status_code == 400
    saved = learner.put(put, {"answers": {drawn[0]["id"]: "a"}}).get_json()["data"]["attempt"]
    assert saved["answers"] == {drawn[0]["id"]: "a"}
    saved = learner.put(put, {"answers": {drawn[0]["id"]: "b", drawn[1]["id"]: "b"}})
    assert saved.get_json()["data"]["attempt"]["answers"] == {
        drawn[0]["id"]: "b",
        drawn[1]["id"]: "b",
    }

    done = learner.post(f"{put}/submit", {})
    assert done.status_code == 200
    result = done.get_json()["data"]["attempt"]
    # Scored against the snapshot's key ("b"), not the edited bank key ("a").
    assert result["status"] == "submitted" and result["percent"] == 100 and result["passed"]
    assert result["practice"] is True and result["answers_revealed"] is True
    assert result["results"][0]["explanation"].startswith("Secret explanation")
    assert result["results"][0]["prompt"] == drawn[0]["prompt"]
    # Submitted attempts are closed.
    closed = learner.post(f"{put}/submit", {})
    assert closed.status_code == 409 and closed.get_json()["error"]["code"] == "attempt_closed"
    assert learner.put(put, {"answers": {}}).status_code == 409

    # Practice exams never count towards completion.
    progress = done.get_json()["data"]["progress"]
    assert progress["required_assessments"] == 0 and progress["complete"] is False
    learner.post(f"{LEARN}/practice-course/lessons/{lessons[0]['slug']}/complete")
    assert learner.get(f"{LEARN}/practice-course").get_json()["data"]["progress"]["complete"]

    # Attempt limits count started attempts.
    second = learner.post(f"{url}/attempts/start").get_json()["data"]["attempt"]
    assert second["id"] != attempt["id"]
    exhausted = learner.post(f"{url}/attempts/start")
    assert exhausted.status_code == 200  # the second attempt is still open
    answers = {q["id"]: "a" for q in second["questions"]}
    res = learner.post(f"{url}/attempts/{second['id']}/submit", {"answers": answers})
    # A new attempt draws from the bank as it is now (the edited key may apply).
    assert res.status_code == 200 and res.get_json()["data"]["attempt"]["status"] == "submitted"
    exhausted = learner.post(f"{url}/attempts/start")
    assert exhausted.status_code == 409
    assert exhausted.get_json()["error"]["code"] == "attempts_exhausted"

    history = learner.get(f"{url}/history").get_json()["data"]["assessments"][0]
    assert history["attempts_used"] == 2 and history["best_percent"] == 100
    assert [a["attempt_number"] for a in history["attempts"]] == [2, 1]
    course_history = learner.get(f"{LEARN}/practice-course/assessment-history").get_json()
    assert [a["assessment_id"] for a in course_history["data"]["assessments"]] == [quiz["id"]]

    # Another learner can't read this learner's attempt.
    other = _learner(seeded, "practice-course", "other@example.com")
    assert other.get(f"{url}/attempts/{attempt['id']}").status_code == 404
    assert other.put(put, {"answers": {}}).status_code == 404

    # Staff with enrolment access see scores and timing (no answers).
    staff_url = f"{COURSES}/{course['id']}/assessments/{quiz['id']}/attempts"
    assert editor.get(staff_url).status_code == 403
    rows = as_role("administrator").get(staff_url).get_json()["data"]
    assert len(rows) == 2 and "answers" not in rows[0] and rows[0]["learner"]


def test_snapshot_is_deterministic_for_a_seed(seeded, as_role, app):
    editor = as_role("editor")
    bank, _ = _bank(editor, breath=6, sleep=0)
    course, _, _ = ready_course(editor, "Seed Course", lessons=1)
    quiz = _quiz(
        editor,
        course,
        selection=[{"bank_id": bank["id"], "count": 3}],
        shuffle_questions=True,
        shuffle_options=True,
    )
    from app.services.courses import assessments

    with app.app_context():
        assessment = db.session.get(Assessment, quiz["id"])
        one = assessments.build_snapshot(assessment, 1234)
        two = assessments.build_snapshot(assessment, 1234)
        assert one == two and len(one["questions"]) == 3
        assert len({q["id"] for q in one["questions"]}) == 3  # never the same question twice
        assert one["questions"][0]["source"]["type"] == "bank"
        seeds = {
            tuple(q["id"] for q in assessments.build_snapshot(assessment, s)["questions"])
            for s in random.Random(7).sample(range(10**6), 8)
        }
        assert len(seeds) > 1  # different attempts draw differently


# ---- timed attempts and deadlines --------------------------------------------------------------


def _timed_course(editor):
    course, _, lessons = ready_course(editor, "Timed Course", lessons=1)
    quiz = _quiz(editor, course, title="Final exam", time_limit_minutes=10, passing_score=60)
    qurl = f"{COURSES}/{course['id']}/assessments/{quiz['id']}/questions"
    for i in range(2):
        res = editor.post(
            qurl,
            {
                "kind": "true_false",
                "prompt": f"Statement {i + 1}.",
                "correct": [True],
                "explanation": "Hidden until submitted.",
            },
        )
        assert res.status_code == 201
    assert _publish(editor, course, quiz).status_code == 200
    return course, quiz, lessons


def _expire(app, attempt_id, seconds=120):
    with app.app_context():
        row = db.session.get(AssessmentAttempt, attempt_id)
        row.deadline_at = datetime.now(UTC) - timedelta(seconds=seconds)
        db.session.commit()


def test_timed_attempt_deadline_scores_only_saved_answers(seeded, as_role, app):
    editor = as_role("editor")
    course, quiz, lessons = _timed_course(editor)
    learner = _learner(seeded, "timed-course")
    url = f"{LEARN}/timed-course/assessments/{quiz['id']}"
    view = learner.get(url).get_json()["data"]["assessment"]
    assert view["questions"] == [] and view["time_limit_minutes"] == 10
    attempt = learner.post(f"{url}/attempts/start").get_json()["data"]["attempt"]
    assert attempt["deadline_at"] and 590 <= attempt["seconds_left"] <= 600
    assert "Hidden until submitted." not in str(attempt)
    first, second = (str(q["id"]) for q in attempt["questions"])

    put = f"{url}/attempts/{attempt['id']}"
    # Required questions are enforced on submit, not on autosave.
    assert learner.put(put, {"answers": {first: "true"}}).status_code == 200
    missing = learner.post(f"{put}/submit", {})
    assert missing.status_code == 400

    _expire(app, attempt["id"])
    late = learner.put(put, {"answers": {second: "true"}})
    assert late.status_code == 409 and late.get_json()["error"]["code"] == "attempt_expired"
    # Submitting late scores only what was saved in time.
    done = learner.post(f"{put}/submit", {"answers": {second: "true"}}).get_json()["data"]
    result = done["attempt"]
    assert result["status"] == "expired" and result["score"] == 1 and result["max_score"] == 2
    assert result["percent"] == 50 and result["passed"] is False
    assert done["assessment"]["status"] == "failed"

    # Within the deadline the attempt is scored normally; it then counts for completion.
    attempt = learner.post(f"{url}/attempts/start").get_json()["data"]["attempt"]
    ids = [str(q["id"]) for q in attempt["questions"]]
    learner.post(f"{LEARN}/timed-course/lessons/{lessons[0]['slug']}/complete")
    ok = learner.post(
        f"{url}/attempts/{attempt['id']}/submit", {"answers": dict.fromkeys(ids, "true")}
    ).get_json()["data"]
    assert ok["attempt"]["status"] == "submitted" and ok["attempt"]["passed"] is True
    assert ok["progress"]["complete"] is True


def test_overdue_attempts_expire_when_the_learner_returns(seeded, as_role, app):
    editor = as_role("editor")
    course, quiz, _ = _timed_course(editor)
    learner = _learner(seeded, "timed-course")
    url = f"{LEARN}/timed-course/assessments/{quiz['id']}"
    attempt = learner.post(f"{url}/attempts/start").get_json()["data"]["attempt"]
    learner.put(
        f"{url}/attempts/{attempt['id']}",
        {"answers": {str(q["id"]): "true" for q in attempt["questions"]}},
    )
    # Inside the grace period the attempt is still open.
    _expire(app, attempt["id"], seconds=5)
    view = learner.get(url).get_json()["data"]["assessment"]
    assert view["in_progress"]["id"] == attempt["id"]
    _expire(app, attempt["id"])
    view = learner.get(url).get_json()["data"]["assessment"]
    assert view["in_progress"] is None and view["status"] == "passed"
    assert view["attempts"][0]["status"] == "expired" and view["attempts"][0]["percent"] == 100
    with app.app_context():
        row = db.session.get(AssessmentAttempt, attempt["id"])
        assert row.status == "expired" and row.submitted_at is not None


# ---- untimed fixed quizzes, existing attempts and completion ------------------------------------


def test_fixed_quiz_one_step_and_started_attempts_share_the_scorer(seeded, as_role, app):
    editor = as_role("editor")
    course, _, lessons = ready_course(editor, "Fixed Course", lessons=1)
    quiz = _quiz(editor, course, title="Check-in", passing_score=100)
    qurl = f"{COURSES}/{course['id']}/assessments/{quiz['id']}/questions"
    editor.post(qurl, {"kind": "true_false", "prompt": "Breathe slowly.", "correct": [True]})
    _publish(editor, course, quiz)
    learner = _learner(seeded, "fixed-course")
    url = f"{LEARN}/fixed-course/assessments/{quiz['id']}"
    view = learner.get(url).get_json()["data"]["assessment"]
    assert view["requires_start"] is False and len(view["questions"]) == 1
    qid = str(view["questions"][0]["id"])

    # The one-step submission still works and stays "submitted".
    one = learner.post(f"{url}/attempts", {"answers": {qid: "false"}}).get_json()["data"]
    assert one["attempt"]["status"] == "submitted" and one["attempt"]["passed"] is False
    # An untimed started attempt is scored the same way; the old route submits it.
    started = learner.post(f"{url}/attempts/start").get_json()["data"]["attempt"]
    assert started["deadline_at"] is None and started["seconds_left"] is None
    two = learner.post(f"{url}/attempts", {"answers": {qid: "true"}}).get_json()["data"]
    assert two["attempt"]["id"] == started["id"] and two["attempt"]["passed"] is True
    learner.post(f"{LEARN}/fixed-course/lessons/{lessons[0]['slug']}/complete")
    progress = learner.get(f"{LEARN}/fixed-course").get_json()["data"]["progress"]
    assert progress["complete"] is True and progress["required_assessments"] == 1

    # A practice exam added later doesn't change requirements or completion.
    bank, _ = _bank(editor)
    practice = _quiz(editor, course, practice=True, selection=[{"bank_id": bank["id"], "count": 1}])
    assert _publish(editor, course, practice).status_code == 200
    progress = learner.get(f"{LEARN}/fixed-course").get_json()["data"]["progress"]
    assert progress["complete"] is True and progress["required_assessments"] == 1


def test_entitlement_and_verification_are_enforced(seeded, as_role):
    editor = as_role("editor")
    course, quiz, _ = _timed_course(editor)
    url = f"{LEARN}/timed-course/assessments/{quiz['id']}"
    stranger = register_customer(seeded, "stranger@example.com", verify=True)
    res = stranger.post(f"{url}/attempts/start")
    assert res.status_code == 403 and res.get_json()["error"]["code"] == "not_enrolled"
    assert stranger.get(f"{url}/history").status_code == 403
    unverified = register_customer(seeded, "unverified@example.com", verify=False)
    res = unverified.post(f"{url}/attempts/start")
    assert res.get_json()["error"]["code"] == "email_verification_required"
    # Unpublished assessments are invisible.
    editor.post(f"{COURSES}/{course['id']}/assessments/{quiz['id']}/status", {"status": "draft"})
    learner = _learner(seeded, "timed-course")
    assert learner.post(f"{url}/attempts/start").status_code == 404


# ---- configuration rules and bank guards --------------------------------------------------------


def test_selection_validation_and_bank_guards(seeded, as_role):
    editor = as_role("editor")
    bank, questions = _bank(editor, breath=2, sleep=1)
    course, _, _ = ready_course(editor, "Guard Course", lessons=1)
    base = f"{COURSES}/{course['id']}/assessments"

    bad = [
        {"title": "R", "kind": "reflection", "selection": [{"bank_id": bank["id"], "count": 1}]},
        {"title": "Q", "selection": [{"bank_id": "missing", "count": 1}]},
        {"title": "Q", "selection": [{"bank_id": bank["id"], "count": 0}]},
        {"title": "Q", "selection": [{"bank_id": bank["id"], "count": 1, "extra": 1}]},
        {"title": "Q", "time_limit_minutes": 0},
        {"title": "Q", "practice": True, "required_for_completion": True},
        {"title": "R", "kind": "reflection", "practice": True},
    ]
    for payload in bad:
        assert editor.post(base, payload).status_code == 400, payload

    # Publishing needs enough active questions for the draws.
    short = _quiz(
        editor, course, selection=[{"bank_id": bank["id"], "count": 3, "tags": ["breath"]}]
    )
    res = _publish(editor, course, short)
    assert res.status_code == 400 and "selection" in res.get_json()["error"]["details"]
    overlap = _quiz(
        editor,
        course,
        title="Overlap",
        selection=[
            {"bank_id": bank["id"], "count": 2, "tags": ["breath"]},
            {"bank_id": bank["id"], "count": 2},
        ],
    )
    assert _publish(editor, course, overlap).status_code == 400

    quiz = _quiz(
        editor,
        course,
        title="Live",
        selection=[{"bank_id": bank["id"], "count": 2, "tags": ["breath"]}],
    )
    assert _publish(editor, course, quiz).status_code == 200

    # Changes that would break a published assessment's draws are refused.
    breath = [q for q in questions if q["tags"] == ["breath"]]
    retire = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{breath[0]['id']}",
        {"status": "retired", "lock_version": breath[0]["lock_version"]},
    )
    assert retire.status_code == 409
    assert editor.delete(f"{BANKS}/{bank['id']}/questions/{breath[0]['id']}").status_code == 409
    archive = editor.patch(f"{BANKS}/{bank['id']}", {"status": "archived", "lock_version": 1})
    assert archive.status_code == 409
    assert editor.delete(f"{BANKS}/{bank['id']}").status_code == 409
    # Questions outside the draws can be retired.
    sleep = next(q for q in questions if q["tags"] == ["sleep"])
    ok = editor.patch(
        f"{BANKS}/{bank['id']}/questions/{sleep['id']}",
        {"status": "retired", "lock_version": sleep["lock_version"]},
    )
    assert ok.status_code == 200 and ok.get_json()["data"]["status"] == "retired"

    # An unused bank can be archived (then no longer chosen) and deleted.
    spare, _ = _bank(editor, "Spare bank", breath=1, sleep=0)
    archived = editor.patch(f"{BANKS}/{spare['id']}", {"status": "archived", "lock_version": 1})
    assert archived.status_code == 200 and archived.get_json()["data"]["status"] == "archived"
    assert (
        editor.post(
            base, {"title": "Q", "selection": [{"bank_id": spare["id"], "count": 1}]}
        ).status_code
        == 400
    )
    assert editor.delete(f"{BANKS}/{spare['id']}").status_code == 200
