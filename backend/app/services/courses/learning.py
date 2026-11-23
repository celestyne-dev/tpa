"""Enrolment, access, progress and completion for learners.

Access rules (checked on every learner request, server-side):

- Learning needs a signed-in, active customer whose email address is confirmed, so
  progress and assessment results belong to someone who proved they own the mailbox.
  One exception: a premium course the customer **bought themselves while signed in**
  (a ``purchase`` or ``bundle`` entitlement from a paid, non-guest order of their own
  account; see ``own_purchase_scope``) opens before the email is confirmed. Those
  entitlements exist only after Paystack verified the payment and end on refund. Free
  courses, membership courses, courses added by staff and claimed guest purchases still
  need a confirmed email.
- The enrolment must be active (staff can end it).
- Free courses: the enrolment's own access period (if any) must not have ended.
- Premium courses: the customer must hold a usable entitlement to the course product in
  their account scope (any source: purchase, bundle, manual, membership). Refunds,
  revocations and expiry therefore end access at once. Guest-checkout purchases only
  count after the account email is confirmed (``entitlements.account_scope``), which is
  how a guest purchase is claimed securely: knowing the purchase email isn't enough.

Enrolments for premium courses are created from those entitlements (``sync``) when the
learner opens their learning area, right after payment, and when staff
enrol someone. Completion is computed from stored records only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ...extensions import db
from ...models import (
    Assessment,
    AssessmentAttempt,
    Course,
    CourseCertificate,
    CourseEnrollment,
    CourseLesson,
    Customer,
    Entitlement,
    LessonProgress,
    Order,
)
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..commerce import entitlements as ent_service
from ..serializers import expand_body, iso
from . import assessments as assessment_service
from . import content
from .admin import lesson_minutes, published_lessons, total_minutes


class EmailVerificationRequired(APIError):
    status_code = 403
    code = "email_verification_required"
    message = "Confirm your email address to start learning."


class NotEnrolledError(APIError):
    status_code = 403
    code = "not_enrolled"
    message = "Enrol in this course to open its lessons."


class AccessEndedError(APIError):
    status_code = 403
    code = "course_access_ended"
    message = "Your access to this course has ended."


def _now() -> datetime:
    return datetime.now(UTC)


def _require_verified(customer: Customer) -> None:
    if not is_verified(customer):
        raise EmailVerificationRequired()


# Entitlement sources created by a paid order (``entitlements.grant_for_order``).
PURCHASE_SOURCES = ("purchase", "bundle")
_PAID_ORDER_STATUSES = ("paid", "partially_refunded")


def is_verified(customer: Customer) -> bool:
    return customer.status == "active" and customer.email_verified_at is not None


def own_purchase_scope(customer: Customer):
    """Entitlements from this customer's own paid, signed-in (non-guest) orders.

    Entitlements are only created once Paystack has verified the payment, and refunds
    revoke them; the order checks here are a second guard, not the only one.
    """
    paid_own_orders = select(Order.id).where(
        Order.customer_id == customer.id,
        Order.is_guest.is_(False),
        Order.status.in_(_PAID_ORDER_STATUSES),
        Order.paid_at.is_not(None),
    )
    return (
        (Entitlement.customer_id == customer.id)
        & Entitlement.source.in_(PURCHASE_SOURCES)
        & Entitlement.order_id.in_(paid_own_orders)
    )


def learner_scope(customer: Customer):
    """Entitlements that open courses: everything in the account once the email is
    confirmed; before that, only the customer's own signed-in purchases."""
    if is_verified(customer):
        return ent_service.account_scope(customer)
    return own_purchase_scope(customer)


def may_open(customer: Customer, course: Course) -> bool:
    """Whether the email requirement lets this customer into this course (enrolment and
    access are checked separately)."""
    if customer.status != "active":
        return False
    if customer.email_verified_at is not None:
        return True
    return course.access_type == "premium" and product_entitlement(customer, course) is not None


def _require_may_open(customer: Customer, course: Course) -> None:
    if not may_open(customer, course):
        raise EmailVerificationRequired()


def learner_course_by_slug(slug: str) -> Course:
    course = db.session.scalar(select(Course).where(Course.slug == slug))
    # Archived courses stay open to people already enrolled.
    if course is None or course.status not in ("published", "archived"):
        raise NotFoundError("Course not found.")
    return course


# ---- access -----------------------------------------------------------------------------


def product_entitlement(customer: Customer, course: Course) -> Entitlement | None:
    """The customer's usable entitlement to the course product (longest-lasting first)."""
    if course.product_id is None:
        return None
    rows = db.session.scalars(
        select(Entitlement).where(
            learner_scope(customer),
            Entitlement.product_id == course.product_id,
            Entitlement.status == "active",
            ent_service.not_expired(),
        )
    ).all()
    if not rows:
        return None
    return max(rows, key=lambda e: (e.expires_at is None, e.expires_at or _now()))


