"""Batch 11.3: learning analytics from existing LMS records (aggregates only)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Assessment,
    AssessmentAttempt,
    AssignmentAttempt,
    AssignmentGrade,
    AssignmentSubmission,
    Course,
    CourseAssignment,
    CourseEnrollment,
    CourseLesson,
    CourseModule,
    Customer,
    LessonProgress,
)

URL = "/api/v1/admin/analytics/learning"
NOW = datetime.now(UTC)
D1 = NOW - timedelta(days=5)
D2 = NOW - timedelta(days=2)
OLD = NOW - timedelta(days=200)


def _customer(i):
    c = Customer(
        public_id=secrets.token_hex(8),
        email=f"learner{i}@example.com",
        display_name=f"Learner {i}",
        status="active",
        is_test_account=False,
        support_notes="",
        email_verified_at=NOW,
    )
    db.session.add(c)
    db.session.flush()
    return c


@pytest.fixture()
def lms(seeded):
    with seeded.app_context():
        course = Course(
            public_id=secrets.token_hex(8),
            slug="calm-analytics",
            title="Calm Analytics",
            status="published",
        )
        db.session.add(course)
        db.session.flush()
        module = CourseModule(course_id=course.id, title="Module 1", position=1)
        db.session.add(module)
        db.session.flush()
        lessons = []
        for n in range(1, 4):
            lesson = CourseLesson(
                course_id=course.id,
                module_id=module.id,
                slug=f"l{n}",
                title=f"Lesson {n}",
                position=n,
                status="published",
            )
            db.session.add(lesson)
            lessons.append(lesson)
        db.session.flush()
        learners = [_customer(i) for i in range(6)]

        def enroll(c, source, at, *, status="active", completed=None, progress=0):
            e = CourseEnrollment(
                customer_id=c.id,
                course_id=course.id,
                source=source,
                status=status,
                enrolled_at=at,
                completed_at=completed,
                progress_percent=progress,
            )
            db.session.add(e)
            db.session.flush()
            return e

        e0 = enroll(learners[0], "purchase", D1, completed=D2, progress=100)  # finished
        e1 = enroll(learners[1], "membership", D1, progress=33)  # stopped after lesson 1
        e2 = enroll(learners[2], "free", D2, progress=66)  # stopped after lesson 2
        enroll(learners[3], "free", D2)  # never started
        e4 = enroll(learners[4], "purchase", OLD, status="revoked", progress=33)  # revoked
        enroll(learners[5], "manual", OLD, completed=OLD, progress=100)  # old completion

        def view(e, upto, at):
            for lesson in lessons[:upto]:
                db.session.add(
                    LessonProgress(
                        enrollment_id=e.id,
                        lesson_id=lesson.id,
                        first_viewed_at=at,
                        last_viewed_at=at,
                        completed_at=at,
                    )
                )

        view(e0, 3, D1)
        view(e1, 1, D1)
        view(e2, 2, D2)
        view(e4, 1, OLD)
        db.session.add(
            LessonProgress(
                enrollment_id=e2.id, lesson_id=lessons[2].id, first_viewed_at=D2, last_viewed_at=D2
            )
        )

        quiz = Assessment(
            course_id=course.id,
            title="Final quiz",
            kind="quiz",
            status="published",
            position=1,
            passing_score=70,
        )
        timed = Assessment(
            course_id=course.id,
            title="Timed exam",
            kind="quiz",
            status="published",
            position=2,
            time_limit_minutes=20,
        )
        practice = Assessment(
            course_id=course.id,
            title="Practice",
            kind="quiz",
            status="published",
            position=3,
            practice=True,
        )
        reflect = Assessment(
            course_id=course.id,
            title="Reflection",
            kind="reflection",
            status="published",
            position=4,
        )
        db.session.add_all([quiz, timed, practice, reflect])
        db.session.flush()

        def attempt(a, e, n, percent, passed, at, status="submitted"):
            db.session.add(
                AssessmentAttempt(
                    assessment_id=a.id,
                    enrollment_id=e.id,
                    attempt_number=n,
                    percent=percent,
                    passed=passed,
                    submitted_at=at if status == "submitted" else None,
                    started_at=at,
                    status=status,
                    answers={"q1": "secret answer"},
                )
            )

        attempt(quiz, e0, 1, 50, False, D1)
        attempt(quiz, e0, 2, 90, True, D2)  # retake: same learner, best = 90
        attempt(quiz, e1, 1, 60, False, D2)
        attempt(timed, e2, 1, 80, True, D2)
        attempt(timed, e1, 1, None, None, D2, status="expired")
        attempt(practice, e1, 1, 40, False, D2)
        attempt(reflect, e2, 1, None, None, D2)
        attempt(quiz, e0, 3, 100, True, OLD)  # out of range

        assignment = CourseAssignment(
            public_id=secrets.token_hex(8),
            course_id=course.id,
            title="Essay",
            position=1,
            status="published",
        )
        db.session.add(assignment)
        db.session.flush()

        def submit(e, status, at, *, late=False, grade=None):
            s = AssignmentSubmission(
                public_id=secrets.token_hex(8),
                assignment_id=assignment.id,
                enrollment_id=e.id,
                customer_id=e.customer_id,
                status=status,
            )
            db.session.add(s)
            db.session.flush()
            att = AssignmentAttempt(
                public_id=secrets.token_hex(8),
                submission_id=s.id,
                number=1,
                status="submitted",
                submitted_at=at,
                is_late=late,
                responses={"p1": "private essay text"},
            )
            db.session.add(att)
            db.session.flush()
            if grade:
                db.session.add(
                    AssignmentGrade(
                        attempt_id=att.id,
                        status="published",
                        published_at=at,
                        feedback="private feedback",
                        private_notes="secret notes",
                        **grade,
                    )
                )

        submit(e0, "graded", D1, grade={"percent": 85, "passed": True, "outcome": "graded"})
        submit(
            e1,
            "changes_requested",
            D2,
            late=True,
            grade={"percent": 40, "passed": False, "outcome": "changes_requested"},
        )
        submit(e2, "pending_review", D2)
        db.session.commit()
        ids = {
            "course": course.id,
            "lessons": [lesson.id for lesson in lessons],
            "e0": e0.id,
            "e4": e4.id,
        }
    return seeded, ids


def _get(api, **params):
    res = api.get(URL, query_string={"range": "30d", **params})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def test_enrollments_starts_completions_and_access(lms, as_role):
    _app, ids = lms
    data = _get(as_role("administrator"), course=ids["course"])
    cur = data["current"]
    assert (cur["enrollments"], cur["revoked"]) == (5, 1)
    # The old manual completion has no lesson views but counts as started.
    assert (cur["started"], cur["completed"], cur["unfinished"], cur["not_started"]) == (4, 2, 2, 1)
    assert cur["completion_rate"] == 40.0 and cur["completion_rate_of_started"] == 50.0
    assert cur["average_progress"] == round((100 + 33 + 66 + 0 + 100) / 5, 1)
    assert cur["by_access"] == {"free": 2, "purchase": 1, "membership": 1, "manual": 1}
    per = data["period"]
    assert (per["new_enrollments"], per["starts"], per["completions"]) == (4, 3, 1)
    assert per["new_by_access"]["free"] == 2
    assert per["active_learners"] == 3  # e0, e1, e2; e3 never did anything
    assert sum(t["enrollments"] for t in data["trend"]) == 4
    [row] = data["courses"]
    assert (
        row["enrollments"],
        row["started"],
        row["completed"],
        row["assignment_submissions"],
    ) == (5, 4, 2, 3)
    assert row["assessment_participants"] == 3
    assert row["average_best_score"] == round(
        (100 + 60 + 80) / 3, 1
    )  # best per learner (all time), no practice


def test_duplicate_enrollments_are_impossible(lms):
    app, ids = lms
    with app.app_context():
        e = db.session.get(CourseEnrollment, ids["e0"])
        db.session.add(
            CourseEnrollment(customer_id=e.customer_id, course_id=e.course_id, source="free")
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_lesson_progress_and_dropout_points(lms, as_role):
    _app, ids = lms
    lessons = _get(as_role("administrator"), course=ids["course"])["lessons"]
    assert lessons["started_learners"] == 4
    items = lessons["items"]
    assert [i["viewed"] for i in items] == [3, 2, 2]
    assert [i["completed"] for i in items] == [3, 2, 1]
    assert [i["unfinished_stopped_here"] for i in items] == [1, 1, 0]
    assert items[2]["completion_rate_of_started"] == 25.0  # 1 of 4 started learners


def test_assessments_respect_types_and_retakes(lms, as_role):
    _app, ids = lms
    a = _get(as_role("administrator"), course=ids["course"])["assessments"]["by_type"]
    assert (
        a["quiz"]["attempts"],
        a["quiz"]["participants"],
        a["quiz"]["passed"],
        a["quiz"]["failed"],
    ) == (3, 2, 1, 2)
    assert a["quiz"]["average_percent"] == round((50 + 90 + 60) / 3, 1)
    assert (a["timed"]["attempts"], a["timed"]["expired"], a["timed"]["passed"]) == (1, 1, 1)
    assert (a["practice"]["attempts"], a["practice"]["passed"], a["practice"]["failed"]) == (
        1,
        0,
        1,
    )
    assert a["ungraded"]["attempts"] == 1 and a["ungraded"]["pass_rate"] is None


def test_assignments_and_grading_workload(lms, as_role):
    _app, ids = lms
    s = _get(as_role("administrator"), course=ids["course"])["assignments"]
    assert (s["submitted"], s["submitted_late"], s["graded"]) == (3, 1, 2)
    assert (s["passed"], s["failed"], s["average_percent"]) == (1, 1, 62.5)
    assert s["changes_requested_in_range"] == 1
    assert (s["pending_grading"], s["awaiting_resubmission"], s["completed_or_graded"]) == (1, 1, 1)


def test_date_filters_and_empty_ranges(lms, as_role):
    _app, ids = lms
    api = as_role("administrator")
    day = D2.date().isoformat()
    only_d2 = _get(api, course=ids["course"], date_from=day, date_to=day)
    assert only_d2["period"]["new_enrollments"] == 2 and only_d2["period"]["completions"] == 1
    assert only_d2["assessments"]["by_type"]["quiz"]["attempts"] == 2
    old = OLD.date().isoformat()
    past = _get(api, course=ids["course"], date_from=old, date_to=old)
    assert (
        past["period"]["completions"] == 1
        and past["assessments"]["by_type"]["quiz"]["attempts"] == 1
    )
    empty = _get(api, course=ids["course"], date_from="2020-01-01", date_to="2020-01-31")
    assert empty["period"] == {
        "new_enrollments": 0,
        "new_by_access": {"free": 0, "purchase": 0, "membership": 0, "manual": 0},
        "starts": 0,
        "completions": 0,
        "active_learners": 0,
    }
    assert api.get(URL, query_string={"course": "abc"}).status_code == 400
    assert api.get(URL, query_string={"course": 999999}).status_code == 404


def test_permissions_and_privacy(lms, as_role, client):
    _app, ids = lms
    assert client.get(URL).status_code == 401
    assert as_role("seo_manager").get(URL).status_code == 403  # analytics only, no learning reports
    marketing = _get(
        as_role("marketing_manager"), course=ids["course"]
    )  # course reports, no assignment reports
    assert marketing["assignments"]["available"] is False
    analyst = _get(as_role("analyst"), course=ids["course"])
    assert analyst["assignments"]["available"] is True
    text = str(analyst)
    for private in (
        "learner0@example.com",
        "Learner 0",
        "secret answer",
        "private essay",
        "private feedback",
        "secret notes",
    ):
        assert private not in text
