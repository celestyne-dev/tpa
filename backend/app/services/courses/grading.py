"""Reviewing and grading submissions (Batch 09.2).

Who may do what (checked here, server-side):

- ``assignments.view_submissions``: read submissions and their documents;
- ``assignments.grade``: save draft grades (scores, feedback, private notes);
- ``assignments.publish_grades``: release grades, request changes, retract a release.

All three also require *scope*: staff who manage assignments, or the course's assessors
(``assignment_admin.in_scope``). Being signed in, or holding the permission alone, is not
enough to read another course's submissions.

Submission workflow (explicit transitions, anything else is refused)::

    draft ─submit→ pending_review ─review→ under_review ─publish→ graded | completed
                                                       └publish (changes)→ changes_requested
    changes_requested ─submit→ resubmitted ─review→ under_review …
    graded ─submit (policy "always")→ resubmitted
    graded | completed | changes_requested ─retract→ under_review

``completed`` means a published, passing grade: it satisfies the assignment's completion
requirement. Each attempt has at most one grade row, pinned to the rubric version it was
first scored against; edits and releases bump ``lock_version`` (stale writes are refused)
and every release, change and retraction is written to the audit log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import (
    AssignmentAttempt,
    AssignmentGrade,
    AssignmentRubric,
    AssignmentSubmission,
    CourseAssignment,
    Customer,
    User,
)
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from . import assignment_admin as defs
from .admin import require
from .submissions import attempt_dict, claim, file_dict

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review"},
    "pending_review": {"under_review", "graded", "completed", "changes_requested"},
    "under_review": {"graded", "completed", "changes_requested", "pending_review"},
    "changes_requested": {"resubmitted", "under_review"},
    "resubmitted": {"under_review", "graded", "completed", "changes_requested"},
    "graded": {"resubmitted", "under_review"},
    "completed": {"under_review"},
}
MAX_FEEDBACK = 20_000


class InvalidTransitionError(ConflictError):
    code = "invalid_transition"


def _now() -> datetime:
    return datetime.now(UTC)


def transition(submission: AssignmentSubmission, target: str) -> None:
    if target not in TRANSITIONS.get(submission.status, set()):
        raise InvalidTransitionError(
            f"A submission can't move from {submission.status.replace('_', ' ')} to "
            f"{target.replace('_', ' ')}."
        )
    submission.status = target
    submission.completed_at = _now() if target == "completed" else None
    submission.lock_version += 1


# ---- scope and lookups ---------------------------------------------------------------------


def _scoped(actor: User, assignment: CourseAssignment, *perms: P) -> None:
    require(actor, *perms)
    if not defs.in_scope(actor, assignment.course_id):
        raise ForbiddenError("You aren't an assessor for this course.")


def get_submission(public_id: str, actor: User) -> AssignmentSubmission:
    submission = db.session.scalar(
        select(AssignmentSubmission).where(AssignmentSubmission.public_id == public_id)
    )
    if submission is None:
        raise NotFoundError("Submission not found.")
    _scoped(actor, submission.assignment, P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    return submission


def get_attempt(public_id: str, actor: User) -> AssignmentAttempt:
    attempt = db.session.scalar(
        select(AssignmentAttempt).where(AssignmentAttempt.public_id == public_id)
    )
    if attempt is None or attempt.status != "submitted":
        raise NotFoundError("Attempt not found.")
    _scoped(actor, attempt.submission.assignment, P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    return attempt


def grade_for(attempt: AssignmentAttempt) -> AssignmentGrade | None:
    return db.session.scalar(
        select(AssignmentGrade).where(AssignmentGrade.attempt_id == attempt.id)
    )


def staff_grade(grade: AssignmentGrade | None) -> dict[str, Any] | None:
    if grade is None:
        return None
    rubric = db.session.get(AssignmentRubric, grade.rubric_id) if grade.rubric_id else None
    return {
        "status": grade.status,
        "outcome": grade.outcome,
        "rubric": defs.rubric_dict(rubric),
        "scores": grade.scores or {},
        "total_points": grade.total_points,
        "max_points": grade.max_points,
        "percent": grade.percent,
        "passed": grade.passed,
        "feedback": grade.feedback,
        "private_notes": grade.private_notes,
        "lock_version": grade.lock_version,
        "grader_id": grade.grader_id,
        "graded_at": iso(grade.graded_at),
        "published_at": iso(grade.published_at),
        "published_by_id": grade.published_by_id,
        "retracted_at": iso(grade.retracted_at),
        "retracted_reason": grade.retracted_reason,
    }


def submission_detail(submission: AssignmentSubmission, actor: User) -> dict[str, Any]:
    submitted = [a for a in submission.attempts if a.status == "submitted"]
    latest = submitted[-1].number if submitted else None
    learner = db.session.get(Customer, submission.customer_id)
    return {
        "id": submission.public_id,
        "assignment": defs.assignment_dict(submission.assignment),
        "learner": {
            "customer_id": submission.customer_id,
            "name": learner.display_name if learner else None,
            "email": learner.email if learner else None,
        },
        "enrollment_id": submission.enrollment_id,
        "status": submission.status,
        "lock_version": submission.lock_version,
        "completed_at": iso(submission.completed_at),
        # Drafts are the learner's private work in progress: staff only see submissions.
        "attempts": [
            {
                **{k: v for k, v in attempt_dict(a, latest_number=latest).items() if k != "grade"},
                "files": [file_dict(f) for f in a.files],
                "content_sha256": a.content_sha256,
                "grade": staff_grade(grade_for(a)),
            }
            for a in reversed(submitted)
        ],
    }


def list_submissions(
    assignment: CourseAssignment, actor: User, status: str | None = None
) -> list[dict[str, Any]]:
    _scoped(actor, assignment, P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    query = select(AssignmentSubmission).where(
        AssignmentSubmission.assignment_id == assignment.id,
        AssignmentSubmission.status != "draft",
    )
    if status:
        query = query.where(AssignmentSubmission.status == status)
    out = []
    for submission in db.session.scalars(query.order_by(AssignmentSubmission.updated_at)):
        submitted = [a for a in submission.attempts if a.status == "submitted"]
        last = submitted[-1] if submitted else None
        out.append(
            {
                "id": submission.public_id,
                "customer_id": submission.customer_id,
                "status": submission.status,
                "attempts": len(submitted),
                "latest_attempt": last.public_id if last else None,
                "submitted_at": iso(last.submitted_at) if last else None,
                "late": bool(last and last.is_late),
            }
        )
    return out


QUEUE_LIMIT = 200


def review_queue(actor: User, args: dict[str, str]) -> dict[str, Any]:
    """Submissions across every course the actor may review (Batch 09.2 phase 3: the
    instructor dashboard). Same scope as ``list_submissions``: staff who manage assignments
    see every course, assessors only their assigned courses. Drafts are never listed."""
    from ...models import Course, CourseAssessor

    require(actor, P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    query = (
        select(AssignmentSubmission, CourseAssignment, Course)
        .join(CourseAssignment, CourseAssignment.id == AssignmentSubmission.assignment_id)
        .join(Course, Course.id == CourseAssignment.course_id)
        .where(AssignmentSubmission.status != "draft")
    )
    if not defs.granted(actor, P.ASSIGNMENTS_MANAGE):
        assigned = select(CourseAssessor.course_id).where(CourseAssessor.user_id == actor.id)
        query = query.where(CourseAssignment.course_id.in_(assigned))
    courses = {
        course.id: course.title
        for _, _, course in db.session.execute(query.order_by(Course.title)).all()
    }
    status = (args.get("status") or "").strip()
    if status == "awaiting":
        query = query.where(
            AssignmentSubmission.status.in_(("pending_review", "resubmitted", "under_review"))
        )
    elif status:
        query = query.where(AssignmentSubmission.status == status)
    course_id = args.get("course_id")
    if course_id:
        if not course_id.isdigit():
            raise ValidationError(details={"course_id": ["Use a course id."]})
        query = query.where(CourseAssignment.course_id == int(course_id))
    rows = db.session.execute(
        query.order_by(AssignmentSubmission.updated_at).limit(QUEUE_LIMIT)
    ).all()
    items = []
    for submission, assignment, course in rows:
        submitted = [a for a in submission.attempts if a.status == "submitted"]
        last = submitted[-1] if submitted else None
        learner = db.session.get(Customer, submission.customer_id)
        grade = grade_for(last) if last else None
        items.append(
            {
                "id": submission.public_id,
                "status": submission.status,
                "course": {"id": course.id, "title": course.title},
                "assignment": {"id": assignment.public_id, "title": assignment.title},
                "learner": {
                    "name": learner.display_name if learner else None,
                    "email": learner.email if learner else None,
                },
                "attempts": len(submitted),
                "latest_attempt": last.public_id if last else None,
                "submitted_at": iso(last.submitted_at) if last else None,
                "late": bool(last and last.is_late),
                "grade_status": grade.status if grade else None,
            }
        )
    return {
        "items": items,
        "courses": [{"id": cid, "title": title} for cid, title in courses.items()],
        "truncated": len(items) == QUEUE_LIMIT,
    }


# ---- review and grading ---------------------------------------------------------------------


def start_review(submission: AssignmentSubmission, data: dict, actor: User) -> None:
    _scoped(actor, submission.assignment, P.ASSIGNMENTS_GRADE)
    defs.check_lock(submission, data)
    claim(AssignmentSubmission, submission, submission.lock_version)
    transition(submission, "under_review")
    audit_service.record(
        "assignment.review_started",
        "course",
        submission.assignment.course_id,
        actor=actor,
        details={"submission_id": submission.public_id},
    )


def _latest_submitted(submission: AssignmentSubmission) -> AssignmentAttempt | None:
    submitted = [a for a in submission.attempts if a.status == "submitted"]
    return submitted[-1] if submitted else None


def _score(
    assignment: CourseAssignment, rubric: AssignmentRubric | None, data: dict, errors: dict
) -> dict[str, Any]:
    if rubric is None:
        passed = data.get("passed")
        if passed is not None and not isinstance(passed, bool):
            errors["passed"] = ["Must be true or false."]
        return {
            "scores": {},
            "total_points": None,
            "max_points": None,
            "percent": None,
            "passed": passed,
        }
    scores = data.get("scores", {})
    if not isinstance(scores, dict):
        errors["scores"] = ["Send a score for each criterion."]
        return {}
    criteria = {c["id"]: c for c in rubric.criteria}
    unknown = set(scores) - set(criteria)
    if unknown:
        errors["scores"] = ["Unknown criterion."]
        return {}
    clean = {}
    for cid, value in scores.items():
        maximum = criteria[cid]["max_points"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
            errors.setdefault("scores", []).append(
                f"“{criteria[cid]['title']}” takes 0 to {maximum} points."
            )
        else:
            clean[cid] = value
    total = sum(clean.values())
    percent = round(100 * total / rubric.total_points) if len(clean) == len(criteria) else None
    return {
        "scores": clean,
        "total_points": total if len(clean) == len(criteria) else None,
        "max_points": rubric.total_points,
        "percent": percent,
        "passed": percent >= rubric.passing_percent if percent is not None else None,
    }


def save_grade(attempt: AssignmentAttempt, data: Any, actor: User) -> AssignmentGrade:
    """Create or update the attempt's draft grade (not visible to the learner)."""
    submission = attempt.submission
    assignment = submission.assignment
    _scoped(actor, assignment, P.ASSIGNMENTS_GRADE)
    if not isinstance(data, dict) or set(data) - {
        "scores",
        "passed",
        "feedback",
        "private_notes",
        "lock_version",
    }:
        raise ValidationError("Send scores, feedback and notes.")
    if attempt is not _latest_submitted(submission):
        raise ConflictError("Only the latest attempt can be graded; earlier attempts are history.")
    grade = grade_for(attempt)
    if grade is not None:
        defs.check_lock(grade, data)
        if grade.status == "published":
            raise ConflictError("Retract the released grade before changing it.")
    errors: dict[str, Any] = {}
    for field in ("feedback", "private_notes"):
        value = data.get(field)
        if value is not None and (
            not isinstance(value, str) or len(value) > MAX_FEEDBACK or plain_text_problem(value)
        ):
            errors[field] = [f"Plain text of at most {MAX_FEEDBACK} characters."]
    if grade is None:
        rubric = defs.current_rubric(assignment)
    else:
        rubric = db.session.get(AssignmentRubric, grade.rubric_id) if grade.rubric_id else None
    scored = (
        _score(assignment, rubric, data, errors) if ("scores" in data or "passed" in data) else None
    )
    if errors:
        raise ValidationError("The grade needs attention.", details=errors)
    created = grade is None
    if created:
        grade = AssignmentGrade(
            attempt_id=attempt.id, rubric_id=rubric.id if rubric else None, status="draft"
        )
        try:
            with db.session.begin_nested():
                db.session.add(grade)
                db.session.flush()
        except IntegrityError:
            raise defs.EditConflictError(
                "Another assessor started grading this attempt. Reload it."
            ) from None
    else:
        claim(AssignmentGrade, grade, grade.lock_version)
    if scored is not None:
        for key, value in scored.items():
            setattr(grade, key, value)
    for field in ("feedback", "private_notes"):
        if data.get(field) is not None:
            setattr(grade, field, data[field].strip())
    if grade.status == "retracted":
        grade.status = "draft"
    grade.grader_id = actor.id
    grade.graded_at = _now()
    if submission.status in ("pending_review", "resubmitted"):
        transition(submission, "under_review")
    db.session.flush()
    audit_service.record(
        "assignment.grade_saved",
        "course",
        assignment.course_id,
        actor=actor,
        details={
            "submission_id": submission.public_id,
            "attempt": attempt.number,
            "rubric_id": grade.rubric_id,
            "percent": grade.percent,
            "created": created,
        },
    )
    return grade


