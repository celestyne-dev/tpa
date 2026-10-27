"""Admin API for courses (/api/v1/admin/courses…).

Every resource requires ``courses.view``; the services then check the specific
permission each action needs (create, edit, publish, archive, curriculum, assessments,
enrolments, reports), so hiding a button in the admin is never the only protection.
"""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource
from sqlalchemy import select

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Author, CourseCategory, Product, Topic
from ...services.courses import admin as course_admin
from ...services.courses import (
    assessments,
    certificates,
    curriculum,
    enrollments,
    public,
    revisions,
)
from ...utils.errors import NotFoundError, ValidationError
from ...utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _page_args() -> dict:
    args = {k: v for k, v in request.args.items() if len(v) <= 120}
    for name, default, high in (("page", 1, 10000), ("page_size", 25, 100)):
        raw = request.args.get(name)
        try:
            args[name] = max(1, min(high, int(raw))) if raw not in (None, "") else default
        except ValueError:
            raise ValidationError(details={name: ["Must be a number."]}) from None
    return args


def _course(course_id: int):
    return course_admin.get_course(course_id)


def _detail(course):
    return course_admin.course_detail(course, current_user)


class CourseListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self):
        items, meta = course_admin.list_courses(_page_args())
        return success(items, meta | {"can": course_admin.can(current_user)})

    @require_permission(P.COURSES_VIEW)
    def post(self):
        course = course_admin.create(_body(), current_user)
        db.session.commit()
        return success(_detail(course), status=201)


class CourseOptionsResource(Resource):
    """Choices for the course form: categories, authors, topics and course products."""

    @require_permission(P.COURSES_VIEW)
    def get(self):
        linked = {
            pid
            for pid in db.session.scalars(
                select(course_admin.Course.product_id).where(
                    course_admin.Course.product_id.is_not(None)
                )
            )
        }
        return success(
            {
                "categories": course_admin.list_categories(),
                "authors": [
                    {"id": a.id, "name": a.display_name}
                    for a in db.session.scalars(
                        select(Author)
                        .where(Author.status == "active")
                        .order_by(Author.display_name)
                    )
                ],
                "topics": [
                    {"id": t.id, "name": t.name}
                    for t in db.session.scalars(
                        select(Topic).where(Topic.status == "active").order_by(Topic.name)
                    )
                ],
                "products": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "status": p.status,
                        "pricing_model": p.pricing_model,
                        "linked": p.id in linked,
                    }
                    for p in db.session.scalars(
                        select(Product)
                        .where(Product.product_type == "course", Product.status != "archived")
                        .order_by(Product.title)
                    )
                ],
                "levels": ["beginner", "intermediate", "advanced", "all_levels"],
            }
        )


class CourseReportsResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self):
        return success(enrollments.reports(current_user))


class CourseResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int):
        return success(_detail(_course(course_id)))

    @require_permission(P.COURSES_VIEW)
    def patch(self, course_id: int):
        course = course_admin.update(_course(course_id), _body(), current_user)
        db.session.commit()
        return success(_detail(course))

    @require_permission(P.COURSES_VIEW)
    def delete(self, course_id: int):
        course_admin.delete(_course(course_id), current_user)
        db.session.commit()
        return success({"deleted": True})


class CourseActionResource(Resource):
    ACTIONS = {
        "publish": lambda c, body: course_admin.publish(c, body, current_user),
        "unpublish": lambda c, body: course_admin.unpublish(c, current_user),
        "archive": lambda c, body: course_admin.archive(c, current_user),
        "restore": lambda c, body: course_admin.restore(c, current_user),
    }

    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, action: str):
        course = _course(course_id)
        if action == "duplicate":
            copy = course_admin.duplicate(course, current_user)
            db.session.commit()
            return success(_detail(copy), status=201)
        handler = self.ACTIONS.get(action)
        if handler is None:
            raise NotFoundError("Unknown action.")
        handler(course, request.get_json(silent=True) or {})
        db.session.commit()
        return success(_detail(course))