def access_state(enrollment: CourseEnrollment, customer: Customer | None = None) -> str:
    """active | revoked | expired | ended (premium access no longer held)."""
    if enrollment.status != "active":
        return "revoked"
    course = enrollment.course
    if course.access_type == "premium":
        if enrollment.source == "manual" and enrollment.entitlement_id:
            entitlement = db.session.get(Entitlement, enrollment.entitlement_id)
            if entitlement is not None and ent_service.is_usable(entitlement):
                return "active"
        return "active" if product_entitlement(customer or enrollment.customer, course) else "ended"
    if enrollment.expires_at is not None and enrollment.expires_at <= _now():
        return "expired"
    return "active"


def _create_enrollment(
    customer: Customer, course: Course, **values
) -> tuple[CourseEnrollment, bool]:
    existing = db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.customer_id == customer.id, CourseEnrollment.course_id == course.id
        )
    )
    if existing is not None:
        return existing, False
    enrollment = CourseEnrollment(customer_id=customer.id, course_id=course.id, **values)
    try:
        with db.session.begin_nested():
            db.session.add(enrollment)
            db.session.flush()
    except IntegrityError:
        # A concurrent request enrolled the same learner: use that row.
        existing = db.session.scalar(
            select(CourseEnrollment).where(
                CourseEnrollment.customer_id == customer.id,
                CourseEnrollment.course_id == course.id,
            )
        )
        return existing, False
    return enrollment, True


def sync(customer: Customer) -> int:
    """Create enrolments for premium courses the customer has access to (before the email
    is confirmed: only courses they bought themselves while signed in)."""
    if customer.status != "active":
        return 0
    rows = db.session.execute(
        select(Course, Entitlement)
        .join(Entitlement, Entitlement.product_id == Course.product_id)
        .where(
            Course.status.in_(("published", "archived")),
            learner_scope(customer),
            Entitlement.status == "active",
            ent_service.not_expired(),
        )
    ).all()
    created = 0
    for course, entitlement in rows:
        source = "free" if entitlement.source == "free" else "purchase"
        if entitlement.source in ("manual", "membership"):
            source = entitlement.source
        enrollment, new = _create_enrollment(
            customer, course, source=source, entitlement_id=entitlement.id
        )
        if new:
            created += 1
            audit_service.record(
                "course.enrolled",
                "course",
                course.id,
                details={
                    "customer_id": customer.id,
                    "source": source,
                    "entitlement_id": entitlement.id,
                },
            )
    return created


def sync_for_order(order) -> int:
    """After a verified payment: enrol registered buyers straight away."""
    customer = order.customer
    if customer is None or order.is_guest:
        return 0  # guest purchases are claimed after the account email is confirmed
    return sync(customer)


def enroll_free(customer: Customer, course: Course) -> tuple[CourseEnrollment, bool]:
    _require_verified(customer)
    if course.status != "published":
        raise NotFoundError("Course not found.")
    if course.access_type != "free":
        raise ConflictError("This is a premium course; buy it to enrol.")
    existing = db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.customer_id == customer.id, CourseEnrollment.course_id == course.id
        )
    )
    if existing is not None:
        if existing.status == "revoked":
            raise ConflictError("Your enrolment was ended. Contact us if this is a mistake.")
        if access_state(existing, customer) == "expired":
            existing.expires_at = _expiry(course)
            _grant_files(customer, course, existing)
            audit_service.record(
                "course.enrollment_renewed",
                "course",
                course.id,
                details={"customer_id": customer.id},
            )
        return existing, False
    if course.availability != "available":
        raise ConflictError("This course isn't open yet.")
    if not course.enrollment_open:
        raise ConflictError("Enrolment for this course is closed.")
    enrollment, created = _create_enrollment(
        customer, course, source="free", expires_at=_expiry(course)
    )
    if created:
        _grant_files(customer, course, enrollment)
        audit_service.record(
            "course.enrolled",
            "course",
            course.id,
            details={"customer_id": customer.id, "source": "free"},
        )
    return enrollment, created


def _expiry(course: Course) -> datetime | None:
    return _now() + timedelta(days=course.access_days) if course.access_days else None


def _grant_files(customer: Customer, course: Course, enrollment: CourseEnrollment) -> None:
    """Free and manual enrolments get the course worksheets through a course entitlement."""
    if course.product is None or course.access_type == "premium" and enrollment.source != "manual":
        return
    from ..commerce import access

    entitlement = access.grant(
        customer,
        course.product,
        source="course",
        reference=f"course-{course.id}-enrollment-{enrollment.id}",
        expires_at=enrollment.expires_at,
        reason=f"Enrolled in “{course.title}”",
    )
    enrollment.entitlement_id = entitlement.id


def enrollment_for(customer: Customer, course: Course) -> CourseEnrollment | None:
    return db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.customer_id == customer.id, CourseEnrollment.course_id == course.id
        )
    )


