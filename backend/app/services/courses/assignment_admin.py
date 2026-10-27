"""Assignment definitions, rubrics, course assessors, exceptions and reports (Batch 09.2).

Staff authorisation is always checked here (``require``), never only in the UI:

- ``assignments.view``: list and read assignment definitions;
- ``assignments.manage``: create, edit, publish, archive, rubrics, course assessors;
- ``assignments.manage_exceptions``: deadline extensions / extra attempts per learner;
- ``assignments.view_reports``: assignment reports.

Deadlines are stored in UTC. Inputs must be ISO 8601 with an explicit offset or ``Z``
(a date-time without a timezone is refused, so a deadline never shifts with the server's
local time).

Completion policy (versioned by publication time): a published, *required* assignment
counts towards completion for every enrolment that has not completed the course yet. Its
``required_since`` records when that started. Enrolments that already completed keep
their completion and certificates — new or changed assignment rules never revoke them.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...extensions import db
from ...models import (
    AssignmentException,
    AssignmentGrade,
    AssignmentRubric,
    AssignmentSubmission,
    Course,
    CourseAssessor,
    CourseAssignment,
    CourseEnrollment,
    CourseLesson,
    User,
)
from ...models.assignments import ASSIGNMENT_KINDS, LATE_POLICIES, RESUBMISSION_POLICIES
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from .admin import require

MAX_PROMPTS = 10
MAX_CRITERIA = 20
MAX_DESCRIPTORS = 6
FILE_RULES = ("none", "optional", "required")


class EditConflictError(ConflictError):
    code = "edit_conflict"
    message = "Someone else changed this after you opened it. Reload and try again."


def _now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return secrets.token_urlsafe(12)


def granted(actor: User, perm: P) -> bool:
    return perm.value in effective_permissions(actor)


def check_lock(row: Any, data: dict[str, Any]) -> None:
    version = data.get("lock_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(details={"lock_version": ["Reload before saving (missing version)."]})
    if version != row.lock_version:
        raise EditConflictError(details={"lock_version": row.lock_version})


def parse_datetime(value: Any, field: str, errors: dict) -> datetime | None:
    """ISO 8601 with an explicit timezone, stored as UTC. None/"" clears the value."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 40:
        errors[field] = ["Use an ISO 8601 date and time with a timezone."]
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        errors[field] = ["Use an ISO 8601 date and time with a timezone."]
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors[field] = ["Include a timezone (for example 2026-11-30T23:59:00-05:00)."]
        return None
    return parsed.astimezone(UTC)


def _text(data: dict, field: str, limit: int, errors: dict, *, required: bool = False):
    value = data.get(field)
    if value is None:
        if required:
            errors[field] = ["This field is required."]
        return None
    if not isinstance(value, str):
        errors[field] = ["Must be text."]
        return None
    value = value.strip()
    if required and not value:
        errors[field] = ["This field is required."]
    elif len(value) > limit:
        errors[field] = [f"At most {limit} characters."]
    elif problem := plain_text_problem(value):
        errors[field] = [problem]
    return value


def _int(data: dict, field: str, low: int, high: int, errors: dict) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        errors[field] = [f"Use a whole number from {low} to {high}."]
        return None
    return value


# ---- lookups ------------------------------------------------------------------------------


def get_assignment(course: Course, public_id: str) -> CourseAssignment:
    assignment = db.session.scalar(
        select(CourseAssignment).where(
            CourseAssignment.public_id == public_id, CourseAssignment.course_id == course.id
        )
    )
    if assignment is None:
        raise NotFoundError("Assignment not found.")
    return assignment


def current_rubric(assignment: CourseAssignment) -> AssignmentRubric | None:
    if assignment.rubric_version is None:
        return None
    return db.session.scalar(
        select(AssignmentRubric).where(
            AssignmentRubric.assignment_id == assignment.id,
            AssignmentRubric.version == assignment.rubric_version,
        )
    )


