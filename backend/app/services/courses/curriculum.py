"""Course curriculum: modules, lessons, lesson content and ordering.

Reordering is validated server-side: the client sends the complete layout (every module,
every lesson exactly once) and positions are renumbered in two steps, so the unique
(parent, position) constraints never see a duplicate even while rows move. Lessons with
learner progress can't be deleted (unpublish them instead), so history is never lost.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Course, CourseLesson, CourseModule, LessonProgress, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE, plain_text_problem, slugify
from .. import audit_service
from ..serializers import expand_body
from . import content
from .admin import lesson_admin_summary, module_dict, require, touch_public


def get_module(course: Course, module_id: int) -> CourseModule:
    module = db.session.get(CourseModule, module_id)
    if module is None or module.course_id != course.id:
        raise NotFoundError("Module not found.")
    return module


def get_lesson(course: Course, lesson_id: int) -> CourseLesson:
    lesson = db.session.get(CourseLesson, lesson_id)
    if lesson is None or lesson.course_id != course.id:
        raise NotFoundError("Lesson not found.")
    return lesson


def course_file_ids(course: Course) -> set[str] | None:
    """Public ids of the course product's active files (None: no product linked)."""
    if course.product is None:
        return None
    return {f.public_id for f in course.product.files if f.status == "active"}


def _editable(course: Course) -> None:
    if course.status == "archived":
        raise ConflictError("Restore this course before changing its curriculum.")


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


def _objectives(value: Any, errors: dict) -> list[str]:
    if not isinstance(value, list) or len(value) > 10:
        errors["objectives"] = ["Use at most 10 objectives."]
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            if len(item.strip()) > 300 or plain_text_problem(item):
                errors["objectives"] = ["Each objective is plain text of at most 300 characters."]
            out.append(item.strip())
    return out


# ---- modules ----------------------------------------------------------------------------


def save_module(
    course: Course, data: dict[str, Any], actor: User, module: CourseModule | None = None
) -> CourseModule:
    require(actor, P.COURSES_MANAGE_CURRICULUM)
    _editable(course)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - {"title", "description", "objectives"}
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    title = _text(data, "title", 200, errors, required=module is None or "title" in data)
    description = _text(data, "description", 1000, errors)
    objectives = _objectives(data["objectives"], errors) if "objectives" in data else None
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    created = module is None
    if module is None:
        last = db.session.scalar(
            select(func.max(CourseModule.position)).where(CourseModule.course_id == course.id)
        )
        module = CourseModule(course_id=course.id, position=(last if last is not None else -1) + 1)
        db.session.add(module)
    if title is not None:
        module.title = title
    if description is not None:
        module.description = description
    if objectives is not None:
        module.objectives = objectives
    db.session.flush()
    audit_service.record(
        "course.module_created" if created else "course.module_updated",
        "course",
        course.id,
        actor=actor,
        details={"module_id": module.id, "title": module.title},
    )
    touch_public(course, "course_curriculum", actor)
    return module


def _has_progress(lesson_ids: list[int]) -> bool:
    if not lesson_ids:
        return False
    return bool(
        db.session.scalar(
            select(func.count(LessonProgress.id)).where(LessonProgress.lesson_id.in_(lesson_ids))
        )
    )


def delete_module(course: Course, module: CourseModule, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_CURRICULUM)
    _editable(course)
    if _has_progress([lesson.id for lesson in module.lessons]):
        raise ConflictError(
            "Learners have progress in this module's lessons. Move or unpublish them instead."
        )
    audit_service.record(
        "course.module_deleted",
        "course",
        course.id,
        actor=actor,
        details={"module_id": module.id, "title": module.title},
    )
    db.session.delete(module)
    db.session.flush()
    _renumber_modules(course, [m for m in course.modules if m.id != module.id])
    touch_public(course, "course_curriculum", actor)


def _renumber_modules(course: Course, ordered: list[CourseModule]) -> None:
    for index, module in enumerate(ordered):
        module.position = -(index + 1)
    db.session.flush()
    for index, module in enumerate(ordered):
        module.position = index
    db.session.flush()


# ---- lessons ----------------------------------------------------------------------------

LESSON_FIELDS = {
    "title",
    "slug",
    "summary",
    "body",
    "estimated_minutes",
    "is_preview",
    "completion_required",
}


def _unique_slug(course: Course, base: str, exclude: int | None = None) -> str:
    base = (base or "lesson")[:190]
    slug, n = base, 2
    while db.session.scalar(
        select(CourseLesson.id).where(
            CourseLesson.course_id == course.id,
            CourseLesson.slug == slug,
            CourseLesson.id != (exclude or 0),
        )
    ):
        slug, n = f"{base}-{n}", n + 1
    return slug