def require_access(customer: Customer, course: Course) -> CourseEnrollment:
    _require_may_open(customer, course)
    enrollment = enrollment_for(customer, course)
    if enrollment is None and course.access_type == "premium":
        sync(customer)
        enrollment = enrollment_for(customer, course)
    if enrollment is None:
        raise NotEnrolledError()
    state = access_state(enrollment, customer)
    if state == "revoked":
        raise AccessEndedError("Your enrolment in this course was ended.")
    if state == "expired":
        raise AccessEndedError(
            "Your access period for this course has ended. Enrol again to continue."
        )
    if state == "ended":
        raise AccessEndedError(
            "Your access to this course has ended (refunded, removed or expired)."
        )
    return enrollment


# ---- progress and completion ------------------------------------------------------------


def _progress_rows(enrollment: CourseEnrollment) -> dict[int, LessonProgress]:
    return {
        p.lesson_id: p
        for p in db.session.scalars(
            select(LessonProgress).where(LessonProgress.enrollment_id == enrollment.id)
        )
    }


def _attempts(enrollment: CourseEnrollment) -> dict[int, list[AssessmentAttempt]]:
    out: dict[int, list[AssessmentAttempt]] = {}
    for attempt in db.session.scalars(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.enrollment_id == enrollment.id)
        .order_by(AssessmentAttempt.attempt_number)
    ):
        out.setdefault(attempt.assessment_id, []).append(attempt)
    return out


def requirements(course: Course) -> tuple[list[CourseLesson], list[Assessment]]:
    lessons = published_lessons(course)
    required = [lesson for lesson in lessons if lesson.completion_required] or lessons
    # Practice exams never count (Batch 09.2 phase 2).
    assessments = [
        a
        for a in course.assessments
        if a.status == "published" and a.required_for_completion and not a.practice
    ]
    return required, assessments


def _assessment_done(assessment: Assessment, attempts: list[AssessmentAttempt]) -> bool:
    if assessment_service.passing_score_problem(assessment):
        return False
    state = assessment_service.assessment_state(assessment, attempts)
    return state in ("passed", "submitted")


def required_assignments(course: Course) -> list:
    """Published, required written assignments (Batch 09.2). See the completion policy in
    services/courses/assignment_admin.py: they apply to enrolments not yet completed."""
    from ...models import CourseAssignment

    return list(
        db.session.scalars(
            select(CourseAssignment).where(
                CourseAssignment.course_id == course.id,
                CourseAssignment.status == "published",
                CourseAssignment.required.is_(True),
            )
        )
    )


def _assignment_statuses(enrollment: CourseEnrollment, assignments: list) -> dict[int, str]:
    """Submission status per required assignment (``completed``: released, passing grade)."""
    if not assignments:
        return {}
    from ...models import AssignmentSubmission

    return dict(
        db.session.execute(
            select(AssignmentSubmission.assignment_id, AssignmentSubmission.status).where(
                AssignmentSubmission.enrollment_id == enrollment.id,
                AssignmentSubmission.assignment_id.in_([a.id for a in assignments]),
            )
        ).all()
    )


def _assignments_done(enrollment: CourseEnrollment, assignments: list) -> int:
    """Required assignments with a released, passing grade (submission ``completed``)."""
    statuses = _assignment_statuses(enrollment, assignments)
    return sum(1 for a in assignments if statuses.get(a.id) == "completed")


# ---- completion -----------------------------------------------------------------------------
#
# Completion rules (calculated here, on the server, from what the learner has done):
# - Required lessons: published lessons marked "required for completion" (when none is
#   marked, every published lesson). A course with no published lessons has no meaningful
#   requirements and never completes, whatever else it contains; enrolment alone never
#   completes a course.
# - Required assessments: published quizzes must be passed (at their passing score, which
#   must be at least 1%: a required quiz at 0% never counts);
#   reflections and self-assessments must be submitted. Practice exams never count.
# - Required written assignments: a released, passing grade.
#
# The completion award (``completed_at`` and ``completion_snapshot``) is recorded once,
# atomically, and never undone. Requirements edited later apply to learners who have not
# completed yet; completed learners keep their completion and certificate. Completions
# recorded before awards existed are re-checked against the current requirements before a
# certificate is issued (see certificates.eligibility).

COMPLETION_RULES = 2


def _best_percent(attempts: list[AssessmentAttempt]) -> int | None:
    scores = [a.percent for a in attempts if a.finished and a.percent is not None]
    return max(scores) if scores else None