def rubric_dict(rubric: AssignmentRubric | None) -> dict[str, Any] | None:
    if rubric is None:
        return None
    return {
        "id": rubric.id,
        "version": rubric.version,
        "criteria": rubric.criteria,
        "total_points": rubric.total_points,
        "passing_percent": rubric.passing_percent,
        "feedback_required": rubric.feedback_required,
        "created_at": iso(rubric.created_at),
    }


def requirements(assignment: CourseAssignment) -> dict[str, Any]:
    req = {"min_words": None, "max_words": None, "files": "optional", "max_files": None}
    return {**req, **(assignment.requirements or {})}


def assignment_dict(assignment: CourseAssignment, *, staff: bool = True) -> dict[str, Any]:
    data = {
        "id": assignment.public_id,
        "course_id": assignment.course_id,
        "lesson_id": assignment.lesson_id,
        "kind": assignment.kind,
        "title": assignment.title,
        "instructions": assignment.instructions,
        "prompts": assignment.prompts or [],
        "requirements": requirements(assignment),
        "required": assignment.required,
        "passing_percent": assignment.passing_percent,
        "max_attempts": assignment.max_attempts,
        "resubmission_policy": assignment.resubmission_policy,
        "available_from": iso(assignment.available_from),
        "due_at": iso(assignment.due_at),
        "late_policy": assignment.late_policy,
        "status": assignment.status,
        "rubric": rubric_dict(current_rubric(assignment)),
    }
    if staff:
        data |= {
            "position": assignment.position,
            "lock_version": assignment.lock_version,
            "required_since": iso(assignment.required_since),
            "published_at": iso(assignment.published_at),
            "archived_at": iso(assignment.archived_at),
            "updated_at": iso(assignment.updated_at),
        }
    return data


def list_assignments(course: Course, actor: User) -> list[dict[str, Any]]:
    require(actor, P.ASSIGNMENTS_VIEW)
    rows = db.session.scalars(
        select(CourseAssignment)
        .where(CourseAssignment.course_id == course.id)
        .order_by(CourseAssignment.position)
    )
    return [assignment_dict(a) for a in rows]


# ---- definitions --------------------------------------------------------------------------

FIELDS = {
    "kind",
    "title",
    "instructions",
    "prompts",
    "requirements",
    "required",
    "passing_percent",
    "max_attempts",
    "resubmission_policy",
    "available_from",
    "due_at",
    "late_policy",
    "lesson_id",
}


def _prompts(value: Any, errors: dict) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_PROMPTS:
        errors["prompts"] = [f"Add between 1 and {MAX_PROMPTS} prompts."]
        return []
    out, seen = [], set()
    for i, item in enumerate(value):
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict) or set(item) - {"id", "text", "min_words"}:
            errors["prompts"] = [f"Prompt {i + 1} is invalid."]
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            errors["prompts"] = [f"Prompt {i + 1} needs text (at most 2000 characters)."]
            continue
        if problem := plain_text_problem(text):
            errors["prompts"] = [f"Prompt {i + 1}: {problem}"]
            continue
        pid = item.get("id")
        if not (isinstance(pid, str) and pid.isalnum() and len(pid) <= 24) or pid in seen:
            pid = f"p{secrets.token_hex(4)}"
        seen.add(pid)
        entry = {"id": pid, "text": text.strip()}
        min_words = item.get("min_words")
        if min_words is not None:
            if (
                not isinstance(min_words, int)
                or isinstance(min_words, bool)
                or not 1 <= min_words <= 20000
            ):
                errors["prompts"] = [f"Prompt {i + 1}: minimum words must be 1 to 20000."]
            else:
                entry["min_words"] = min_words
        out.append(entry)
    return out