class CoursePreviewResource(Resource):
    """Private preview of a course page as it would look (drafts included)."""

    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int):
        return success(public.course_detail(_course(course_id), preview=True))


class CourseReportResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int):
        return success(enrollments.reports(current_user, _course(course_id)))


# ---- categories -------------------------------------------------------------------------


class CourseCategoryListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self):
        return success(course_admin.list_categories())

    @require_permission(P.COURSES_VIEW)
    def post(self):
        category = course_admin.save_category(_body(), current_user)
        db.session.commit()
        return success(course_admin.category_dict(category), status=201)


class CourseCategoryResource(Resource):
    def _get(self, category_id: int) -> CourseCategory:
        category = db.session.get(CourseCategory, category_id)
        if category is None:
            raise NotFoundError("Category not found.")
        return category

    @require_permission(P.COURSES_VIEW)
    def patch(self, category_id: int):
        category = course_admin.save_category(_body(), current_user, self._get(category_id))
        db.session.commit()
        return success(course_admin.category_dict(category))

    @require_permission(P.COURSES_VIEW)
    def delete(self, category_id: int):
        course_admin.delete_category(self._get(category_id), current_user)
        db.session.commit()
        return success({"deleted": True})


# ---- curriculum -------------------------------------------------------------------------


class ModuleListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int):
        course = _course(course_id)
        curriculum.save_module(course, _body(), current_user)
        db.session.commit()
        return success(curriculum.curriculum(course), status=201)


class ModuleResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def patch(self, course_id: int, module_id: int):
        course = _course(course_id)
        curriculum.save_module(
            course, _body(), current_user, curriculum.get_module(course, module_id)
        )
        db.session.commit()
        return success(curriculum.curriculum(course))

    @require_permission(P.COURSES_VIEW)
    def delete(self, course_id: int, module_id: int):
        course = _course(course_id)
        curriculum.delete_module(course, curriculum.get_module(course, module_id), current_user)
        db.session.commit()
        return success(curriculum.curriculum(course))


class CurriculumOrderResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def put(self, course_id: int):
        course = _course(course_id)
        curriculum.reorder(course, _body().get("layout"), current_user)
        db.session.commit()
        return success(curriculum.curriculum(course))


class LessonListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, module_id: int):
        course = _course(course_id)
        lesson = curriculum.save_lesson(
            course, _body(), current_user, module=curriculum.get_module(course, module_id)
        )
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson), status=201)


class LessonResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        course_admin.require(current_user, P.COURSES_VIEW_DRAFTS)
        return success(curriculum.lesson_detail(course, curriculum.get_lesson(course, lesson_id)))

    @require_permission(P.COURSES_VIEW)
    def patch(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.save_lesson(
            course, _body(), current_user, lesson=curriculum.get_lesson(course, lesson_id)
        )
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson))

    @require_permission(P.COURSES_VIEW)
    def delete(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        curriculum.delete_lesson(course, curriculum.get_lesson(course, lesson_id), current_user)
        db.session.commit()
        return success(curriculum.curriculum(course))


class LessonStatusResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        curriculum.set_lesson_status(course, lesson, _body().get("status"), current_user)
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson))


class LessonPublishResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        body = request.get_json(silent=True) or {}
        revisions.publish(course, lesson, current_user, note=body.get("note") or "")
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson))


class LessonDiscardDraftResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        revisions.discard_draft(course, lesson, _body(), current_user)
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson))


class LessonRevisionListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        return success(revisions.history(lesson, current_user))


class LessonRevisionResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, lesson_id: int, number: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        return success(revisions.revision_detail(lesson, number, current_user))


class LessonRevisionRestoreResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, lesson_id: int, number: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        revisions.restore(course, lesson, number, _body(), current_user)
        db.session.commit()
        return success(curriculum.lesson_detail(course, lesson))


class LessonCompareResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, lesson_id: int):
        course = _course(course_id)
        lesson = curriculum.get_lesson(course, lesson_id)
        left = (request.args.get("left") or "live")[:20]
        right = (request.args.get("right") or "draft")[:20]
        return success(revisions.compare(lesson, left, right, current_user))


# ---- assessments ------------------------------------------------------------------------


class AssessmentListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int):
        course = _course(course_id)
        return success([assessments.assessment_summary(a) for a in course.assessments])

    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int):
        course = _course(course_id)
        assessment = assessments.save_assessment(course, _body(), current_user)
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user), status=201)


class AssessmentOrderResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def put(self, course_id: int):
        course = _course(course_id)
        assessments.reorder_assessments(course, _body().get("ids"), current_user)
        db.session.commit()
        return success([assessments.assessment_summary(a) for a in course.assessments])


class AssessmentResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, assessment_id: int):
        course = _course(course_id)
        return success(
            assessments.assessment_admin_detail(
                assessments.get_assessment(course, assessment_id), current_user
            )
        )

    @require_permission(P.COURSES_VIEW)
    def patch(self, course_id: int, assessment_id: int):
        course = _course(course_id)
        assessment = assessments.save_assessment(
            course, _body(), current_user, assessments.get_assessment(course, assessment_id)
        )
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user))

    @require_permission(P.COURSES_VIEW)
    def delete(self, course_id: int, assessment_id: int):
        course = _course(course_id)
        assessments.delete_assessment(
            course, assessments.get_assessment(course, assessment_id), current_user
        )
        db.session.commit()
        return success({"deleted": True})


class AssessmentAttemptsResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, assessment_id: int):
        course = _course(course_id)
        assessment = assessments.get_assessment(course, assessment_id)
        return success(assessments.staff_attempts(assessment, current_user))


class AssessmentStatusResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, assessment_id: int):
        course = _course(course_id)
        assessment = assessments.get_assessment(course, assessment_id)
        assessments.set_assessment_status(course, assessment, _body().get("status"), current_user)
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user))


class QuestionListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, assessment_id: int):
        assessment = assessments.get_assessment(_course(course_id), assessment_id)
        assessments.save_question(assessment, _body(), current_user)
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user), status=201)


class QuestionOrderResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def put(self, course_id: int, assessment_id: int):
        assessment = assessments.get_assessment(_course(course_id), assessment_id)
        assessments.reorder_questions(assessment, _body().get("ids"), current_user)
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user))


class QuestionResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def patch(self, course_id: int, assessment_id: int, question_id: int):
        assessment = assessments.get_assessment(_course(course_id), assessment_id)
        assessments.save_question(
            assessment, _body(), current_user, assessments.get_question(assessment, question_id)
        )
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user))

    @require_permission(P.COURSES_VIEW)
    def delete(self, course_id: int, assessment_id: int, question_id: int):
        assessment = assessments.get_assessment(_course(course_id), assessment_id)
        assessments.delete_question(
            assessment, assessments.get_question(assessment, question_id), current_user
        )
        db.session.commit()
        return success(assessments.assessment_admin_detail(assessment, current_user))


# ---- enrolments and certificates --------------------------------------------------------


class EnrollmentListResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int):
        items, meta = enrollments.list_enrollments(_course(course_id), _page_args(), current_user)
        return success(items, meta)

    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int):
        course = _course(course_id)
        enrollment = enrollments.manual_enroll(course, _body(), current_user)
        db.session.commit()
        return success(enrollments.enrollment_detail(course, enrollment, current_user), status=201)


class EnrollmentResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def get(self, course_id: int, enrollment_id: int):
        course = _course(course_id)
        return success(
            enrollments.enrollment_detail(
                course, enrollments.get_enrollment(course, enrollment_id), current_user
            )
        )


class EnrollmentActionResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, course_id: int, enrollment_id: int, action: str):
        course = _course(course_id)
        enrollment = enrollments.get_enrollment(course, enrollment_id)
        if action == "revoke":
            enrollments.revoke_enrollment(course, enrollment, _body(), current_user)
        elif action == "restore":
            enrollment = enrollments.restore_enrollment(course, enrollment, _body(), current_user)
        else:
            raise NotFoundError("Unknown action.")
        db.session.commit()
        return success(enrollments.enrollment_detail(course, enrollment, current_user))