def progress(enrollment: CourseEnrollment) -> dict[str, Any]:
    course = enrollment.course
    lessons, assessments = requirements(course)
    assignments = required_assignments(course)
    rows = _progress_rows(enrollment)
    attempts = _attempts(enrollment)
    statuses = _assignment_statuses(enrollment, assignments)
    outstanding: list[dict[str, Any]] = []
    lessons_done = 0
    for lesson in lessons:
        if rows.get(lesson.id) and rows[lesson.id].completed_at:
            lessons_done += 1
        else:
            outstanding.append({"type": "lesson", "slug": lesson.slug, "title": lesson.title})
    assessments_done = 0
    for assessment in assessments:
        state = assessment_service.assessment_state(assessment, attempts.get(assessment.id, []))
        if assessment_service.passing_score_problem(assessment):
            # A required quiz with a 0% passing score proves nothing: it never counts until
            # staff set a real passing score (publishing such a quiz is refused).
            state = "needs_passing_score"
        if state in ("passed", "submitted"):
            assessments_done += 1
        else:
            outstanding.append(
                {
                    "type": "assessment",
                    "id": assessment.id,
                    "title": assessment.title,
                    "state": state,
                    "passing_score": assessment.passing_score if assessment.graded else None,
                    "best_percent": _best_percent(attempts.get(assessment.id, [])),
                }
            )
    assignments_done = 0
    for assignment in assignments:
        if statuses.get(assignment.id) == "completed":
            assignments_done += 1
        else:
            outstanding.append(
                {
                    "type": "assignment",
                    "id": assignment.id,
                    "title": assignment.title,
                    "state": statuses.get(assignment.id, "not_started"),
                }
            )
    total = len(lessons) + len(assessments) + len(assignments)
    done = lessons_done + assessments_done + assignments_done
    meaningful = bool(lessons)
    return {
        "percent": round(100 * done / total) if total else 0,
        "required_lessons": len(lessons),
        "completed_lessons": lessons_done,
        "required_assessments": len(assessments),
        "completed_assessments": assessments_done,
        "required_assignments": len(assignments),
        "completed_assignments": assignments_done,
        "has_requirements": meaningful,
        "complete": meaningful and done == total,
        "outstanding": outstanding[:50],
    }


def completion_snapshot(
    enrollment: CourseEnrollment, state: dict[str, Any], *, recorded: str = "at_completion"
) -> dict[str, Any]:
    """What the learner had met when the completion award was recorded."""
    course = enrollment.course
    lessons, assessments = requirements(course)
    attempts = _attempts(enrollment)
    return {
        "rules": COMPLETION_RULES,
        "recorded": recorded,
        "at": iso(_now()),
        "lessons": [lesson.id for lesson in lessons],
        "assessments": [
            {
                "id": a.id,
                "kind": a.kind,
                "passing_score": a.passing_score if a.graded else None,
                "best_percent": _best_percent(attempts.get(a.id, [])),
            }
            for a in assessments
        ],
        "assignments": [a.id for a in required_assignments(course)],
        "counts": {
            "lessons": state["required_lessons"],
            "assessments": state["required_assessments"],
            "assignments": state["required_assignments"],
        },
    }


def _award(enrollment: CourseEnrollment, state: dict[str, Any]) -> bool:
    """Record the completion once (a conditional UPDATE, so concurrent requests can't both
    award it). Returns True for the request that recorded it."""
    now = _now()
    result = db.session.execute(
        update(CourseEnrollment)
        .where(CourseEnrollment.id == enrollment.id, CourseEnrollment.completed_at.is_(None))
        .values(
            completed_at=now,
            completion_snapshot=completion_snapshot(enrollment, state),
            progress_percent=100,
        )
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(enrollment, ["completed_at", "completion_snapshot", "progress_percent"])
    if result.rowcount != 1:
        return False
    audit_service.record(
        "course.completed",
        "course",
        enrollment.course_id,
        details={"customer_id": enrollment.customer_id, "enrollment_id": enrollment.id},
    )
    return True


def recompute(enrollment: CourseEnrollment) -> dict[str, Any]:
    """Recalculate progress after a change and record the completion award when every
    requirement is met. Completion is never undone: requirements added later (e.g. a new
    required lesson or assignment) don't reopen a completed course or revoke its
    certificate."""
    state = progress(enrollment)
    if state["complete"] and enrollment.completed_at is None and _award(enrollment, state):
        from .certificates import issue_on_completion

        issue_on_completion(enrollment)
    enrollment.progress_percent = 100 if enrollment.completed_at else state["percent"]
    return state


def _touch(enrollment: CourseEnrollment, lesson: CourseLesson | None = None) -> None:
    enrollment.last_activity_at = _now()
    if lesson is not None:
        enrollment.last_lesson_id = lesson.id


def _lesson_row(enrollment: CourseEnrollment, lesson: CourseLesson) -> LessonProgress:
    row = db.session.scalar(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id, LessonProgress.lesson_id == lesson.id
        )
    )
    if row is not None:
        return row
    row = LessonProgress(
        enrollment_id=enrollment.id, lesson_id=lesson.id, acknowledged=[], responses={}
    )
    try:
        with db.session.begin_nested():
            db.session.add(row)
            db.session.flush()
    except IntegrityError:
        row = db.session.scalar(
            select(LessonProgress).where(
                LessonProgress.enrollment_id == enrollment.id,
                LessonProgress.lesson_id == lesson.id,
            )
        )
    return row