def publish_grade(attempt: AssignmentAttempt, data: Any, actor: User) -> AssignmentGrade:
    """Release the draft grade (``outcome=graded``) or request changes."""
    submission = attempt.submission
    assignment = submission.assignment
    _scoped(actor, assignment, P.ASSIGNMENTS_PUBLISH_GRADES)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    grade = grade_for(attempt)
    if grade is None:
        raise ConflictError("Save a grade before releasing it.")
    defs.check_lock(grade, data)
    if grade.status == "published":
        raise ConflictError("This grade has already been released.")
    if attempt is not _latest_submitted(submission):
        raise ConflictError("Only the latest attempt can be released.")
    outcome = data.get("outcome", "graded")
    if outcome not in ("graded", "changes_requested"):
        raise ValidationError(details={"outcome": ["Use graded or changes_requested."]})
    rubric = db.session.get(AssignmentRubric, grade.rubric_id) if grade.rubric_id else None
    problems = []
    if outcome == "graded":
        if rubric is not None and grade.total_points is None:
            problems.append("Score every criterion before releasing the grade.")
        if rubric is None and grade.passed is None:
            problems.append("Mark the submission as passed or not passed.")
        if rubric is not None and rubric.feedback_required and not grade.feedback.strip():
            problems.append("This rubric requires written feedback.")
    elif not grade.feedback.strip():
        problems.append("Explain what should change (feedback is required).")
    if problems:
        raise ValidationError("The grade isn't ready to release.", details={"grade": problems})
    if rubric is None and outcome == "graded" and grade.passed is not None:
        grade.percent = 100 if grade.passed else 0
    passed = bool(grade.passed) if outcome == "graded" else None
    target = ("completed" if passed else "graded") if outcome == "graded" else "changes_requested"
    claim(AssignmentGrade, grade, grade.lock_version)
    transition(submission, target)
    grade.outcome = outcome
    if outcome == "changes_requested":
        grade.passed = None
    grade.status = "published"
    grade.published_at = _now()
    grade.published_by_id = actor.id
    grade.retracted_at, grade.retracted_reason = None, ""
    db.session.flush()
    audit_service.record(
        "assignment.grade_published",
        "course",
        assignment.course_id,
        actor=actor,
        details={
            "submission_id": submission.public_id,
            "attempt": attempt.number,
            "outcome": outcome,
            "percent": grade.percent,
            "passed": grade.passed,
            "rubric_id": grade.rubric_id,
            "grader_id": grade.grader_id,
        },
    )
    _recompute(submission)
    return grade