def _requirements(value: Any, errors: dict) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"min_words", "max_words", "files", "max_files"}:
        errors["requirements"] = ["Use min_words, max_words, files and max_files."]
        return {}
    out: dict[str, Any] = {}
    sub: dict[str, Any] = {}
    out["min_words"] = _int(value, "min_words", 1, 50000, sub)
    out["max_words"] = _int(value, "max_words", 1, 50000, sub)
    if out["min_words"] and out["max_words"] and out["min_words"] > out["max_words"]:
        sub["max_words"] = ["Must be at least the minimum."]
    files = value.get("files", "optional")
    if files not in FILE_RULES:
        sub["files"] = [f"Use one of: {', '.join(FILE_RULES)}."]
    out["files"] = files
    from flask import current_app

    limit = current_app.config["SUBMISSION_MAX_FILES"]
    out["max_files"] = _int(value, "max_files", 1, limit, sub)
    if sub:
        errors["requirements"] = [f"{k}: {v[0]}" for k, v in sub.items()]
    return out


def _clean(course: Course, data: dict[str, Any], creating: bool) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - FIELDS - {"lock_version"}
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean: dict[str, Any] = {}
    if creating or "title" in data:
        clean["title"] = _text(data, "title", 200, errors, required=True)
    if "instructions" in data:
        value = data.get("instructions")
        if not isinstance(value, str) or len(value) > 20000:
            errors["instructions"] = ["Plain text of at most 20000 characters."]
        elif problem := plain_text_problem(value):
            errors["instructions"] = [problem]
        else:
            clean["instructions"] = value.strip()
    if "kind" in data:
        if data["kind"] not in ASSIGNMENT_KINDS:
            errors["kind"] = [f"Use one of: {', '.join(ASSIGNMENT_KINDS)}."]
        clean["kind"] = data["kind"]
    if creating or "prompts" in data:
        clean["prompts"] = _prompts(data.get("prompts", [{"text": "Write your response."}]), errors)
    if "requirements" in data:
        clean["requirements"] = _requirements(data["requirements"], errors)
    if "required" in data:
        if not isinstance(data["required"], bool):
            errors["required"] = ["Must be true or false."]
        clean["required"] = data["required"]
    if "passing_percent" in data:
        clean["passing_percent"] = _int(data, "passing_percent", 0, 100, errors)
    if "max_attempts" in data:
        clean["max_attempts"] = _int(data, "max_attempts", 1, 20, errors)
    for field, options in (
        ("resubmission_policy", RESUBMISSION_POLICIES),
        ("late_policy", LATE_POLICIES),
    ):
        if field in data:
            if data[field] not in options:
                errors[field] = [f"Use one of: {', '.join(options)}."]
            clean[field] = data[field]
    for field in ("available_from", "due_at"):
        if field in data:
            clean[field] = parse_datetime(data[field], field, errors)
    if "lesson_id" in data:
        lesson_id = data["lesson_id"]
        if lesson_id is not None:
            lesson = db.session.get(CourseLesson, lesson_id) if isinstance(lesson_id, int) else None
            if lesson is None or lesson.course_id != course.id:
                errors["lesson_id"] = ["Choose a lesson of this course."]
        clean["lesson_id"] = lesson_id
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return clean


def _editable(course: Course) -> None:
    if course.status == "archived":
        raise ConflictError("Restore this course before changing its assignments.")


def create(course: Course, data: dict[str, Any], actor: User) -> CourseAssignment:
    require(actor, P.ASSIGNMENTS_MANAGE)
    _editable(course)
    clean = _clean(course, data, creating=True)
    last = db.session.scalar(
        select(func.max(CourseAssignment.position)).where(CourseAssignment.course_id == course.id)
    )
    assignment = CourseAssignment(
        public_id=new_id(),
        course_id=course.id,
        position=(last if last is not None else -1) + 1,
        created_by_id=actor.id,
        updated_by_id=actor.id,
        requirements={"files": "optional"},
    )
    for key, value in clean.items():
        setattr(assignment, key, value)
    db.session.add(assignment)
    db.session.flush()
    audit_service.record(
        "assignment.created",
        "course",
        course.id,
        actor=actor,
        details={"assignment_id": assignment.public_id, "title": assignment.title},
    )
    return assignment