def _find_lesson(course: Course, lesson_slug: str) -> CourseLesson:
    for lesson in published_lessons(course):
        if lesson.slug == lesson_slug:
            return lesson
    raise NotFoundError("Lesson not found.")


def complete_lesson(customer: Customer, course: Course, lesson_slug: str) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    lesson = _find_lesson(course, lesson_slug)
    row = _lesson_row(enrollment, lesson)
    missing = content.required_exercise_ids(lesson.body) - set(row.acknowledged or [])
    if missing:
        raise ValidationError(
            "Mark the required exercises as done first.",
            details={"exercises": sorted(missing)},
        )
    unticked = content.required_checklist_item_ids(lesson.body) - set(row.checklist or [])
    if unticked:
        raise ValidationError(
            "Tick every item in the required checklist first.",
            details={"checklist": sorted(unticked)},
        )
    if row.completed_at is None:
        row.completed_at = _now()
    _touch(enrollment, lesson)
    return {"lesson_completed": True, "progress": recompute(enrollment)}


def save_exercise(
    customer: Customer, course: Course, lesson_slug: str, exercise_id: str, data: Any
) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    lesson = _find_lesson(course, lesson_slug)
    exercise = next((e for e in content.exercises(lesson.body) if e.get("id") == exercise_id), None)
    if exercise is None:
        raise NotFoundError("Exercise not found.")
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    row = _lesson_row(enrollment, lesson)
    if "response" in data:
        response = data["response"]
        if not exercise.get("allow_response", True):
            raise ValidationError(details={"response": ["This exercise has no written answer."]})
        if not isinstance(response, str) or len(response) > 5000 or plain_text_problem(response):
            raise ValidationError(details={"response": ["Plain text of at most 5000 characters."]})
        responses = dict(row.responses or {})
        responses[exercise_id] = response.strip()
        row.responses = responses
    if "done" in data:
        if not isinstance(data["done"], bool):
            raise ValidationError(details={"done": ["Must be true or false."]})
        done = set(row.acknowledged or [])
        (done.add if data["done"] else done.discard)(exercise_id)
        row.acknowledged = sorted(done)
    _touch(enrollment, lesson)
    return {
        "exercise_id": exercise_id,
        "done": exercise_id in (row.acknowledged or []),
        "response": (row.responses or {}).get(exercise_id, ""),
    }


def _published_assessment(course: Course, assessment_id: int) -> Assessment:
    assessment = db.session.get(Assessment, assessment_id)
    if assessment is None or assessment.course_id != course.id or assessment.status != "published":
        raise NotFoundError("Assessment not found.")
    if assessment.lesson_id is not None:
        lesson = db.session.get(CourseLesson, assessment.lesson_id)
        if lesson is None or lesson.status != "published":
            raise NotFoundError("Assessment not found.")
    return assessment


def _open_assessment(
    customer: Customer, course: Course, assessment_id: int
) -> tuple[CourseEnrollment, Assessment]:
    """Access check, then the published assessment; an attempt whose deadline passed is
    scored on its saved answers first (so progress reflects it)."""
    enrollment = require_access(customer, course)
    assessment = _published_assessment(course, assessment_id)
    if assessment_service.expire_overdue(assessment, enrollment):
        recompute(enrollment)
    return enrollment, assessment


def _attempt_result(
    enrollment: CourseEnrollment, assessment: Assessment, attempt: AssessmentAttempt
) -> dict[str, Any]:
    _touch(enrollment)
    state = recompute(enrollment)
    return {
        "attempt": assessment_service.learner_attempt(assessment, attempt),
        "assessment": assessment_service.learner_assessment(assessment, enrollment),
        "progress": state,
    }


def submit_assessment(
    customer: Customer, course: Course, assessment_id: int, answers: Any
) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    assessment = _published_assessment(course, assessment_id)
    attempt = assessment_service.submit(assessment, enrollment, answers)
    return _attempt_result(enrollment, assessment, attempt)


def start_assessment(
    customer: Customer, course: Course, assessment_id: int
) -> tuple[dict[str, Any], bool]:
    enrollment, assessment = _open_assessment(customer, course, assessment_id)
    attempt, created = assessment_service.start(assessment, enrollment)
    _touch(enrollment)
    return {
        "attempt": assessment_service.in_progress_dict(attempt),
        "assessment": assessment_service.learner_assessment(assessment, enrollment),
    }, created


def save_attempt(
    customer: Customer, course: Course, assessment_id: int, attempt_id: int, answers: Any
) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    assessment = _published_assessment(course, assessment_id)
    attempt = assessment_service.save_answers(assessment, enrollment, attempt_id, answers)
    _touch(enrollment)
    return {"attempt": assessment_service.in_progress_dict(attempt)}


