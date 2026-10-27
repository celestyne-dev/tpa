"""Public course catalogue, certificate verification and the learner API.

- ``/courses``…: published catalogue data only (prerendered; never lesson content except
  lessons marked as free previews).
- ``/account/learning``…: signed-in customers with a confirmed email; every request
  re-checks enrolment and access (refunds, revocation and expiry apply at once).
- ``/certificates/<code>``: anyone can check a certificate code (no-store, noindex).
"""

from __future__ import annotations

from flask import Response, request
from flask_restful import Resource

from ..auth.customer_session import current_customer, require_customer
from ..extensions import db, limiter
from ..services.courses import certificates, learning, public
from ..utils.errors import NotFoundError, ValidationError
from ..utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


class CourseListResource(Resource):
    def get(self):
        args = {k: v for k, v in request.args.items() if len(v) <= 120}
        items, meta = public.list_public(args)
        return success(items, meta)


class CourseDetailResource(Resource):
    def get(self, slug: str):
        return success(public.course_detail(public.published_by_slug(slug)))


class CoursePreviewLessonResource(Resource):
    def get(self, slug: str, lesson_slug: str):
        return success(public.preview_lesson(slug, lesson_slug))


class CertificateVerifyResource(Resource):
    decorators = [limiter.limit("30 per minute")]

    def get(self, code: str):
        return success(certificates.verify_dict(certificates.get_by_code(code)))


# ---- learner ------------------------------------------------------------------------------


class LearningResource(Resource):
    @require_customer
    def get(self):
        data = learning.my_learning(current_customer())
        db.session.commit()
        return success(data)


class LearningStatusResource(Resource):
    """What the course page should offer this visitor (never an error for "not enrolled")."""

    @require_customer
    def get(self, slug: str):
        customer = current_customer()
        course = public.published_by_slug(slug)
        if customer.email_verified_at is not None and course.access_type == "premium":
            learning.sync(customer)
        enrollment = learning.enrollment_for(customer, course)
        state = learning.access_state(enrollment, customer) if enrollment else None
        db.session.commit()
        return success(
            {
                "verified": customer.email_verified_at is not None,
                "enrolled": enrollment is not None,
                "access": state,
                "progress": enrollment.progress_percent if enrollment else 0,
                "completed": bool(enrollment and enrollment.completed_at),
                "can_enroll": course.access_type == "free"
                and course.availability == "available"
                and (course.enrollment_open or enrollment is not None)
                and state in (None, "expired"),
            }
        )


class LearningEnrollResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self, slug: str):
        course = public.published_by_slug(slug)
        enrollment, created = learning.enroll_free(current_customer(), course)
        db.session.commit()
        return success(
            {"enrolled": True, "created": created, "course": course.slug},
            status=201 if created else 200,
        )


class LearningCourseResource(Resource):
    @require_customer
    def get(self, slug: str):
        data = learning.course_outline(current_customer(), learning.learner_course_by_slug(slug))
        db.session.commit()
        return success(data)


class LearningLessonResource(Resource):
    @require_customer
    def get(self, slug: str, lesson_slug: str):
        data = learning.lesson_view(
            current_customer(), learning.learner_course_by_slug(slug), lesson_slug
        )
        db.session.commit()
        return success(data)


class LearningLessonCompleteResource(Resource):
    method_decorators = {"post": [limiter.limit("60 per minute")]}

    @require_customer
    def post(self, slug: str, lesson_slug: str):
        data = learning.complete_lesson(
            current_customer(), learning.learner_course_by_slug(slug), lesson_slug
        )
        db.session.commit()
        return success(data)


class LearningExerciseResource(Resource):
    method_decorators = {"put": [limiter.limit("60 per minute")]}

    @require_customer
    def put(self, slug: str, lesson_slug: str, exercise_id: str):
        data = learning.save_exercise(
            current_customer(),
            learning.learner_course_by_slug(slug),
            lesson_slug,
            exercise_id,
            _body(),
        )
        db.session.commit()
        return success(data)


class LearningAssessmentResource(Resource):
    @require_customer
    def get(self, slug: str, assessment_id: int):
        data = learning.assessment_view(
            current_customer(), learning.learner_course_by_slug(slug), assessment_id
        )
        db.session.commit()
        return success(data)


class LearningAttemptResource(Resource):
    method_decorators = {"post": [limiter.limit("20 per minute")]}

    @require_customer
    def post(self, slug: str, assessment_id: int):
        data = learning.submit_assessment(
            current_customer(),
            learning.learner_course_by_slug(slug),
            assessment_id,
            _body().get("answers"),
        )
        db.session.commit()
        return success(data, status=201)


class LearningCertificateResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self, slug: str):
        customer = current_customer()
        course = learning.learner_course_by_slug(slug)
        enrollment = learning.require_access(customer, course)
        certificate = certificates.issue(enrollment, _body().get("name"))
        db.session.commit()
        return success(certificates.verify_dict(certificate), status=201)


class LearningCertificatePdfResource(Resource):
    @require_customer
    def get(self, code: str):
        certificate = certificates.get_by_code(code)
        if certificate.customer_id != current_customer().id:
            raise NotFoundError("Certificate not found.")
        pdf = certificates.render_pdf(certificate)
        response = Response(pdf, mimetype="application/pdf")
        response.headers["Content-Disposition"] = (
            f'attachment; filename="certificate-{certificate.code.lower()}.pdf"'
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


PUBLIC_COURSE_ROUTES = [
    (CourseListResource, "/courses"),
    (CourseDetailResource, "/courses/<string:slug>"),
    (CoursePreviewLessonResource, "/courses/<string:slug>/preview/<string:lesson_slug>"),
    (CertificateVerifyResource, "/certificates/<string:code>"),
    (LearningResource, "/account/learning"),
    (LearningStatusResource, "/account/learning/<string:slug>/status"),
    (LearningEnrollResource, "/account/learning/<string:slug>/enroll"),
    (LearningCourseResource, "/account/learning/<string:slug>"),
    (LearningLessonResource, "/account/learning/<string:slug>/lessons/<string:lesson_slug>"),
    (
        LearningLessonCompleteResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/complete",
    ),
    (
        LearningExerciseResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/exercises/<string:exercise_id>",
    ),
    (LearningAssessmentResource, "/account/learning/<string:slug>/assessments/<int:assessment_id>"),
    (
        LearningAttemptResource,
        "/account/learning/<string:slug>/assessments/<int:assessment_id>/attempts",
    ),
    (LearningCertificateResource, "/account/learning/<string:slug>/certificate"),
    (LearningCertificatePdfResource, "/account/certificates/<string:code>/pdf"),
]

# Certificate checks are public but never cached or indexed (they contain a name).
COURSE_PRIVATE_PREFIXES = ("/api/v1/certificates",)