def update(
    course: Course, assignment: CourseAssignment, data: dict[str, Any], actor: User
) -> CourseAssignment:
    require(actor, P.ASSIGNMENTS_MANAGE)
    _editable(course)
    check_lock(assignment, data)
    clean = _clean(course, data, creating=False)
    if "prompts" in clean and _has_submissions(assignment):
        old = {p["id"] for p in assignment.prompts or []}
        if not old <= {p["id"] for p in clean["prompts"]}:
            raise ConflictError(
                "Learners have answered these prompts; keep the existing prompts (you can "
                "edit their wording or add new ones)."
            )
    changed = sorted(k for k, v in clean.items() if getattr(assignment, k) != v)
    for key, value in clean.items():
        setattr(assignment, key, value)
    if assignment.status == "published" and assignment.required and not assignment.required_since:
        assignment.required_since = _now()
    assignment.lock_version += 1
    assignment.updated_by_id = actor.id
    db.session.flush()
    audit_service.record(
        "assignment.updated",
        "course",
        course.id,
        actor=actor,
        details={"assignment_id": assignment.public_id, "fields": changed},
    )
    return assignment


def _has_submissions(assignment: CourseAssignment) -> bool:
    return bool(
        db.session.scalar(
            select(func.count(AssignmentSubmission.id)).where(
                AssignmentSubmission.assignment_id == assignment.id
            )
        )
    )


def set_status(
    course: Course, assignment: CourseAssignment, status: Any, actor: User
) -> CourseAssignment:
    require(actor, P.ASSIGNMENTS_MANAGE)
    _editable(course)
    if status not in ("draft", "published", "archived"):
        raise ValidationError(details={"status": ["Use draft, published or archived."]})
    if status == assignment.status:
        return assignment
    if status == "published":
        problems = []
        if not assignment.prompts:
            problems.append("Add at least one prompt.")
        if assignment.rubric_version is None and assignment.passing_percent is None:
            problems.append("Add a rubric, or set a passing percentage for pass/fail grading.")
        if problems:
            raise ValidationError("This assignment isn't ready.", details={"readiness": problems})
        now = _now()
        assignment.published_at = assignment.published_at or now
        assignment.archived_at = None
        if assignment.required and assignment.required_since is None:
            assignment.required_since = now
    elif status == "archived":
        assignment.archived_at = _now()
    elif status == "draft" and _has_submissions(assignment):
        raise ConflictError("Learners have submitted work; archive the assignment instead.")
    previous = assignment.status
    assignment.status = status
    assignment.lock_version += 1
    assignment.updated_by_id = actor.id
    db.session.flush()
    audit_service.record(
        f"assignment.{status}",
        "course",
        course.id,
        actor=actor,
        details={"assignment_id": assignment.public_id, "from": previous},
    )
    return assignment


def delete(course: Course, assignment: CourseAssignment, actor: User) -> None:
    require(actor, P.ASSIGNMENTS_MANAGE)
    if assignment.published_at is not None or _has_submissions(assignment):
        raise ConflictError("Published assignments are kept; archive it instead.")
    audit_service.record(
        "assignment.deleted",
        "course",
        course.id,
        actor=actor,
        details={"assignment_id": assignment.public_id, "title": assignment.title},
    )
    db.session.delete(assignment)


# ---- rubrics (immutable versions) -----------------------------------------------------------