def submit_attempt(
    customer: Customer, course: Course, assessment_id: int, attempt_id: int, answers: Any
) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    assessment = _published_assessment(course, assessment_id)
    attempt = assessment_service.finish(assessment, enrollment, attempt_id, answers)
    return _attempt_result(enrollment, assessment, attempt)


def attempt_view(
    customer: Customer, course: Course, assessment_id: int, attempt_id: int
) -> dict[str, Any]:
    enrollment, assessment = _open_assessment(customer, course, assessment_id)
    attempt = db.session.get(AssessmentAttempt, attempt_id)
    if (
        attempt is None
        or attempt.assessment_id != assessment.id
        or attempt.enrollment_id != enrollment.id
    ):
        raise NotFoundError("Attempt not found.")
    return {"attempt": assessment_service.learner_attempt(assessment, attempt)}


def assessment_history(
    customer: Customer, course: Course, assessment_id: int | None = None
) -> dict[str, Any]:
    """The learner's attempts: for one assessment, or every published one in the course."""
    enrollment = require_access(customer, course)
    if assessment_id is not None:
        assessments = [_published_assessment(course, assessment_id)]
    else:
        visible = {lesson.id for lesson in published_lessons(course)}
        assessments = [
            a
            for a in course.assessments
            if a.status == "published" and (a.lesson_id is None or a.lesson_id in visible)
        ]
    changed = False
    for assessment in assessments:
        changed = assessment_service.expire_overdue(assessment, enrollment) or changed
    if changed:
        recompute(enrollment)
    return {
        "course": {"slug": course.slug, "title": course.title},
        "assessments": [assessment_service.attempt_history(a, enrollment) for a in assessments],
    }


# ---- learner views ----------------------------------------------------------------------


def _resume_lesson(
    course: Course, enrollment: CourseEnrollment, rows: dict[int, LessonProgress]
) -> CourseLesson | None:
    lessons = published_lessons(course)
    if not lessons:
        return None
    if enrollment.last_lesson_id:
        last = next((lesson for lesson in lessons if lesson.id == enrollment.last_lesson_id), None)
        if last is not None and not (rows.get(last.id) and rows[last.id].completed_at):
            return last
    return next(
        (
            lesson
            for lesson in lessons
            if not (rows.get(lesson.id) and rows[lesson.id].completed_at)
        ),
        lessons[0],
    )


def _resume_dict(
    resume: CourseLesson | None, rows: dict[int, LessonProgress]
) -> dict[str, Any] | None:
    if resume is None:
        return None
    row = rows.get(resume.id)
    position = row.position if row is not None else None
    return {
        "slug": resume.slug,
        "title": resume.title,
        "percent": (position or {}).get("percent"),
        "last_viewed_at": iso(row.last_viewed_at) if row is not None else None,
    }


def _certificate(enrollment: CourseEnrollment) -> dict[str, Any] | None:
    from .certificates import latest_for, learner_dict

    return learner_dict(latest_for(enrollment.id))


def certificate_status(
    enrollment: CourseEnrollment, state: dict[str, Any], certificate: dict[str, Any] | None
) -> str:
    """issued | revoked | available (ask for it) | requirements_changed | in_progress |
    not_offered."""
    if certificate is not None:
        return "revoked" if certificate["revoked"] else "issued"
    if not enrollment.course.certificate_enabled:
        return "not_offered"
    if enrollment.completed_at is None:
        return "in_progress"
    if enrollment.completion_snapshot is None and not state["complete"]:
        return "requirements_changed"
    return "available"


def _cover(course: Course) -> dict | None:
    from ...models import MediaAsset

    asset = db.session.get(MediaAsset, course.cover_media_id) if course.cover_media_id else None
    if asset is None or asset.visibility != "public" or asset.status == "archived":
        return None
    return asset.as_image("responsive")


def enrollment_card(enrollment: CourseEnrollment, customer: Customer) -> dict[str, Any]:
    course = enrollment.course
    rows = _progress_rows(enrollment)
    resume = _resume_lesson(course, enrollment, rows)
    state = progress(enrollment)
    certificate = _certificate(enrollment)
    status = certificate_status(enrollment, state, certificate)
    return {
        "course": {
            "slug": course.slug,
            "title": course.title,
            "summary": course.summary,
            "cover": _cover(course),
            "access_type": course.access_type,
            "total_minutes": total_minutes(course),
            "archived": course.status == "archived",
        },
        "access": access_state(enrollment, customer),
        "enrolled_at": iso(enrollment.enrolled_at),
        "expires_at": iso(enrollment.expires_at),
        "last_activity_at": iso(enrollment.last_activity_at),
        "completed_at": iso(enrollment.completed_at),
        "progress": state,
        "resume": _resume_dict(resume, rows),
        "certificate": certificate,
        "certificate_status": status,
        "certificate_available": status == "available",
    }


