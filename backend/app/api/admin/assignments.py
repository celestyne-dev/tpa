"""Admin API for written assignments, rubrics, assessors, exceptions, submissions and
grading (/api/v1/admin/…, Batch 09.2).

Every resource requires an authenticated staff user with ``assignments.view``; the
services then check the specific permission (manage, view submissions, grade, publish
grades, manage exceptions, view reports) and, for submissions, the assessor scope.
"""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...services.courses import admin as course_admin
from ...services.courses import assignment_admin as defs
from ...services.courses import grading
from ...utils.errors import ValidationError
from ...utils.responses import success

VIEW = require_permission(P.ASSIGNMENTS_VIEW)


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _assignment(course_id: int, assignment_id: str):
    course = course_admin.get_course(course_id)
    return course, defs.get_assignment(course, assignment_id)


class AssignmentListResource(Resource):
    @VIEW
    def get(self, course_id: int):
        course = course_admin.get_course(course_id)
        return success(defs.list_assignments(course, current_user))

    @VIEW
    def post(self, course_id: int):
        course = course_admin.get_course(course_id)
        assignment = defs.create(course, _body(), current_user)
        db.session.commit()
        return success(defs.assignment_dict(assignment), status=201)


class AssignmentResource(Resource):
    @VIEW
    def get(self, course_id: int, assignment_id: str):
        _, assignment = _assignment(course_id, assignment_id)
        return success(defs.assignment_dict(assignment))

    @VIEW
    def patch(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        defs.update(course, assignment, _body(), current_user)
        db.session.commit()
        return success(defs.assignment_dict(assignment))

    @VIEW
    def delete(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        defs.delete(course, assignment, current_user)
        db.session.commit()
        return success({"deleted": True})


class AssignmentStatusResource(Resource):
    @VIEW
    def post(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        defs.set_status(course, assignment, _body().get("status"), current_user)
        db.session.commit()
        return success(defs.assignment_dict(assignment))


class AssignmentRubricResource(Resource):
    @VIEW
    def get(self, course_id: int, assignment_id: str):
        _, assignment = _assignment(course_id, assignment_id)
        return success(defs.rubric_history(assignment, current_user))

    @VIEW
    def put(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        rubric = defs.save_rubric(course, assignment, _body(), current_user)
        db.session.commit()
        return success(
            {"rubric": defs.rubric_dict(rubric), "assignment": defs.assignment_dict(assignment)}
        )


class AssessorsResource(Resource):
    @VIEW
    def get(self, course_id: int):
        return success(defs.assessors(course_admin.get_course(course_id), current_user))

    @VIEW
    def put(self, course_id: int):
        course = course_admin.get_course(course_id)
        data = defs.set_assessors(course, _body().get("user_ids"), current_user)
        db.session.commit()
        return success(data)


class ExceptionListResource(Resource):
    @VIEW
    def get(self, course_id: int, assignment_id: str):
        _, assignment = _assignment(course_id, assignment_id)
        return success(defs.list_exceptions(assignment, current_user))

    @VIEW
    def post(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        row = defs.grant_exception(course, assignment, _body(), current_user)
        db.session.commit()
        return success(defs.exception_dict(row), status=201)


class ExceptionRevokeResource(Resource):
    @VIEW
    def post(self, course_id: int, assignment_id: str, exception_id: int):
        course, assignment = _assignment(course_id, assignment_id)
        row = defs.revoke_exception(course, assignment, exception_id, current_user)
        db.session.commit()
        return success(defs.exception_dict(row))


class AssignmentReportResource(Resource):
    @VIEW
    def get(self, course_id: int, assignment_id: str):
        course, assignment = _assignment(course_id, assignment_id)
        return success(defs.report(course, assignment, current_user))


class SubmissionListResource(Resource):
    @VIEW
    def get(self, course_id: int, assignment_id: str):
        _, assignment = _assignment(course_id, assignment_id)
        status = (request.args.get("status") or "")[:30] or None
        return success(grading.list_submissions(assignment, current_user, status))


class SubmissionResource(Resource):
    @VIEW
    def get(self, submission_id: str):
        submission = grading.get_submission(submission_id, current_user)
        return success(grading.submission_detail(submission, current_user))


class SubmissionReviewResource(Resource):
    @VIEW
    def post(self, submission_id: str):
        submission = grading.get_submission(submission_id, current_user)
        grading.start_review(submission, _body(), current_user)
        db.session.commit()
        return success(grading.submission_detail(submission, current_user))


class AttemptGradeResource(Resource):
    @VIEW
    def put(self, attempt_id: str):
        attempt = grading.get_attempt(attempt_id, current_user)
        grade = grading.save_grade(attempt, _body(), current_user)
        db.session.commit()
        return success(grading.staff_grade(grade))


class AttemptGradeActionResource(Resource):
    @VIEW
    def post(self, attempt_id: str, action: str):
        attempt = grading.get_attempt(attempt_id, current_user)
        if action == "publish":
            grade = grading.publish_grade(attempt, _body(), current_user)
        elif action == "retract":
            grade = grading.retract_grade(attempt, _body(), current_user)
        else:
            from ...utils.errors import NotFoundError

            raise NotFoundError()
        db.session.commit()
        return success(grading.staff_grade(grade))


class SubmissionFileResource(Resource):
    @VIEW
    def get(self, file_id: str):
        return grading.download_for_staff(file_id, current_user)


ASSIGNMENT_ADMIN_ROUTES = [
    (AssignmentListResource, "/admin/courses/<int:course_id>/assignments"),
    (AssessorsResource, "/admin/courses/<int:course_id>/assessors"),
    (AssignmentResource, "/admin/courses/<int:course_id>/assignments/<string:assignment_id>"),
    (
        AssignmentStatusResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/status",
    ),
    (
        AssignmentRubricResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/rubric",
    ),
    (
        ExceptionListResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/exceptions",
    ),
    (
        ExceptionRevokeResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/exceptions/"
        "<int:exception_id>/revoke",
    ),
    (
        AssignmentReportResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/report",
    ),
    (
        SubmissionListResource,
        "/admin/courses/<int:course_id>/assignments/<string:assignment_id>/submissions",
    ),
    (SubmissionResource, "/admin/assignment-submissions/<string:submission_id>"),
    (SubmissionReviewResource, "/admin/assignment-submissions/<string:submission_id>/review"),
    (AttemptGradeResource, "/admin/assignment-attempts/<string:attempt_id>/grade"),
    (
        AttemptGradeActionResource,
        "/admin/assignment-attempts/<string:attempt_id>/grade/<string:action>",
    ),
    (SubmissionFileResource, "/admin/assignment-files/<string:file_id>/download"),
]