def _criteria(value: Any, errors: dict) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CRITERIA:
        errors["criteria"] = [f"Add between 1 and {MAX_CRITERIA} criteria."]
        return []
    out, seen = [], set()
    for i, item in enumerate(value):
        label = f"Criterion {i + 1}"
        if not isinstance(item, dict) or set(item) - {
            "id",
            "title",
            "description",
            "max_points",
            "descriptors",
        }:
            errors.setdefault("criteria", []).append(f"{label} is invalid.")
            continue
        title, description = item.get("title"), item.get("description", "")
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            errors.setdefault("criteria", []).append(
                f"{label}: a title (160 characters) is needed."
            )
            continue
        if not isinstance(description, str) or len(description) > 1000:
            errors.setdefault("criteria", []).append(f"{label}: description too long.")
            continue
        if plain_text_problem(title) or plain_text_problem(description):
            errors.setdefault("criteria", []).append(f"{label}: use plain text.")
            continue
        max_points = item.get("max_points")
        if (
            not isinstance(max_points, int)
            or isinstance(max_points, bool)
            or not 1 <= max_points <= 100
        ):
            errors.setdefault("criteria", []).append(f"{label}: maximum points must be 1 to 100.")
            continue
        descriptors = item.get("descriptors", [])
        if not isinstance(descriptors, list) or len(descriptors) > MAX_DESCRIPTORS:
            errors.setdefault("criteria", []).append(
                f"{label}: at most {MAX_DESCRIPTORS} performance descriptors."
            )
            continue
        clean_desc = []
        for d in descriptors:
            points = d.get("points") if isinstance(d, dict) else None
            text_label = d.get("label") if isinstance(d, dict) else None
            text = d.get("description", "") if isinstance(d, dict) else None
            if (
                not isinstance(d, dict)
                or set(d) - {"label", "points", "description"}
                or not isinstance(text_label, str)
                or not text_label.strip()
                or len(text_label) > 80
                or not isinstance(text, str)
                or len(text) > 500
                or plain_text_problem(text_label)
                or plain_text_problem(text)
                or not isinstance(points, int)
                or isinstance(points, bool)
                or not 0 <= points <= max_points
            ):
                errors.setdefault("criteria", []).append(
                    f"{label}: each descriptor needs a label and points from 0 to {max_points}."
                )
                break
            clean_desc.append(
                {"label": text_label.strip(), "points": points, "description": text.strip()}
            )
        cid = item.get("id")
        if not (isinstance(cid, str) and cid.isalnum() and len(cid) <= 24) or cid in seen:
            cid = f"c{secrets.token_hex(4)}"
        seen.add(cid)
        out.append(
            {
                "id": cid,
                "title": title.strip(),
                "description": description.strip(),
                "max_points": max_points,
                "descriptors": sorted(clean_desc, key=lambda d: -d["points"]),
            }
        )
    return out


def save_rubric(
    course: Course, assignment: CourseAssignment, data: Any, actor: User
) -> AssignmentRubric:
    """Store a new rubric version. Earlier versions (and grades using them) are untouched."""
    require(actor, P.ASSIGNMENTS_MANAGE)
    _editable(course)
    if not isinstance(data, dict) or set(data) - {
        "criteria",
        "passing_percent",
        "feedback_required",
        "lock_version",
    }:
        raise ValidationError("Send criteria, passing_percent and feedback_required.")
    check_lock(assignment, data)
    errors: dict[str, Any] = {}
    criteria = _criteria(data.get("criteria"), errors)
    passing = data.get("passing_percent")
    if not isinstance(passing, int) or isinstance(passing, bool) or not 0 <= passing <= 100:
        errors["passing_percent"] = ["Use a percentage from 0 to 100."]
    feedback_required = data.get("feedback_required", False)
    if not isinstance(feedback_required, bool):
        errors["feedback_required"] = ["Must be true or false."]
    if errors:
        raise ValidationError("The rubric needs attention.", details=errors)
    total = sum(c["max_points"] for c in criteria)
    if total > 1000:
        raise ValidationError(details={"criteria": ["The rubric can total at most 1000 points."]})
    version = (
        db.session.scalar(
            select(func.max(AssignmentRubric.version)).where(
                AssignmentRubric.assignment_id == assignment.id
            )
        )
        or 0
    ) + 1
    rubric = AssignmentRubric(
        assignment_id=assignment.id,
        version=version,
        criteria=criteria,
        total_points=total,
        passing_percent=passing,
        feedback_required=feedback_required,
        created_by_id=actor.id,
    )
    db.session.add(rubric)
    assignment.rubric_version = version
    assignment.lock_version += 1
    assignment.updated_by_id = actor.id
    db.session.flush()
    audit_service.record(
        "assignment.rubric_saved",
        "course",
        course.id,
        actor=actor,
        details={"assignment_id": assignment.public_id, "version": version, "total": total},
    )
    return rubric