def my_learning(customer: Customer) -> dict[str, Any]:
    if customer.status != "active":
        raise EmailVerificationRequired()
    sync(customer)
    enrollments = db.session.scalars(
        select(CourseEnrollment)
        .where(CourseEnrollment.customer_id == customer.id)
        .order_by(
            func.coalesce(CourseEnrollment.last_activity_at, CourseEnrollment.enrolled_at).desc()
        )
    ).all()
    verified = is_verified(customer)
    if not verified:  # only courses they bought while signed in, until the email is confirmed
        enrollments = [e for e in enrollments if may_open(customer, e.course)]
    return {
        "verified": verified,
        "enrollments": [enrollment_card(e, customer) for e in enrollments],
    }


def course_outline(customer: Customer, course: Course) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    rows = _progress_rows(enrollment)
    attempts = _attempts(enrollment)
    resume = _resume_lesson(course, enrollment, rows)
    modules = []
    for module in course.modules:
        lessons = [lesson for lesson in module.lessons if lesson.status == "published"]
        if not lessons:
            continue
        modules.append(
            {
                "id": module.id,
                "title": module.title,
                "description": module.description,
                "objectives": module.objectives or [],
                "lessons": [
                    {
                        "slug": lesson.slug,
                        "title": lesson.title,
                        "summary": lesson.summary,
                        "minutes": lesson_minutes(lesson),
                        "completed": bool(rows.get(lesson.id) and rows[lesson.id].completed_at),
                        "viewed": lesson.id in rows,
                        "required": lesson.completion_required,
                    }
                    for lesson in lessons
                ],
                "completed": all(
                    rows.get(lesson.id) and rows[lesson.id].completed_at for lesson in lessons
                ),
            }
        )
    visible_lessons = {lesson.id for lesson in published_lessons(course)}
    assessment_items = [
        {
            "id": a.id,
            "title": a.title,
            "kind": a.kind,
            "graded": a.graded,
            "lesson_id": a.lesson_id,
            "required": a.required_for_completion,
            "practice": a.practice,
            "status": assessment_service.assessment_state(a, attempts.get(a.id, [])),
        }
        for a in course.assessments
        if a.status == "published" and (a.lesson_id is None or a.lesson_id in visible_lessons)
    ]
    return {
        **enrollment_card(enrollment, customer),
        "course": {
            "slug": course.slug,
            "title": course.title,
            "summary": course.summary,
            "outcomes": course.outcomes or [],
            "total_minutes": total_minutes(course),
            "access_type": course.access_type,
            "certificate_enabled": course.certificate_enabled,
            "cover": _cover(course),
        },
        "modules": modules,
        "assessments": assessment_items,
        "resume": _resume_dict(resume, rows),
    }


def _downloads(
    customer: Customer, course: Course, enrollment: CourseEnrollment, blocks: list[dict]
) -> dict[str, dict]:
    wanted = content.download_file_ids(blocks)
    if not wanted or course.product_id is None:
        return {}
    entitlement = product_entitlement(customer, course)
    if entitlement is None and enrollment.entitlement_id:
        candidate = db.session.get(Entitlement, enrollment.entitlement_id)
        if candidate is not None and ent_service.is_usable(candidate):
            entitlement = candidate
    if entitlement is None:
        return {}
    out = {}
    for item in ent_service.accessible_files(entitlement):
        file = item["file"]
        if file.public_id not in wanted:
            continue
        kind, version = item["versions"][0]
        out[file.public_id] = {
            "entitlement_id": entitlement.id,
            "version_id": version.id,
            "title": file.title,
            "format": version.file_format.upper(),
            "size_bytes": version.size_bytes,
        }
    return out


def _reader_outline(
    course: Course, rows: dict[int, LessonProgress], current: CourseLesson
) -> list[dict[str, Any]]:
    out = []
    for module in course.modules:
        lessons = [lesson for lesson in module.lessons if lesson.status == "published"]
        if not lessons:
            continue
        items = [
            {
                "slug": lesson.slug,
                "title": lesson.title,
                "minutes": lesson_minutes(lesson),
                "completed": bool(rows.get(lesson.id) and rows[lesson.id].completed_at),
                "current": lesson.id == current.id,
            }
            for lesson in lessons
        ]
        out.append(
            {
                "id": module.id,
                "title": module.title,
                "lessons": items,
                "completed": sum(1 for i in items if i["completed"]),
                "total": len(items),
                "current": module.id == current.module_id,
            }
        )
    return out


