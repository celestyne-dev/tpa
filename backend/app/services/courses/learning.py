"""Enrolment, access, progress and completion for learners.

Access rules (checked on every learner request, server-side):

- Learning needs a signed-in customer whose email address is confirmed, so progress and
  assessment results belong to someone who proved they own the mailbox.
- The enrolment must be active (staff can end it).
- Free courses: the enrolment's own access period (if any) must not have ended.
- Premium courses: the customer must hold a usable entitlement to the course product in
  their account scope (any source: purchase, bundle, manual, membership). Refunds,
  revocations and expiry therefore end access at once. Guest-checkout purchases only
  count after the account email is confirmed (``entitlements.account_scope``), which is
  how a guest purchase is claimed securely: knowing the purchase email isn't enough.

Enrolments for premium courses are created from those entitlements (``sync``) when the
learner opens their learning area, after payment for verified accounts, and when staff
enrol someone. Completion is computed from stored records only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
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
    if customer.status != "active" or customer.email_verified_at is None:
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
            ent_service.account_scope(customer),
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
    """Create enrolments for premium courses the customer has (verified) access to."""
    if customer.status != "active" or customer.email_verified_at is None:
        return 0
    rows = db.session.execute(
        select(Course, Entitlement)
        .join(Entitlement, Entitlement.product_id == Course.product_id)
        .where(
            Course.status.in_(("published", "archived")),
            ent_service.account_scope(customer),
            Entitlement.status == "active",
            ent_service.not_expired(),
        )
    ).all()
    created = 0
    for course, entitlement in rows:
        source = "free" if entitlement.source == "free" else "purchase"
        if entitlement.source == "manual":
            source = "manual"
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
    """After a verified payment: enrol registered, verified buyers straight away."""
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
    _require_verified(customer)
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
    assessments = [
        a for a in course.assessments if a.status == "published" and a.required_for_completion
    ]
    return required, assessments


def _assessment_done(assessment: Assessment, attempts: list[AssessmentAttempt]) -> bool:
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


def _assignments_done(enrollment: CourseEnrollment, assignments: list) -> int:
    """Required assignments with a released, passing grade (submission ``completed``)."""
    if not assignments:
        return 0
    from ...models import AssignmentSubmission

    return int(
        db.session.scalar(
            select(func.count(AssignmentSubmission.id)).where(
                AssignmentSubmission.enrollment_id == enrollment.id,
                AssignmentSubmission.assignment_id.in_([a.id for a in assignments]),
                AssignmentSubmission.status == "completed",
            )
        )
        or 0
    )


def progress(enrollment: CourseEnrollment) -> dict[str, Any]:
    course = enrollment.course
    lessons, assessments = requirements(course)
    assignments = required_assignments(course)
    rows = _progress_rows(enrollment)
    attempts = _attempts(enrollment)
    lessons_done = sum(
        1 for lesson in lessons if rows.get(lesson.id) and rows[lesson.id].completed_at
    )
    assessments_done = sum(1 for a in assessments if _assessment_done(a, attempts.get(a.id, [])))
    assignments_done = _assignments_done(enrollment, assignments)
    total = len(lessons) + len(assessments) + len(assignments)
    done = lessons_done + assessments_done + assignments_done
    return {
        "percent": round(100 * done / total) if total else 0,
        "required_lessons": len(lessons),
        "completed_lessons": lessons_done,
        "required_assessments": len(assessments),
        "completed_assessments": assessments_done,
        "required_assignments": len(assignments),
        "completed_assignments": assignments_done,
        "complete": bool(total) and done == total,
    }


def recompute(enrollment: CourseEnrollment) -> dict[str, Any]:
    state = progress(enrollment)
    # Completion is never undone: requirements added later (e.g. a new required
    # assignment) don't revoke a completed course or its certificate.
    enrollment.progress_percent = 100 if enrollment.completed_at else state["percent"]
    if state["complete"] and enrollment.completed_at is None:
        enrollment.completed_at = _now()
        audit_service.record(
            "course.completed",
            "course",
            enrollment.course_id,
            details={"customer_id": enrollment.customer_id, "enrollment_id": enrollment.id},
        )
        if enrollment.course.certificate_enabled:
            from .certificates import issue

            if (enrollment.customer.display_name or "").strip():
                issue(enrollment)
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


def submit_assessment(
    customer: Customer, course: Course, assessment_id: int, answers: Any
) -> dict[str, Any]:
    enrollment = require_access(customer, course)
    assessment = db.session.get(Assessment, assessment_id)
    if assessment is None or assessment.course_id != course.id or assessment.status != "published":
        raise NotFoundError("Assessment not found.")
    if assessment.lesson_id is not None:
        lesson = db.session.get(CourseLesson, assessment.lesson_id)
        if lesson is None or lesson.status != "published":
            raise NotFoundError("Assessment not found.")
    attempt = assessment_service.submit(assessment, enrollment, answers)
    _touch(enrollment)
    state = recompute(enrollment)
    return {
        "attempt": assessment_service.attempt_dict(assessment, attempt),
        "assessment": assessment_service.learner_assessment(assessment, enrollment),
        "progress": state,
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
    certificate = db.session.scalar(
        select(CourseCertificate).where(CourseCertificate.enrollment_id == enrollment.id)
    )
    if certificate is None:
        return None
    return {
        "code": certificate.code,
        "recipient_name": certificate.recipient_name,
        "issued_at": iso(certificate.issued_at),
        "revoked": certificate.revoked_at is not None,
    }


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
        "certificate": _certificate(enrollment),
        "certificate_available": course.certificate_enabled and enrollment.completed_at is not None,
    }


def my_learning(customer: Customer) -> dict[str, Any]:
    _require_verified(customer)
    sync(customer)
    enrollments = db.session.scalars(
        select(CourseEnrollment)
        .where(CourseEnrollment.customer_id == customer.id)
        .order_by(
            func.coalesce(CourseEnrollment.last_activity_at, CourseEnrollment.enrolled_at).desc()
        )
    ).all()
    return {"enrollments": [enrollment_card(e, customer) for e in enrollments]}


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
    enrollment = require_access(customer, course)
    assessment = db.session.get(Assessment, assessment_id)
    if assessment is None or assessment.course_id != course.id or assessment.status != "published":
        raise NotFoundError("Assessment not found.")
    if assessment.lesson_id is not None:
        lesson = db.session.get(CourseLesson, assessment.lesson_id)
        if lesson is None or lesson.status != "published":
            raise NotFoundError("Assessment not found.")
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
                        "answers": a.answers,
                        "percent": a.percent,
                        "passed": a.passed,
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
        certificate.recipient_name = "Deleted account"
        if certificate.revoked_at is None:
            certificate.revoked_at, certificate.revoked_reason = now, "Account deleted"