def rubric_history(assignment: CourseAssignment, actor: User) -> list[dict[str, Any]]:
    require(actor, P.ASSIGNMENTS_VIEW)
    rows = db.session.scalars(
        select(AssignmentRubric)
        .where(AssignmentRubric.assignment_id == assignment.id)
        .order_by(AssignmentRubric.version.desc())
    )
    return [rubric_dict(r) for r in rows]


# ---- course assessors ------------------------------------------------------------------------


def assessors(course: Course, actor: User) -> list[dict[str, Any]]:
    require(actor, P.ASSIGNMENTS_VIEW)
    rows = db.session.execute(
        select(CourseAssessor, User)
        .join(User, User.id == CourseAssessor.user_id)
        .where(CourseAssessor.course_id == course.id)
        .order_by(User.display_name)
    ).all()
    return [
        {"user_id": user.id, "name": user.display_name, "email": user.email} for _, user in rows
    ]


def set_assessors(course: Course, user_ids: Any, actor: User) -> list[dict[str, Any]]:
    """Replace the course's assessors. Each must be able to view submissions."""
    require(actor, P.ASSIGNMENTS_MANAGE)
    if not isinstance(user_ids, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in user_ids
    ):
        raise ValidationError(details={"user_ids": ["Send a list of staff user ids."]})
    wanted = set(user_ids)
    users = {u.id: u for u in db.session.scalars(select(User).where(User.id.in_(wanted or {0})))}
    problems = [
        f"User {uid} can't review submissions."
        for uid in wanted
        if uid not in users
        or not users[uid].is_active
        or not granted(users[uid], P.ASSIGNMENTS_VIEW_SUBMISSIONS)
    ]
    if problems:
        raise ValidationError(details={"user_ids": problems})
    current = {
        a.user_id: a
        for a in db.session.scalars(
            select(CourseAssessor).where(CourseAssessor.course_id == course.id)
        )
    }
    for uid in set(current) - wanted:
        db.session.delete(current[uid])
    for uid in wanted - set(current):
        db.session.add(CourseAssessor(course_id=course.id, user_id=uid, added_by_id=actor.id))
    db.session.flush()
    audit_service.record(
        "assignment.assessors_changed",
        "course",
        course.id,
        actor=actor,
        details={"added": sorted(wanted - set(current)), "removed": sorted(set(current) - wanted)},
    )
    return assessors(course, actor)


def in_scope(actor: User, course_id: int) -> bool:
    """Staff may review a course's submissions when they manage assignments or are one of
    the course's assessors (having the permission alone isn't enough)."""
    if granted(actor, P.ASSIGNMENTS_MANAGE):
        return True
    return bool(
        db.session.scalar(
            select(CourseAssessor.id).where(
                CourseAssessor.course_id == course_id, CourseAssessor.user_id == actor.id
            )
        )
    )


# ---- exceptions ----------------------------------------------------------------------------


def exception_dict(row: AssignmentException) -> dict[str, Any]:
    return {
        "id": row.id,
        "enrollment_id": row.enrollment_id,
        "due_at": iso(row.due_at),
        "extra_attempts": row.extra_attempts,
        "reason": row.reason,
        "granted_by_id": row.granted_by_id,
        "created_at": iso(row.created_at),
        "revoked_at": iso(row.revoked_at),
    }


def active_exception(assignment_id: int, enrollment_id: int) -> AssignmentException | None:
    return db.session.scalar(
        select(AssignmentException)
        .where(
            AssignmentException.assignment_id == assignment_id,
            AssignmentException.enrollment_id == enrollment_id,
            AssignmentException.revoked_at.is_(None),
        )
        .order_by(AssignmentException.id.desc())
        .limit(1)
    )