def retract_grade(attempt: AssignmentAttempt, data: Any, actor: User) -> AssignmentGrade:
    """Withdraw a released grade (with a reason). The learner no longer sees it. A
    course completion or certificate already issued is not revoked by this."""
    submission = attempt.submission
    assignment = submission.assignment
    _scoped(actor, assignment, P.ASSIGNMENTS_PUBLISH_GRADES)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    grade = grade_for(attempt)
    if grade is None or grade.status != "published":
        raise ConflictError("Only a released grade can be retracted.")
    defs.check_lock(grade, data)
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        raise ValidationError(details={"reason": ["Give a reason (at most 300 characters)."]})
    if attempt is not _latest_submitted(submission):
        raise ConflictError("Only the latest attempt's grade can be retracted.")
    claim(AssignmentGrade, grade, grade.lock_version)
    transition(submission, "under_review")
    grade.status = "retracted"
    grade.retracted_at = _now()
    grade.retracted_reason = reason.strip()
    db.session.flush()
    audit_service.record(
        "assignment.grade_retracted",
        "course",
        assignment.course_id,
        actor=actor,
        details={
            "submission_id": submission.public_id,
            "attempt": attempt.number,
            "reason": reason.strip(),
            "previous_percent": grade.percent,
        },
    )
    _recompute(submission)
    return grade


def _recompute(submission: AssignmentSubmission) -> None:
    from ...models import CourseEnrollment
    from .learning import recompute

    enrollment = db.session.get(CourseEnrollment, submission.enrollment_id)
    if enrollment is not None and enrollment.status == "active":
        recompute(enrollment)


def download_for_staff(file_public_id: str, actor: User):
    from ...models import AssignmentFile
    from ..commerce.downloads import file_response

    file = db.session.scalar(
        select(AssignmentFile).where(AssignmentFile.public_id == file_public_id)
    )
    if file is None:
        raise NotFoundError("File not found.")
    attempt = file.attempt
    submission = attempt.submission
    _scoped(actor, submission.assignment, P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    if attempt.status != "submitted":
        raise NotFoundError("File not found.")  # drafts stay private to the learner
    audit_service.record(
        "assignment.file_downloaded",
        "course",
        submission.assignment.course_id,
        actor=actor,
        details={"file_id": file.public_id, "submission_id": submission.public_id, "by": "staff"},
    )
    db.session.commit()
    return file_response(file, f"submission-{submission.public_id}-{file.public_id}")
