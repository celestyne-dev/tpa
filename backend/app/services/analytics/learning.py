"""Learning analytics (Batch 11.3): aggregates over existing LMS records only.

No new tracking: everything comes from ``course_enrollments``, ``lesson_progress``,
``assessment_attempts``, ``assignment_submissions`` / ``assignment_attempts`` /
``assignment_grades``. No learner names, emails, answers, responses, feedback or
individual grades are returned.

Definitions (also returned in ``definitions``):

- enrollment: one row per learner and course (unique), so re-enrolling never double
  counts; "current" figures exclude revoked enrollments;
- started: an enrollment with at least one lesson viewed, or completed (older/manual
  completions may have no lesson views); start time = its first lesson view, else the
  completion time; completed: ``completed_at`` set (the LMS's own completion rules);
- completion rate: completed ÷ enrolled (and ÷ started, shown separately);
- unfinished: current enrollments that started but haven't completed;
- active learners (range): distinct learners with a lesson view, lesson completion,
  assessment submission or assignment submission recorded in the range. Only the first
  and latest view of each lesson are stored, so this is a lower bound;
- assessments are split into practice, timed (time limit, not practice), standard quizzes
  and ungraded reflections/self-assessments; pass/fail and scores use submitted,
  non-practice quiz attempts; expired timed attempts are counted separately;
- assignments: attempts submitted in range, grades published in range (pass/fail and
  average of published grades), and the current grading queue.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...extensions import db
from ...models import (
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
    LessonProgress,
    User,
)
from ...utils.errors import NotFoundError, ValidationError
from ..serializers import iso
from . import reports as traffic

E = CourseEnrollment
L = LessonProgress
A = AssessmentAttempt
PENDING_REVIEW = ("pending_review", "under_review", "resubmitted")
SOURCES = ("free", "purchase", "membership", "manual")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    lo = datetime(start.year, start.month, start.day, tzinfo=UTC)
    return lo, datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)


def _day(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


def _rate(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _course_filter(args: dict[str, Any]) -> Course | None:
    raw = args.get("course")
    if not raw:
        return None
    try:
        course = db.session.get(Course, int(raw))
    except (TypeError, ValueError):
        raise ValidationError(details={"course": ["Choose a course."]}) from None
    if course is None:
        raise NotFoundError("Course not found.")
    return course


def _first_views(enrollment_ids=None, course=None) -> dict[int, datetime]:
    """Enrollment id -> first lesson view (the "started" moment)."""
    stmt = select(L.enrollment_id, func.min(L.first_viewed_at)).group_by(L.enrollment_id)
    if course is not None:
        stmt = stmt.join(E, E.id == L.enrollment_id).where(E.course_id == course.id)
    return dict(db.session.execute(stmt).all())


def _population(course: Course | None):
    """All enrollments in scope with their start moments (independent of the range)."""
    scope = [E.course_id == course.id] if course else []
    enrollments = db.session.execute(
        select(
            E.id,
            E.course_id,
            E.customer_id,
            E.source,
            E.status,
            E.enrolled_at,
            E.completed_at,
            E.progress_percent,
        ).where(*scope)
    ).all()
    first_view = _first_views(course=course)
    for e in enrollments:  # completed without recorded lesson views: started at completion
        if e.id not in first_view and e.completed_at is not None:
            first_view[e.id] = e.completed_at
    return enrollments, first_view


def _current_figures(enrollments, first_view) -> dict[str, Any]:
    current = [e for e in enrollments if e.status == "active"]
    started = [e for e in current if e.id in first_view]
    completed = [e for e in current if e.completed_at is not None]
    unfinished = [e for e in started if e.completed_at is None]
    return {
        "enrollments": len(current),
        "revoked": len(enrollments) - len(current),
        "started": len(started),
        "completed": len(completed),
        "unfinished": len(unfinished),
        "not_started": len(current) - len(started),
        "completion_rate": _rate(len(completed), len(current)),
        "completion_rate_of_started": _rate(len(completed), len(started)),
        "average_progress": round(sum(e.progress_percent for e in current) / len(current), 1)
        if current
        else None,
        "by_access": {s: sum(1 for e in current if e.source == s) for s in SOURCES},
    }


def _period_figures(enrollments, first_view, scope, lo, hi):
    """Range figures plus the matching enrollment rows (for trends)."""

    def in_range(when):
        if when is None:
            return False
        return lo <= (when if when.tzinfo else when.replace(tzinfo=UTC)) < hi

    new = [e for e in enrollments if in_range(e.enrolled_at)]
    starts = [e for e in enrollments if in_range(first_view.get(e.id))]
    completions = [e for e in enrollments if in_range(e.completed_at)]

    # Active learners in range (lower bound; see module docstring).
    enrollment_scope = select(E.id).where(*scope)
    active_ids: set[int] = set()
    for column in (L.first_viewed_at, L.last_viewed_at, L.completed_at):
        active_ids |= set(
            db.session.scalars(
                select(L.enrollment_id).where(
                    column >= lo, column < hi, L.enrollment_id.in_(enrollment_scope)
                )
            )
        )
    active_ids |= set(
        db.session.scalars(
            select(A.enrollment_id).where(
                A.submitted_at >= lo, A.submitted_at < hi, A.enrollment_id.in_(enrollment_scope)
            )
        )
    )
    active_ids |= set(
        db.session.scalars(
            select(AssignmentSubmission.enrollment_id)
            .join(AssignmentAttempt, AssignmentAttempt.submission_id == AssignmentSubmission.id)
            .where(
                AssignmentAttempt.submitted_at >= lo,
                AssignmentAttempt.submitted_at < hi,
                AssignmentSubmission.enrollment_id.in_(enrollment_scope),
            )
        )
    )
    learner_of = {e.id: e.customer_id for e in enrollments}
    period = {
        "new_enrollments": len(new),
        "new_by_access": {s: sum(1 for e in new if e.source == s) for s in SOURCES},
        "starts": len(starts),
        "completions": len(completions),
        "active_learners": len({learner_of[i] for i in active_ids if i in learner_of}),
    }
    return period, new, starts, completions


def learning_summary(ranges: list[dict[str, Any]]) -> dict[str, Any]:
    """Current figures and the period figures for each range, from one load of the
    enrollments (all courses). Same definitions as ``learning_report``; used by the
    unified overview."""
    enrollments, first_view = _population(None)
    periods = []
    for args in ranges:
        start, end, _g = traffic.resolve_range(args)
        lo, hi = _bounds(start, end)
        periods.append(_period_figures(enrollments, first_view, [], lo, hi)[0])
    return {"current": _current_figures(enrollments, first_view), "periods": periods}


def learning_report(args: dict[str, Any], actor: User) -> dict[str, Any]:
    start, end, granularity = traffic.resolve_range(args)
    course = _course_filter(args)
    lo, hi = _bounds(start, end)
    scope = [E.course_id == course.id] if course else []

    enrollments, first_view = _population(course)
    period, new, starts, completions = _period_figures(enrollments, first_view, scope, lo, hi)

    # Trends.
    buckets: dict[str, dict[str, int]] = {}
    day = start
    while day <= end:
        buckets.setdefault(
            traffic._bucket(day, granularity), {"enrollments": 0, "starts": 0, "completions": 0}
        )
        day += timedelta(days=1)
    for key, rows, attr in (
        ("enrollments", new, "enrolled_at"),
        ("completions", completions, "completed_at"),
    ):
        for e in rows:
            buckets[traffic._bucket(_day(getattr(e, attr)), granularity)][key] += 1
    for e in starts:
        buckets[traffic._bucket(_day(first_view[e.id]), granularity)]["starts"] += 1

    granted = effective_permissions(actor)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "granularity": granularity},
        "course": {"id": course.id, "title": course.title} if course else None,
        "generated_at": iso(datetime.now(UTC)),
        "has_data": bool(enrollments),
        "course_options": course_options(),
        "current": _current_figures(enrollments, first_view),
        "period": period,
        "trend": [{"period": k, **v} for k, v in buckets.items()],
        "courses": _courses(course, enrollments, first_view, lo, hi),
        "lessons": _lessons(course, enrollments, first_view) if course else None,
        "assessments": _assessments(scope, lo, hi),
        "assignments": _assignments(scope, lo, hi)
        if P.ASSIGNMENTS_VIEW_REPORTS.value in granted
        else {"available": False, "reason": "Needs the assignment reports permission."},
        "definitions": {
            "started": "At least one lesson viewed, or completed. Start time is the first lesson "
            "view (or the completion time when no views were recorded).",
            "completed": "Marked complete by the course's completion rules.",
            "completion_rate": "Completed ÷ current enrollments (revoked access excluded).",
            "unfinished": "Started but not completed (current enrollments).",
            "active_learners": "Learners with a lesson view, lesson completion, assessment or "
            "assignment submission in the range. Only first and latest lesson views are "
            "stored, so this is a minimum.",
            "course_figures": "Per-course enrollment, completion, progress, submission, "
            "participation and best-score figures cover all time; the range applies to new "
            "enrollments and completions in range.",
            "access": "free = free course, purchase = bought individually, membership = "
            "included in a membership, manual = granted by staff.",
        },
    }


def _courses(course, enrollments, first_view, lo, hi) -> list[dict[str, Any]]:
    by_course: dict[int, list] = defaultdict(list)
    for e in enrollments:
        by_course[e.course_id].append(e)
    ids = [course.id] if course else list(by_course)
    if not ids:
        return []
    titles = {c.id: c for c in db.session.scalars(select(Course).where(Course.id.in_(ids)))}
    submissions = dict(
        db.session.execute(
            select(CourseAssignment.course_id, func.count(AssignmentSubmission.id))
            .join(AssignmentSubmission, AssignmentSubmission.assignment_id == CourseAssignment.id)
            .where(CourseAssignment.course_id.in_(ids), AssignmentSubmission.status != "draft")
            .group_by(CourseAssignment.course_id)
        ).all()
    )
    participants = dict(
        db.session.execute(
            select(Assessment.course_id, func.count(func.distinct(A.enrollment_id)))
            .join(A, A.assessment_id == Assessment.id)
            .where(Assessment.course_id.in_(ids), A.status == "submitted")
            .group_by(Assessment.course_id)
        ).all()
    )
    scores = _best_scores([Assessment.course_id.in_(ids)])
    rows = []
    for cid in ids:
        items = by_course.get(cid, [])
        current = [e for e in items if e.status == "active"]
        started = [e for e in current if e.id in first_view]
        done = [e for e in current if e.completed_at is not None]
        course_scores = [s for (c, _a, _e), s in scores.items() if c == cid]

        def inside(v):
            return v is not None and lo <= (v if v.tzinfo else v.replace(tzinfo=UTC)) < hi

        rows.append(
            {
                "id": cid,
                "title": titles[cid].title if cid in titles else str(cid),
                "status": titles[cid].status if cid in titles else None,
                "enrollments": len(current),
                "started": len(started),
                "completed": len(done),
                "completion_rate": _rate(len(done), len(current)),
                "average_progress": round(
                    sum(e.progress_percent for e in current) / len(current), 1
                )
                if current
                else None,
                "new_enrollments": sum(1 for e in items if inside(e.enrolled_at)),
                "completions_in_range": sum(1 for e in items if inside(e.completed_at)),
                "assignment_submissions": int(submissions.get(cid, 0)),
                "assessment_participants": int(participants.get(cid, 0)),
                "average_best_score": round(sum(course_scores) / len(course_scores), 1)
                if course_scores
                else None,
            }
        )
    rows.sort(key=lambda r: (-r["enrollments"], r["title"]))
    return rows


def _best_scores(conds) -> dict[tuple[int, int, int], int]:
    """(course, assessment, enrollment) -> best percent on graded, non-practice quizzes."""
    rows = db.session.execute(
        select(Assessment.course_id, A.assessment_id, A.enrollment_id, func.max(A.percent))
        .join(Assessment, Assessment.id == A.assessment_id)
        .where(
            *conds,
            A.status == "submitted",
            A.percent.is_not(None),
            Assessment.kind == "quiz",
            Assessment.practice.is_(False),
        )
        .group_by(Assessment.course_id, A.assessment_id, A.enrollment_id)
    ).all()
    return {(c, a, e): p for c, a, e, p in rows}


def _lessons(course, enrollments, first_view) -> dict[str, Any]:
    """Per published lesson: learners who viewed / completed it, and where unfinished
    learners stopped (their furthest completed lesson)."""
    lessons = db.session.execute(
        select(CourseLesson.id, CourseLesson.title, CourseModule.position, CourseLesson.position)
        .join(CourseModule, CourseModule.id == CourseLesson.module_id)
        .where(CourseLesson.course_id == course.id, CourseLesson.status == "published")
        .order_by(CourseModule.position, CourseLesson.position)
    ).all()
    current = {e.id: e for e in enrollments if e.status == "active"}
    started = [i for i in current if i in first_view]
    progress = db.session.execute(
        select(L.enrollment_id, L.lesson_id, L.completed_at).where(
            L.enrollment_id.in_(list(current) or [0])
        )
    ).all()
    viewed = defaultdict(int)
    done = defaultdict(int)
    completed_by: dict[int, set[int]] = defaultdict(set)
    for enrollment_id, lesson_id, completed_at in progress:
        viewed[lesson_id] += 1
        if completed_at is not None:
            done[lesson_id] += 1
            completed_by[enrollment_id].add(lesson_id)
    order = [lid for lid, *_ in lessons]
    stopped = defaultdict(int)
    for eid in started:
        if current[eid].completed_at is not None:
            continue
        furthest = None
        for lid in order:
            if lid in completed_by[eid]:
                furthest = lid
        stopped[furthest] += 1
    return {
        "started_learners": len(started),
        "items": [
            {
                "lesson_id": lid,
                "title": title,
                "viewed": viewed[lid],
                "completed": done[lid],
                "completion_rate_of_started": _rate(done[lid], len(started)),
                "unfinished_stopped_here": stopped.get(lid, 0),
            }
            for lid, title, *_ in lessons
        ],
        "unfinished_before_first_completion": stopped.get(None, 0),
        "note": '"Stopped here" = unfinished learners whose furthest completed lesson is '
        "this one; it shows where learners stall, not why.",
    }


def _kind(a: Assessment) -> str:
    if a.kind != "quiz":
        return "ungraded"
    if a.practice:
        return "practice"
    return "timed" if a.time_limit_minutes else "quiz"


def _assessments(scope, lo, hi) -> dict[str, Any]:
    rows = db.session.execute(
        select(Assessment, A.status, A.passed, A.percent, A.enrollment_id)
        .join(Assessment, Assessment.id == A.assessment_id)
        .join(E, E.id == A.enrollment_id)
        .where(
            *scope,
            or_(
                (A.submitted_at >= lo) & (A.submitted_at < hi),
                (A.status == "expired") & (A.started_at >= lo) & (A.started_at < hi),
            ),
        )
    ).all()
    groups: dict[str, dict[str, Any]] = {
        k: {
            "attempts": 0,
            "expired": 0,
            "participants": set(),
            "passed": 0,
            "failed": 0,
            "percents": [],
        }
        for k in ("quiz", "timed", "practice", "ungraded")
    }
    per_assessment: dict[int, dict[str, Any]] = {}
    for assessment, status, passed, percent, enrollment_id in rows:
        g = groups[_kind(assessment)]
        if status == "expired":
            g["expired"] += 1
            continue
        g["attempts"] += 1
        g["participants"].add(enrollment_id)
        if passed is True:
            g["passed"] += 1
        elif passed is False:
            g["failed"] += 1
        if percent is not None:
            g["percents"].append(percent)
        item = per_assessment.setdefault(
            assessment.id,
            {
                "assessment_id": assessment.id,
                "title": assessment.title,
                "type": _kind(assessment),
                "attempts": 0,
                "participants": set(),
                "passed": 0,
                "failed": 0,
                "percents": [],
            },
        )
        item["attempts"] += 1
        item["participants"].add(enrollment_id)
        item["passed"] += passed is True
        item["failed"] += passed is False
        if percent is not None:
            item["percents"].append(percent)

    def finish(d: dict[str, Any]) -> dict[str, Any]:
        percents = d.pop("percents")
        d["participants"] = len(d["participants"])
        d["average_percent"] = round(sum(percents) / len(percents), 1) if percents else None
        d["pass_rate"] = _rate(d["passed"], d["passed"] + d["failed"])
        return d

    return {
        "by_type": {k: finish(v) for k, v in groups.items()},
        "items": sorted((finish(v) for v in per_assessment.values()), key=lambda r: -r["attempts"])[
            :25
        ],
        "note": "Attempts submitted in the range. Pass rate = passed ÷ graded attempts. "
        "Practice and ungraded attempts never count towards grades.",
    }


def _assignments(scope, lo, hi) -> dict[str, Any]:
    sub_scope = (
        select(AssignmentSubmission.id)
        .join(E, E.id == AssignmentSubmission.enrollment_id)
        .where(*scope)
    )
    submitted = db.session.execute(
        select(AssignmentAttempt.is_late, func.count(AssignmentAttempt.id))
        .where(
            AssignmentAttempt.status == "submitted",
            AssignmentAttempt.submitted_at >= lo,
            AssignmentAttempt.submitted_at < hi,
            AssignmentAttempt.submission_id.in_(sub_scope),
        )
        .group_by(AssignmentAttempt.is_late)
    ).all()
    grades = db.session.execute(
        select(AssignmentGrade.passed, AssignmentGrade.percent, AssignmentGrade.outcome)
        .join(AssignmentAttempt, AssignmentAttempt.id == AssignmentGrade.attempt_id)
        .where(
            AssignmentGrade.status == "published",
            AssignmentGrade.published_at >= lo,
            AssignmentGrade.published_at < hi,
            AssignmentAttempt.submission_id.in_(sub_scope),
        )
    ).all()
    queue = dict(
        db.session.execute(
            select(AssignmentSubmission.status, func.count(AssignmentSubmission.id))
            .where(AssignmentSubmission.id.in_(sub_scope))
            .group_by(AssignmentSubmission.status)
        ).all()
    )
    percents = [p for _ok, p, _o in grades if p is not None]
    passed = sum(1 for ok, _p, _o in grades if ok is True)
    failed = sum(1 for ok, _p, _o in grades if ok is False)
    return {
        "available": True,
        "submitted": sum(n for _late, n in submitted),
        "submitted_late": sum(n for late, n in submitted if late),
        "graded": len(grades),
        "changes_requested_in_range": sum(1 for *_x, o in grades if o == "changes_requested"),
        "passed": passed,
        "failed": failed,
        "pass_rate": _rate(passed, passed + failed),
        "average_percent": round(sum(percents) / len(percents), 1) if percents else None,
        "pending_grading": sum(int(queue.get(s, 0)) for s in PENDING_REVIEW),
        "awaiting_resubmission": int(queue.get("changes_requested", 0)),
        "completed_or_graded": int(queue.get("graded", 0)) + int(queue.get("completed", 0)),
        "note": "Submitted = attempts submitted in the range; graded = grades published in "
        "the range. Pending grading is the current queue, whatever the dates.",
    }


def course_options() -> list[dict[str, Any]]:
    return [
        {"id": c.id, "title": c.title, "status": c.status}
        for c in db.session.scalars(
            select(Course).where(Course.status != "draft").order_by(Course.title)
        )
    ]
