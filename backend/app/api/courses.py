"""Public course catalogue, certificate verification and the learner API.

- ``/courses``…: published catalogue data only (prerendered; never lesson content except
  lessons marked as free previews).
- ``/account/learning``…: signed-in customers with a confirmed email; every request
  re-checks enrolment and access (refunds, revocation and expiry apply at once).
- ``/certificates/<code>``: anyone can check a certificate code (no-store, noindex).
- ``/learning/search``: course search; anonymous visitors get catalogue data and free
  previews, signed-in learners also the lessons they can open (decided server-side).
- ``/account/study``… and lesson study routes (Batch 09.1): the learner's own notes,
  highlights, bookmarks, checklist ticks, reading position and preferences.
- ``…/assessments/<id>/attempts/…`` and ``…/assessment-history`` (Batch 09.2 phase 2):
  started (drawn, shuffled or timed) attempts, autosave, submission and attempt history.
"""

from __future__ import annotations

from flask import Response, request
from flask_restful import Resource

from ..auth.customer_session import current_customer, require_customer
from ..extensions import db, limiter
from ..services.courses import certificates, learning, public, search, study, submissions
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


class LearningAttemptStartResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self, slug: str, assessment_id: int):
        data, created = learning.start_assessment(
            current_customer(), learning.learner_course_by_slug(slug), assessment_id
        )
        db.session.commit()
        return success(data, status=201 if created else 200)


class LearningAttemptDetailResource(Resource):
    method_decorators = {"put": [limiter.limit("60 per minute")]}

    @require_customer
    def get(self, slug: str, assessment_id: int, attempt_id: int):
        data = learning.attempt_view(
            current_customer(), learning.learner_course_by_slug(slug), assessment_id, attempt_id
        )
        db.session.commit()
        return success(data)

    @require_customer
    def put(self, slug: str, assessment_id: int, attempt_id: int):
        data = learning.save_attempt(
            current_customer(),
            learning.learner_course_by_slug(slug),
            assessment_id,
            attempt_id,
            _body().get("answers"),
        )
        db.session.commit()
        return success(data)


class LearningAttemptSubmitResource(Resource):
    method_decorators = {"post": [limiter.limit("20 per minute")]}

    @require_customer
    def post(self, slug: str, assessment_id: int, attempt_id: int):
        data = learning.submit_attempt(
            current_customer(),
            learning.learner_course_by_slug(slug),
            assessment_id,
            attempt_id,
            _body().get("answers"),
        )
        db.session.commit()
        return success(data)


class LearningAssessmentHistoryResource(Resource):
    @require_customer
    def get(self, slug: str, assessment_id: int):
        data = learning.assessment_history(
            current_customer(), learning.learner_course_by_slug(slug), assessment_id
        )
        db.session.commit()
        return success(data)


class LearningCourseHistoryResource(Resource):
    @require_customer
    def get(self, slug: str):
        data = learning.assessment_history(
            current_customer(), learning.learner_course_by_slug(slug)
        )
        db.session.commit()
        return success(data)


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


# ---- search and study tools (Batch 09.1) --------------------------------------------------


class LearningSearchResource(Resource):
    decorators = [limiter.limit("30 per minute")]

    def get(self):
        customer = current_customer()
        data = search.search(request.args.get("q", ""), customer)
        db.session.commit()
        return success(data)


def _lesson_args(slug: str):
    return current_customer(), learning.learner_course_by_slug(slug)


class LessonNotesResource(Resource):
    method_decorators = {"post": [limiter.limit("60 per minute")]}

    @require_customer
    def post(self, slug: str, lesson_slug: str):
        customer, course = _lesson_args(slug)
        data = study.create_note(customer, course, lesson_slug, _body())
        db.session.commit()
        return success(data, status=201)


class LessonHighlightsResource(Resource):
    method_decorators = {"post": [limiter.limit("60 per minute")]}

    @require_customer
    def post(self, slug: str, lesson_slug: str):
        customer, course = _lesson_args(slug)
        data = study.create_highlight(customer, course, lesson_slug, _body())
        db.session.commit()
        return success(data, status=201)