class CertificateActionResource(Resource):
    @require_permission(P.COURSES_VIEW)
    def post(self, code: str, action: str):
        certificate = certificates.get_by_code(code)
        body = _body()
        if action == "revoke":
            certificates.revoke(certificate, body.get("reason"), current_user)
        elif action == "reinstate":
            certificates.reinstate(certificate, body.get("reason"), current_user)
        elif action == "correct":
            certificates.correct(certificate, body, current_user)
        else:
            raise NotFoundError("Unknown action.")
        db.session.commit()
        return success(certificates.admin_dict(certificate))


COURSE_ADMIN_ROUTES = [
    (CourseListResource, "/admin/courses"),
    (CourseOptionsResource, "/admin/courses/options"),
    (CourseReportsResource, "/admin/courses/reports"),
    (CourseCategoryListResource, "/admin/course-categories"),
    (CourseCategoryResource, "/admin/course-categories/<int:category_id>"),
    (CourseResource, "/admin/courses/<int:course_id>"),
    (
        CourseActionResource,
        "/admin/courses/<int:course_id>/<string:action>",
    ),
    (CoursePreviewResource, "/admin/courses/<int:course_id>/preview"),
    (CourseReportResource, "/admin/courses/<int:course_id>/reports"),
    (ModuleListResource, "/admin/courses/<int:course_id>/modules"),
    (ModuleResource, "/admin/courses/<int:course_id>/modules/<int:module_id>"),
    (CurriculumOrderResource, "/admin/courses/<int:course_id>/curriculum"),
    (LessonListResource, "/admin/courses/<int:course_id>/modules/<int:module_id>/lessons"),
    (LessonResource, "/admin/courses/<int:course_id>/lessons/<int:lesson_id>"),
    (LessonStatusResource, "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/status"),
    (LessonPublishResource, "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/publish"),
    (
        LessonDiscardDraftResource,
        "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/discard-draft",
    ),
    (
        LessonRevisionListResource,
        "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/revisions",
    ),
    (
        LessonRevisionResource,
        "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/revisions/<int:number>",
    ),
    (
        LessonRevisionRestoreResource,
        "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/revisions/<int:number>/restore",
    ),
    (LessonCompareResource, "/admin/courses/<int:course_id>/lessons/<int:lesson_id>/compare"),
    (AssessmentListResource, "/admin/courses/<int:course_id>/assessments"),
    (AssessmentOrderResource, "/admin/courses/<int:course_id>/assessments/order"),
    (AssessmentResource, "/admin/courses/<int:course_id>/assessments/<int:assessment_id>"),
    (
        AssessmentStatusResource,
        "/admin/courses/<int:course_id>/assessments/<int:assessment_id>/status",
    ),
    (
        AssessmentAttemptsResource,
        "/admin/courses/<int:course_id>/assessments/<int:assessment_id>/attempts",
    ),
    (
        QuestionListResource,
        "/admin/courses/<int:course_id>/assessments/<int:assessment_id>/questions",
    ),
    (
        QuestionOrderResource,
        "/admin/courses/<int:course_id>/assessments/<int:assessment_id>/questions/order",
    ),
    (
        QuestionResource,
        "/admin/courses/<int:course_id>/assessments/<int:assessment_id>/questions/<int:question_id>",
    ),
    (EnrollmentListResource, "/admin/courses/<int:course_id>/enrollments"),
    (EnrollmentResource, "/admin/courses/<int:course_id>/enrollments/<int:enrollment_id>"),
    (
        EnrollmentActionResource,
        "/admin/courses/<int:course_id>/enrollments/<int:enrollment_id>/<string:action>",
    ),
    (
        CertificateActionResource,
        "/admin/certificates/<string:code>/<string:action>",
    ),
]