def save_lesson(
    course: Course,
    data: dict[str, Any],
    actor: User,
    *,
    module: CourseModule | None = None,
    lesson: CourseLesson | None = None,
) -> CourseLesson:
    require(actor, P.COURSES_MANAGE_CURRICULUM)
    _editable(course)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - LESSON_FIELDS - {"lock_version"}
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    title = _text(data, "title", 200, errors, required=lesson is None or "title" in data)
    summary = _text(data, "summary", 400, errors)
    slug = None
    if "slug" in data:
        slug = data["slug"]
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or len(slug) > 200:
            errors["slug"] = ["Use lowercase letters, numbers and hyphens."]
        elif db.session.scalar(
            select(CourseLesson.id).where(
                CourseLesson.course_id == course.id,
                CourseLesson.slug == slug,
                CourseLesson.id != (lesson.id if lesson else 0),
            )
        ):
            errors["slug"] = ["Another lesson in this course uses this address."]
    body = None
    if "body" in data:
        try:
            body = content.validate_lesson_blocks(data["body"], file_ids=course_file_ids(course))
        except ValidationError as exc:
            errors["body"] = (
                exc.details.get("body") if isinstance(exc.details, dict) else [exc.message]
            )
    minutes = data.get("estimated_minutes")
    if (
        "estimated_minutes" in data
        and minutes is not None
        and (not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 600)
    ):
        errors["estimated_minutes"] = ["Use 1 to 600 minutes, or leave empty to estimate."]
    for flag in ("is_preview", "completion_required"):
        if flag in data and not isinstance(data[flag], bool):
            errors[flag] = ["Must be true or false."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    created = lesson is None
    if lesson is None:
        last = db.session.scalar(
            select(func.max(CourseLesson.position)).where(CourseLesson.module_id == module.id)
        )
        lesson = CourseLesson(
            course_id=course.id,
            module_id=module.id,
            slug=slug or _unique_slug(course, slugify(title or "")),
            title=title,
            position=(last if last is not None else -1) + 1,
            body=[],
        )
        db.session.add(lesson)
    if title is not None:
        lesson.title = title
    if slug is not None:
        lesson.slug = slug
    if summary is not None:
        lesson.summary = summary
    if body is not None:
        lesson.body = body
    if "estimated_minutes" in data:
        lesson.estimated_minutes = minutes
    for flag in ("is_preview", "completion_required"):
        if flag in data:
            setattr(lesson, flag, data[flag])
    lesson.updated_by_id = actor.id
    db.session.flush()
    audit_service.record(
        "course.lesson_created" if created else "course.lesson_updated",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title},
    )
    if lesson.status == "published":
        touch_public(course, "course_curriculum", actor)
    return lesson


def set_lesson_status(course: Course, lesson: CourseLesson, status: str, actor: User) -> None:
    require(actor, P.COURSES_PUBLISH)
    _editable(course)
    if status not in ("draft", "published"):
        raise ValidationError(details={"status": ["Use draft or published."]})
    if status == "published" and not lesson.body:
        raise ValidationError("Add some content before publishing this lesson.")
    if lesson.status == status:
        return
    lesson.status = status
    audit_service.record(
        f"course.lesson_{'published' if status == 'published' else 'unpublished'}",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title},
    )
    touch_public(course, "course_curriculum", actor)


def delete_lesson(course: Course, lesson: CourseLesson, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_CURRICULUM)
    _editable(course)
    if _has_progress([lesson.id]):
        raise ConflictError("Learners have progress in this lesson. Unpublish it instead.")
    module = lesson.module
    audit_service.record(
        "course.lesson_deleted",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title},
    )
    db.session.delete(lesson)
    db.session.flush()
    remaining = [item for item in module.lessons if item.id != lesson.id]
    for index, item in enumerate(remaining):
        item.position = -(index + 1)
    db.session.flush()
    for index, item in enumerate(remaining):
        item.position = index
    db.session.flush()
    touch_public(course, "course_curriculum", actor)


def reorder(course: Course, layout: Any, actor: User) -> None:
    """Apply a complete layout: [{"module_id": 1, "lesson_ids": [3, 4]}, ...] in order."""
    require(actor, P.COURSES_MANAGE_CURRICULUM)
    _editable(course)
    if not isinstance(layout, list) or not all(isinstance(m, dict) for m in layout):
        raise ValidationError(details={"layout": ["Send the full list of modules and lessons."]})
    modules = {m.id: m for m in course.modules}
    lessons = {lesson.id: lesson for m in course.modules for lesson in m.lessons}
    module_ids = [m.get("module_id") for m in layout]
    lesson_ids = [i for m in layout for i in (m.get("lesson_ids") or [])]
    if sorted(module_ids, key=str) != sorted(modules, key=str) or len(set(module_ids)) != len(
        module_ids
    ):
        raise ValidationError(details={"layout": ["Include every module of this course once."]})
    if (
        not all(isinstance(m.get("lesson_ids"), list) for m in layout)
        or sorted(lesson_ids, key=str) != sorted(lessons, key=str)
        or len(set(lesson_ids)) != len(lesson_ids)
    ):
        raise ValidationError(details={"layout": ["Include every lesson of this course once."]})
    _renumber_modules(course, [modules[mid] for mid in module_ids])
    # Step 1: unique negative positions while lessons change module; step 2: final order.
    for entry in layout:
        for lesson_id in entry["lesson_ids"]:
            lessons[lesson_id].module_id = entry["module_id"]
            lessons[lesson_id].position = -lesson_id
    db.session.flush()
    for entry in layout:
        for index, lesson_id in enumerate(entry["lesson_ids"]):
            lessons[lesson_id].position = index
    db.session.flush()
    db.session.expire(course, ["modules"])
    for module in modules.values():
        db.session.expire(module, ["lessons"])
    audit_service.record("course.curriculum_reordered", "course", course.id, actor=actor)
    touch_public(course, "course_curriculum", actor)


def lesson_detail(course: Course, lesson: CourseLesson) -> dict[str, Any]:
    from .assessments import assessment_summary

    return {
        **lesson_admin_summary(lesson),
        "body": lesson.body or [],
        "course_id": course.id,
        "assessments": [
            assessment_summary(a) for a in course.assessments if a.lesson_id == lesson.id
        ],
        # Images resolved for the staff preview (the editor keeps working with media ids).
        "preview_body": expand_body(lesson.body or []),
        "word_count": content.lesson_word_count(lesson.body),
        "reading_minutes": content.reading_minutes(lesson.body),
    }


def curriculum(course: Course) -> list[dict[str, Any]]:
    return [module_dict(m) for m in course.modules]