def list_exceptions(assignment: CourseAssignment, actor: User) -> list[dict[str, Any]]:
    require(actor, P.ASSIGNMENTS_MANAGE_EXCEPTIONS)
    rows = db.session.scalars(
        select(AssignmentException)
        .where(AssignmentException.assignment_id == assignment.id)
        .order_by(AssignmentException.id.desc())
    )
    return [exception_dict(r) for r in rows]


def grant_exception(
    course: Course, assignment: CourseAssignment, data: Any, actor: User
) -> AssignmentException:
    require(actor, P.ASSIGNMENTS_MANAGE_EXCEPTIONS)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    enrollment = None
    if isinstance(data.get("enrollment_id"), int):
        enrollment = db.session.get(CourseEnrollment, data["enrollment_id"])
    if enrollment is None or enrollment.course_id != course.id:
        errors["enrollment_id"] = ["Choose a learner enrolled in this course."]
    due_at = parse_datetime(data.get("due_at"), "due_at", errors)
    extra = data.get("extra_attempts", 0)
    if not isinstance(extra, int) or isinstance(extra, bool) or not 0 <= extra <= 10:
        errors["extra_attempts"] = ["Use 0 to 10 extra attempts."]
    reason = _text(data, "reason", 300, errors, required=True)
    if not errors and due_at is None and not extra:
        errors["due_at"] = ["Give a new deadline and/or extra attempts."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    previous = active_exception(assignment.id, enrollment.id)
    if previous is not None:
        previous.revoked_at, previous.revoked_by_id = _now(), actor.id
    row = AssignmentException(
        assignment_id=assignment.id,
        enrollment_id=enrollment.id,
        due_at=due_at,
        extra_attempts=extra,
        reason=reason,
        granted_by_id=actor.id,
    )
    db.session.add(row)
    db.session.flush()
    audit_service.record(
        "assignment.exception_granted",
        "course",
        course.id,
        actor=actor,
        details={
            "assignment_id": assignment.public_id,
            "enrollment_id": enrollment.id,
            "due_at": iso(due_at),
            "extra_attempts": extra,
            "reason": reason,
        },
    )
    return row


def revoke_exception(
    course: Course, assignment: CourseAssignment, exception_id: int, actor: User
) -> AssignmentException:
    require(actor, P.ASSIGNMENTS_MANAGE_EXCEPTIONS)
    row = db.session.get(AssignmentException, exception_id)
    if row is None or row.assignment_id != assignment.id:
        raise NotFoundError("Exception not found.")
    if row.revoked_at is None:
        row.revoked_at, row.revoked_by_id = _now(), actor.id
        audit_service.record(
            "assignment.exception_revoked",
            "course",
            course.id,
            actor=actor,
            details={"assignment_id": assignment.public_id, "exception_id": row.id},
        )
    return row


# ---- reports -------------------------------------------------------------------------------


def report(course: Course, assignment: CourseAssignment, actor: User) -> dict[str, Any]:
    require(actor, P.ASSIGNMENTS_VIEW_REPORTS)
    by_status = dict(
        db.session.execute(
            select(AssignmentSubmission.status, func.count(AssignmentSubmission.id))
            .where(AssignmentSubmission.assignment_id == assignment.id)
            .group_by(AssignmentSubmission.status)
        ).all()
    )
    from ...models import AssignmentAttempt

    published = db.session.execute(
        select(AssignmentGrade.percent, AssignmentGrade.passed)
        .join(AssignmentAttempt, AssignmentAttempt.id == AssignmentGrade.attempt_id)
        .join(AssignmentSubmission, AssignmentSubmission.id == AssignmentAttempt.submission_id)
        .where(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentGrade.status == "published",
            AssignmentGrade.outcome == "graded",
        )
    ).all()
    percents = [p for p, _ in published if p is not None]
    return {
        "assignment": {"id": assignment.public_id, "title": assignment.title},
        "submissions": sum(by_status.values()),
        "by_status": by_status,
        "grades_published": len(published),
        "pass_rate": round(100 * sum(1 for _, ok in published if ok) / len(published))
        if published
        else None,
        "average_percent": round(sum(percents) / len(percents)) if percents else None,
    }