class LessonBookmarkResource(Resource):
    method_decorators = {"put": [limiter.limit("60 per minute")]}

    @require_customer
    def put(self, slug: str, lesson_slug: str):
        customer, course = _lesson_args(slug)
        data = study.set_bookmark(customer, course, lesson_slug, _body().get("bookmarked"))
        db.session.commit()
        return success(data)


class LessonChecklistResource(Resource):
    method_decorators = {"put": [limiter.limit("120 per minute")]}

    @require_customer
    def put(self, slug: str, lesson_slug: str, item_id: str):
        customer, course = _lesson_args(slug)
        data = study.set_checklist_item(customer, course, lesson_slug, item_id, _body())
        db.session.commit()
        return success(data)


class LessonPositionResource(Resource):
    # The reader saves at most every few seconds; this limit only stops abuse.
    method_decorators = {"put": [limiter.limit("30 per minute")]}

    @require_customer
    def put(self, slug: str, lesson_slug: str):
        customer, course = _lesson_args(slug)
        data = study.save_position(customer, course, lesson_slug, _body())
        db.session.commit()
        return success(data)


class StudyNoteResource(Resource):
    method_decorators = {
        "patch": [limiter.limit("120 per minute")],
        "delete": [limiter.limit("60 per minute")],
    }

    @require_customer
    def patch(self, note_id: str):
        data = study.update_note(current_customer(), note_id, _body())
        db.session.commit()
        return success(data)

    @require_customer
    def delete(self, note_id: str):
        study.delete_note(current_customer(), note_id)
        db.session.commit()
        return success({"deleted": True})


class StudyHighlightResource(Resource):
    method_decorators = {
        "patch": [limiter.limit("60 per minute")],
        "delete": [limiter.limit("60 per minute")],
    }

    @require_customer
    def patch(self, highlight_id: str):
        data = study.update_highlight(current_customer(), highlight_id, _body())
        db.session.commit()
        return success(data)

    @require_customer
    def delete(self, highlight_id: str):
        study.delete_highlight(current_customer(), highlight_id)
        db.session.commit()
        return success({"deleted": True})


class StudyNotebookResource(Resource):
    decorators = [limiter.limit("60 per minute")]

    @require_customer
    def get(self):
        args = {k: v for k, v in request.args.items() if len(v) <= 120}
        data = study.notebook(current_customer(), args)
        db.session.commit()
        return success(data)


class StudyExportResource(Resource):
    decorators = [limiter.limit("10 per minute")]

    @require_customer
    def get(self):
        payload, mimetype, filename = study.export(
            current_customer(),
            request.args.get("format", "txt"),
            (request.args.get("course") or "")[:200] or None,
        )
        response = Response(payload, mimetype=mimetype)
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


class StudyPreferencesResource(Resource):
    method_decorators = {"put": [limiter.limit("30 per minute")]}

    @require_customer
    def get(self):
        return success(study.get_preferences(current_customer()))

    @require_customer
    def put(self):
        data = study.save_preferences(current_customer(), _body())
        db.session.commit()
        return success(data)


# ---- written assignments (Batch 09.2) -------------------------------------------------------


class LearnerAssignmentListResource(Resource):
    @require_customer
    def get(self, slug: str):
        data = submissions.list_for_learner(
            current_customer(), learning.learner_course_by_slug(slug)
        )
        db.session.commit()
        return success(data)


class LearnerAssignmentResource(Resource):
    @require_customer
    def get(self, slug: str, assignment_id: str):
        data = submissions.get_for_learner(
            current_customer(), learning.learner_course_by_slug(slug), assignment_id
        )
        db.session.commit()
        return success(data)


class LearnerAssignmentDraftResource(Resource):
    method_decorators = {"put": [limiter.limit("60 per minute")]}

    @require_customer
    def put(self, slug: str, assignment_id: str):
        data = submissions.save_draft(
            current_customer(), learning.learner_course_by_slug(slug), assignment_id, _body()
        )
        db.session.commit()
        return success(data)


class LearnerAssignmentSubmitResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self, slug: str, assignment_id: str):
        data, created = submissions.submit(
            current_customer(), learning.learner_course_by_slug(slug), assignment_id, _body()
        )
        db.session.commit()
        return success(data, status=201 if created else 200)


class LearnerAssignmentFilesResource(Resource):
    method_decorators = {"post": [limiter.limit("20 per hour")]}

    @require_customer
    def post(self, slug: str, assignment_id: str):
        data = submissions.upload(
            current_customer(),
            learning.learner_course_by_slug(slug),
            assignment_id,
            request.files.get("file"),
        )
        db.session.commit()
        return success(data, status=201)


class LearnerAssignmentFileResource(Resource):
    method_decorators = {"delete": [limiter.limit("30 per minute")]}

    @require_customer
    def delete(self, file_id: str):
        submissions.remove_file(current_customer(), file_id)
        db.session.commit()
        return success({"deleted": True})


class LearnerAssignmentFileDownloadResource(Resource):
    decorators = [limiter.limit("60 per minute")]

    @require_customer
    def get(self, file_id: str):
        return submissions.download_for_learner(current_customer(), file_id)


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
    (
        LearningAttemptStartResource,
        "/account/learning/<string:slug>/assessments/<int:assessment_id>/attempts/start",
    ),
    (
        LearningAttemptDetailResource,
        "/account/learning/<string:slug>/assessments/<int:assessment_id>/attempts/<int:attempt_id>",
    ),
    (
        LearningAttemptSubmitResource,
        "/account/learning/<string:slug>/assessments/<int:assessment_id>/attempts/"
        "<int:attempt_id>/submit",
    ),
    (
        LearningAssessmentHistoryResource,
        "/account/learning/<string:slug>/assessments/<int:assessment_id>/history",
    ),
    (LearningCourseHistoryResource, "/account/learning/<string:slug>/assessment-history"),
    (LearningCertificateResource, "/account/learning/<string:slug>/certificate"),
    (LearningCertificatePdfResource, "/account/certificates/<string:code>/pdf"),
    (LearningSearchResource, "/learning/search"),
    (LessonNotesResource, "/account/learning/<string:slug>/lessons/<string:lesson_slug>/notes"),
    (
        LessonHighlightsResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/highlights",
    ),
    (
        LessonBookmarkResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/bookmark",
    ),
    (
        LessonChecklistResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/checklist/<string:item_id>",
    ),
    (
        LessonPositionResource,
        "/account/learning/<string:slug>/lessons/<string:lesson_slug>/position",
    ),
    (StudyNoteResource, "/account/study/notes/<string:note_id>"),
    (StudyHighlightResource, "/account/study/highlights/<string:highlight_id>"),
    (StudyNotebookResource, "/account/study/notebook"),
    (StudyExportResource, "/account/study/export"),
    (StudyPreferencesResource, "/account/study/preferences"),
    (LearnerAssignmentListResource, "/account/learning/<string:slug>/assignments"),
    (
        LearnerAssignmentResource,
        "/account/learning/<string:slug>/assignments/<string:assignment_id>",
    ),
    (
        LearnerAssignmentDraftResource,
        "/account/learning/<string:slug>/assignments/<string:assignment_id>/draft",
    ),
    (
        LearnerAssignmentSubmitResource,
        "/account/learning/<string:slug>/assignments/<string:assignment_id>/submit",
    ),
    (
        LearnerAssignmentFilesResource,
        "/account/learning/<string:slug>/assignments/<string:assignment_id>/files",
    ),
    (LearnerAssignmentFileResource, "/account/assignment-files/<string:file_id>"),
    (LearnerAssignmentFileDownloadResource, "/account/assignment-files/<string:file_id>/download"),
]

# Certificate checks are public but never cached or indexed (they contain a name).
# Search results depend on who is signed in, so they are never cached either.
COURSE_PRIVATE_PREFIXES = ("/api/v1/certificates", "/api/v1/learning")
