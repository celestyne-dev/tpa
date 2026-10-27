"""Enrolment administration and course reports (real database records only).

Staff see progress, scores and completion. Learners' private exercise notes and written
reflection answers are not shown in the admin: they are personal learning records, and
nothing in the course is graded from them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import (
    Assessment,
    AssessmentAttempt,
    Course,
    CourseCertificate,
    CourseEnrollment,
    Customer,
    LessonProgress,
    User,
)
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..commerce import access
from ..serializers import iso
from . import learning
from .admin import published_lessons, require
from .certificates import admin_dict


def get_enrollment(course: Course, enrollment_id: int) -> CourseEnrollment:
    enrollment = db.session.get(CourseEnrollment, enrollment_id)
    if enrollment is None or enrollment.course_id != course.id:
        raise NotFoundError("Enrolment not found.")
    return enrollment


def _certificates(enrollment_ids: list[int]) -> dict[int, CourseCertificate]:
    if not enrollment_ids:
        return {}
    return {
        c.enrollment_id: c
        for c in db.session.scalars(
            select(CourseCertificate).where(CourseCertificate.enrollment_id.in_(enrollment_ids))
        )
    }


def enrollment_row(
    enrollment: CourseEnrollment, certificate: CourseCertificate | None
) -> dict[str, Any]:
    customer = enrollment.customer
    return {
        "id": enrollment.id,
        "learner": {
            "id": customer.public_id,
            "customer_id": customer.id,
            "email": customer.email,
            "name": customer.display_name,
        },
        "source": enrollment.source,
        "status": enrollment.status,
        "access": learning.access_state(enrollment),
        "enrolled_at": iso(enrollment.enrolled_at),
        "expires_at": iso(enrollment.expires_at),
        "last_activity_at": iso(enrollment.last_activity_at),
        "progress_percent": enrollment.progress_percent,
        "completed_at": iso(enrollment.completed_at),
        "revoked_reason": enrollment.revoked_reason,
        "certificate": admin_dict(certificate) if certificate else None,
    }


def list_enrollments(course: Course, args: dict[str, Any], actor: User) -> tuple[list, dict]:
    require(actor, P.COURSES_VIEW_ENROLLMENTS)
    stmt = (
        select(CourseEnrollment)
        .join(Customer, Customer.id == CourseEnrollment.customer_id)
        .where(CourseEnrollment.course_id == course.id)
    )
    status = args.get("status")
    if status == "active":
        stmt = stmt.where(CourseEnrollment.status == "active")
    elif status == "revoked":
        stmt = stmt.where(CourseEnrollment.status == "revoked")
    elif status == "completed":
        stmt = stmt.where(CourseEnrollment.completed_at.is_not(None))
    elif status == "in_progress":
        stmt = stmt.where(
            CourseEnrollment.completed_at.is_(None), CourseEnrollment.status == "active"
        )
    if q := (args.get("q") or "").strip().lower()[:100]:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(func.lower(Customer.email).like(like), func.lower(Customer.display_name).like(like))
        )
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        stmt.order_by(CourseEnrollment.enrolled_at.desc(), CourseEnrollment.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    certificates = _certificates([e.id for e in rows])
    return [enrollment_row(e, certificates.get(e.id)) for e in rows], {
        "page": page,
        "page_size": size,
        "total": total,
    }


def enrollment_detail(course: Course, enrollment: CourseEnrollment, actor: User) -> dict[str, Any]:
    require(actor, P.COURSES_VIEW_ENROLLMENTS)
    rows = {
        p.lesson_id: p
        for p in db.session.scalars(
            select(LessonProgress).where(LessonProgress.enrollment_id == enrollment.id)
        )
    }
    attempts: dict[int, list[AssessmentAttempt]] = {}
    for attempt in db.session.scalars(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.enrollment_id == enrollment.id)
        .order_by(AssessmentAttempt.attempt_number)
    ):
        attempts.setdefault(attempt.assessment_id, []).append(attempt)
    certificate = _certificates([enrollment.id]).get(enrollment.id)
    return {
        **enrollment_row(enrollment, certificate),
        "progress": learning.progress(enrollment),
        "lessons": [
            {
                "id": lesson.id,
                "title": lesson.title,
                "module": lesson.module.title,
                "viewed_at": iso(rows[lesson.id].last_viewed_at) if lesson.id in rows else None,
                "completed_at": iso(rows[lesson.id].completed_at) if lesson.id in rows else None,
                "exercises_done": len(rows[lesson.id].acknowledged or [])
                if lesson.id in rows
                else 0,
            }
            for lesson in published_lessons(course)
        ],
        "assessments": [
            {
                "id": a.id,
                "title": a.title,
                "kind": a.kind,
                "status": learning.assessment_service.assessment_state(a, attempts.get(a.id, [])),
                "attempts": [
                    {
                        "attempt_number": t.attempt_number,
                        "score": t.score,
                        "max_score": t.max_score,
                        "percent": t.percent,
                        "passed": t.passed,
                        "status": t.status,
                        "started_at": iso(t.started_at),
                        "submitted_at": iso(t.submitted_at),
                    }
                    for t in attempts.get(a.id, [])
                ],
            }
            for a in course.assessments
        ],
    }


def _reason(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ValidationError(details={"reason": ["Explain why (at most 300 characters)."]})
    return value.strip()


def manual_enroll(course: Course, data: Any, actor: User) -> CourseEnrollment:
    """Enrol an existing customer account (support cases, scholarships, corrections)."""
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    reason = _reason(data.get("reason"))
    email = (data.get("email") or "").strip().lower() if isinstance(data.get("email"), str) else ""
    customer = db.session.scalar(select(Customer).where(Customer.email == email)) if email else None
    if customer is None or customer.status != "active":
        raise ValidationError(details={"email": ["No active customer account uses this email."]})
    if course.status not in ("published", "draft", "scheduled"):
        raise ConflictError("Restore this course before enrolling learners.")
    enrollment = learning.enrollment_for(customer, course)
    created = enrollment is None
    if enrollment is None:
        expires = None
        if course.access_type == "free" and course.access_days:
            expires = datetime.now(UTC) + timedelta(days=course.access_days)
        elif course.access_type == "premium" and course.product is not None:
            from ..commerce.entitlements import expiry_for

            expires = expiry_for(course.product)
        enrollment, created = learning._create_enrollment(
            customer, course, source="manual", expires_at=expires, granted_by_id=actor.id
        )
    elif enrollment.status == "revoked":
        enrollment.status, enrollment.revoked_at, enrollment.revoked_reason = "active", None, ""
    else:
        raise ConflictError("This learner is already enrolled.")
    if course.product is not None and (
        course.access_type == "free" or enrollment.source == "manual"
    ):
        entitlement = access.grant(
            customer,
            course.product,
            source="course",
            reference=f"course-{course.id}-enrollment-{enrollment.id}",
            expires_at=enrollment.expires_at,
            reason=reason,
        )
        enrollment.entitlement_id = entitlement.id
    audit_service.record(
        "course.enrollment_granted" if created else "course.enrollment_restored",
        "course",
        course.id,
        actor=actor,
        details={"customer_id": customer.id, "enrollment_id": enrollment.id, "reason": reason},
    )
    return enrollment


def revoke_enrollment(
    course: Course, enrollment: CourseEnrollment, data: Any, actor: User
) -> CourseEnrollment:
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    reason = _reason((data or {}).get("reason") if isinstance(data, dict) else None)
    if enrollment.status == "revoked":
        raise ConflictError("This enrolment has already ended.")
    enrollment.status, enrollment.revoked_at, enrollment.revoked_reason = (
        "revoked",
        datetime.now(UTC),
        reason,
    )
    # Worksheets granted by the enrolment go too; purchases are refunded/revoked in Orders.
    revoked = access.revoke("course", f"course-{course.id}-enrollment-{enrollment.id}", reason)
    audit_service.record(
        "course.enrollment_revoked",
        "course",
        course.id,
        actor=actor,
        details={"enrollment_id": enrollment.id, "reason": reason, "entitlements_revoked": revoked},
    )
    return enrollment


def restore_enrollment(
    course: Course, enrollment: CourseEnrollment, data: Any, actor: User
) -> CourseEnrollment:
    return (
        manual_enroll(
            course,
            {"email": enrollment.customer.email, "reason": (data or {}).get("reason")},
            actor,
        )
        if enrollment.status == "revoked"
        else enrollment
    )


# ---- reports ----------------------------------------------------------------------------


def reports(actor: User, course: Course | None = None) -> dict[str, Any]:
    require(actor, P.COURSES_VIEW_REPORTS)
    now = datetime.now(UTC)
    status_counts = dict(
        db.session.execute(
            select(Course.status, func.count(Course.id)).group_by(Course.status)
        ).all()
    )
    scope = [CourseEnrollment.course_id == course.id] if course else []
    enrolled = select(func.count(CourseEnrollment.id)).where(*scope)
    totals = {
        "enrollments": db.session.scalar(enrolled) or 0,
        "active_enrollments": db.session.scalar(enrolled.where(CourseEnrollment.status == "active"))
        or 0,
        "completions": db.session.scalar(enrolled.where(CourseEnrollment.completed_at.is_not(None)))
        or 0,
        "active_learners_30d": db.session.scalar(
            select(func.count(func.distinct(CourseEnrollment.customer_id))).where(
                *scope, CourseEnrollment.last_activity_at >= now - timedelta(days=30)
            )
        )
        or 0,
        "new_enrollments_30d": db.session.scalar(
            enrolled.where(CourseEnrollment.enrolled_at >= now - timedelta(days=30))
        )
        or 0,
        "certificates_issued": db.session.scalar(
            select(func.count(CourseCertificate.id)).where(
                CourseCertificate.revoked_at.is_(None),
                *([CourseCertificate.course_id == course.id] if course else []),
            )
        )
        or 0,
    }
    totals["completion_rate"] = (
        round(100 * totals["completions"] / totals["enrollments"])
        if totals["enrollments"]
        else None
    )
    by_source = dict(
        db.session.execute(
            select(CourseEnrollment.source, func.count(CourseEnrollment.id))
            .where(*scope)
            .group_by(CourseEnrollment.source)
        ).all()
    )
    by_access = {"in_progress": 0, "completed": 0, "revoked": 0}
    for status, completed, count in db.session.execute(
        select(
            CourseEnrollment.status,
            CourseEnrollment.completed_at.is_not(None),
            func.count(CourseEnrollment.id),
        )
        .where(*scope)
        .group_by(CourseEnrollment.status, CourseEnrollment.completed_at.is_not(None))
    ).all():
        key = "revoked" if status == "revoked" else ("completed" if completed else "in_progress")
        by_access[key] += count
    assessments_q = select(Assessment).where(Assessment.kind == "quiz")
    if course:
        assessments_q = assessments_q.where(Assessment.course_id == course.id)
    pass_rates = []
    for assessment in db.session.scalars(assessments_q):
        attempted = (
            db.session.scalar(
                select(func.count(func.distinct(AssessmentAttempt.enrollment_id))).where(
                    AssessmentAttempt.assessment_id == assessment.id,
                    AssessmentAttempt.status != "in_progress",
                )
            )
            or 0
        )
        if not attempted:
            continue
        passed = (
            db.session.scalar(
                select(func.count(func.distinct(AssessmentAttempt.enrollment_id))).where(
                    AssessmentAttempt.assessment_id == assessment.id,
                    AssessmentAttempt.passed.is_(True),
                )
            )
            or 0
        )
        attempts = (
            db.session.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.assessment_id == assessment.id,
                    AssessmentAttempt.status != "in_progress",
                )
            )
            or 0
        )
        pass_rates.append(
            {
                "assessment_id": assessment.id,
                "course_id": assessment.course_id,
                "title": assessment.title,
                "learners": attempted,
                "passed": passed,
                "attempts": attempts,
                "pass_rate": round(100 * passed / attempted),
            }
        )
    per_course = []
    courses = (
        [course]
        if course
        else db.session.scalars(
            select(Course).where(Course.status != "archived").order_by(Course.title)
        ).all()
    )
    for item in courses:
        stats = db.session.execute(
            select(
                func.count(CourseEnrollment.id),
                func.count(CourseEnrollment.completed_at),
                func.avg(CourseEnrollment.progress_percent),
            ).where(CourseEnrollment.course_id == item.id, CourseEnrollment.status == "active")
        ).one()
        per_course.append(
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "access_type": item.access_type,
                "learners": stats[0],
                "completions": stats[1],
                "average_progress": round(float(stats[2])) if stats[2] is not None else None,
            }
        )
    return {
        "courses": {
            "total": sum(status_counts.values()),
            "published": status_counts.get("published", 0),
            "draft": status_counts.get("draft", 0),
            "scheduled": status_counts.get("scheduled", 0),
            "archived": status_counts.get("archived", 0),
        },
        "enrollments": totals,
        "by_source": by_source,
        "by_status": by_access,
        "assessment_pass_rates": pass_rates,
        "per_course": per_course,
        "generated_at": iso(now),
    }