def lesson_view(customer: Customer, course: Course, lesson_slug: str) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    lesson = _find_lesson(course, lesson_slug)
    row = _lesson_row(enrollment, lesson)
    row.last_viewed_at = _now()
    _touch(enrollment, lesson)
    lessons = published_lessons(course)
    index = lessons.index(lesson)
    downloads = _downloads(customer, course, enrollment, lesson.body)
    body = []
    for block in expand_body(lesson.body or []):
        if block.get("type") == "download":
            file = downloads.get(block.get("file_id"))
            if file is None:
                continue  # file inactive or not covered by this learner's access
            block = {**block, "file": file}
        body.append(block)
    assessments = [
        assessment_service.learner_assessment(a, enrollment)
        for a in course.assessments
        if a.lesson_id == lesson.id and a.status == "published"
    ]
    module = lesson.module
    from . import study

    rows = _progress_rows(enrollment)
    outline = _reader_outline(course, rows, lesson)
    current_module = next((m for m in outline if m["current"]), None)
    return {
        "course": {"slug": course.slug, "title": course.title},
        "module": {
            "id": module.id,
            "title": module.title,
            "completed": current_module["completed"] if current_module else 0,
            "total": current_module["total"] if current_module else 0,
        },
        "outline": outline,
        "toc": content.headings(lesson.body),
        "lesson": {
            "slug": lesson.slug,
            "title": lesson.title,
            "summary": lesson.summary,
            "minutes": lesson_minutes(lesson),
            "body": body,
            "position": index + 1,
            "count": len(lessons),
            "required": lesson.completion_required,
        },
        "state": {
            "completed": row.completed_at is not None,
            "acknowledged": row.acknowledged or [],
            "responses": row.responses or {},
            "required_exercises": sorted(content.required_exercise_ids(lesson.body)),
            "required_checklist": sorted(content.required_checklist_item_ids(lesson.body)),
        },
        "study": study.lesson_state(customer, lesson, row),
        "previous": {"slug": lessons[index - 1].slug, "title": lessons[index - 1].title}
        if index > 0
        else None,
        "next": {"slug": lessons[index + 1].slug, "title": lessons[index + 1].title}
        if index + 1 < len(lessons)
        else None,
        "assessments": assessments,
        "progress": progress(enrollment),
    }


def assessment_view(customer: Customer, course: Course, assessment_id: int) -> dict[str, Any]:
    enrollment, assessment = _open_assessment(customer, course, assessment_id)
    return {
        "course": {"slug": course.slug, "title": course.title},
        "assessment": assessment_service.learner_assessment(assessment, enrollment),
        "progress": progress(enrollment),
    }


# ---- personal data ------------------------------------------------------------------------


def export_learner(customer: Customer) -> list[dict[str, Any]]:
    """Enrolments, progress, notes, answers and certificates (data-portability export)."""
    out = []
    for enrollment in db.session.scalars(
        select(CourseEnrollment).where(CourseEnrollment.customer_id == customer.id)
    ):
        rows = _progress_rows(enrollment)
        lessons = {lesson.id: lesson.title for lesson in published_lessons(enrollment.course)}
        attempts = _attempts(enrollment)
        out.append(
            {
                "course": enrollment.course.title,
                "enrolled_at": iso(enrollment.enrolled_at),
                "source": enrollment.source,
                "status": enrollment.status,
                "completed_at": iso(enrollment.completed_at),
                "progress_percent": enrollment.progress_percent,
                "lessons": [
                    {
                        "lesson": lessons.get(row.lesson_id, f"Lesson {row.lesson_id}"),
                        "completed_at": iso(row.completed_at),
                        "notes": row.responses or {},
                    }
                    for row in rows.values()
                ],
                "assessments": [
                    {
                        "attempt": a.attempt_number,
                        "status": a.status,
                        "answers": a.answers,
                        "percent": a.percent,
                        "passed": a.passed,
                        "started_at": iso(a.started_at),
                        "submitted_at": iso(a.submitted_at),
                    }
                    for items in attempts.values()
                    for a in items
                ],
                "certificate": _certificate(enrollment),
            }
        )
    return out


def erase_learner(customer: Customer) -> None:
    """On account deletion: remove private notes and written answers, end enrolments and
    revoke certificates (their verification page would otherwise show the name)."""
    from . import study, submissions

    study.erase(customer)
    submissions.erase_learner(customer)
    now = _now()
    for enrollment in db.session.scalars(
        select(CourseEnrollment).where(CourseEnrollment.customer_id == customer.id)
    ):
        if enrollment.status == "active":
            enrollment.status, enrollment.revoked_at = "revoked", now
            enrollment.revoked_reason = "Account deleted"
        for row in _progress_rows(enrollment).values():
            row.responses = {}
        for items in _attempts(enrollment).values():
            for attempt in items:
                attempt.answers = {
                    k: (None if isinstance(v, str) else v)
                    for k, v in (attempt.answers or {}).items()
                }
                attempt.results = [
                    {**r, "answer": None} if r.get("kind") == "short_text" else r
                    for r in attempt.results or []
                ]
    for certificate in db.session.scalars(
        select(CourseCertificate).where(CourseCertificate.customer_id == customer.id)
    ):
        # Every one, including certificates already revoked or replaced, so verification
        # says "unavailable" and shows no name.
        certificate.recipient_name = "Deleted account"
        certificate.revoked_at = certificate.revoked_at or now
        certificate.revoked_reason = "Account deleted"
