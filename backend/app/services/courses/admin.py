"""Course administration: details, access rules, publication, duplication and categories.

Every function re-checks the specific permission it needs (the API decorators only check
that the caller may see courses at all), so a limited role can never widen its rights by
calling an endpoint directly.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sql_update

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms.blocks import validate_blocks
from ...extensions import db
from ...models import (
    Assessment,
    AssessmentQuestion,
    Author,
    Course,
    CourseCategory,
    CourseEnrollment,
    CourseLesson,
    CourseModule,
    Product,
    Topic,
    User,
)
from ...models.courses import COURSE_ACCESS, COURSE_AVAILABILITY, COURSE_LEVELS
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE, plain_text_problem, slugify
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso
from . import content


def _now() -> datetime:
    return datetime.now(UTC)


def require(actor: User, *perms: P) -> None:
    granted = effective_permissions(actor)
    if not all(p.value in granted for p in perms):
        raise ForbiddenError()


def can(actor: User) -> dict[str, bool]:
    granted = effective_permissions(actor)
    keys = {
        "create": P.COURSES_CREATE,
        "edit": P.COURSES_EDIT,
        "publish": P.COURSES_PUBLISH,
        "archive": P.COURSES_ARCHIVE,
        "manage_curriculum": P.COURSES_MANAGE_CURRICULUM,
        "manage_assessments": P.COURSES_MANAGE_ASSESSMENTS,
        "view_enrollments": P.COURSES_VIEW_ENROLLMENTS,
        "manage_enrollments": P.COURSES_MANAGE_ENROLLMENTS,
        "view_reports": P.COURSES_VIEW_REPORTS,
        "view_drafts": P.COURSES_VIEW_DRAFTS,
        "edit_drafts": P.COURSES_EDIT_DRAFTS,
        "publish_lessons": P.COURSES_PUBLISH_LESSONS,
        "view_revisions": P.COURSES_VIEW_REVISIONS,
        "restore_revisions": P.COURSES_RESTORE_REVISIONS,
    }
    return {name: perm.value in granted for name, perm in keys.items()}


def get_course(course_id: int) -> Course:
    course = db.session.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    return course


def touch_public(course: Course, reason: str, actor: User | None) -> None:
    """Queue a site rebuild when a change affects a public course page."""
    if course.status == "published":
        record_public_change("course", course.id, reason, actor)


# ---- derived values ---------------------------------------------------------------------


def lesson_minutes(lesson: CourseLesson) -> int:
    return lesson.estimated_minutes or content.reading_minutes(lesson.body)


def published_lessons(course: Course) -> list[CourseLesson]:
    return [l for m in course.modules for l in m.lessons if l.status == "published"]  # noqa: E741


def total_minutes(course: Course) -> int:
    if course.estimated_minutes:
        return course.estimated_minutes
    return sum(lesson_minutes(lesson) for lesson in published_lessons(course))


def readiness(course: Course) -> dict[str, Any]:
    """Problems that block publication (``issues``) and things worth checking (``warnings``)."""
    issues: list[str] = []
    warnings: list[str] = []
    lessons = published_lessons(course)
    if not lessons:
        issues.append("Publish at least one lesson.")
    if not course.summary.strip():
        issues.append("Add a short summary (shown in the catalogue and search results).")
    if course.access_type == "premium":
        product = course.product
        if product is None:
            issues.append("Premium courses need a linked course product (price and checkout).")
        elif product.pricing_model != "paid":
            issues.append("The linked product is free; premium courses need a paid product.")
        else:
            from ..commerce import catalogue

            state = catalogue.readiness(product)
            blockers = [b for b in state["blockers"] if "linked course" not in b]
            if blockers and course.availability == "available":
                warnings.append("The course product can't be bought yet: " + " ".join(blockers[:3]))
    if not course.outcomes:
        warnings.append("List what learners will be able to do (learning outcomes).")
    drafts = sum(1 for m in course.modules for l in m.lessons if l.status != "published")  # noqa: E741
    if drafts:
        warnings.append(f"{drafts} lesson(s) are still drafts and won't be shown to learners.")
    for assessment in course.assessments:
        if assessment.status != "published":
            continue
        if not assessment.questions:
            issues.append(f"Assessment “{assessment.title}” has no questions.")
        elif assessment.kind == "quiz" and not any(q.graded for q in assessment.questions):
            issues.append(f"Quiz “{assessment.title}” has no automatically scored questions.")
    if (
        course.certificate_enabled
        and not any(
            l.completion_required
            for l in lessons  # noqa: E741
        )
        and not any(
            a.required_for_completion and a.status == "published" for a in course.assessments
        )
    ):
        warnings.append("Nothing is required for completion, so certificates are issued at once.")
    return {"issues": issues, "warnings": warnings, "publishable": not issues}


# ---- serialisation ----------------------------------------------------------------------


def _counts(course_ids: list[int]) -> dict[int, dict[str, int]]:
    if not course_ids:
        return {}
    rows = db.session.execute(
        select(
            CourseEnrollment.course_id,
            func.count(CourseEnrollment.id),
            func.count(CourseEnrollment.completed_at),
        )
        .where(CourseEnrollment.course_id.in_(course_ids), CourseEnrollment.status == "active")
        .group_by(CourseEnrollment.course_id)
    ).all()
    return {cid: {"enrollments": total, "completions": done} for cid, total, done in rows}


def _media(media_id: int | None) -> dict | None:
    from ...models import MediaAsset

    asset = db.session.get(MediaAsset, media_id) if media_id else None
    return asset.as_image("responsive") if asset is not None else None


def course_summary(course: Course, counts: dict[str, int] | None = None) -> dict[str, Any]:
    lessons = [l for m in course.modules for l in m.lessons]  # noqa: E741
    counts = counts or {}
    return {
        "id": course.id,
        "public_id": course.public_id,
        "slug": course.slug,
        "title": course.title,
        "status": course.status,
        "access_type": course.access_type,
        "availability": course.availability,
        "enrollment_open": course.enrollment_open,
        "category": {"id": course.category.id, "name": course.category.name}
        if course.category
        else None,
        "product": {
            "id": course.product.id,
            "title": course.product.title,
            "status": course.product.status,
        }
        if course.product
        else None,
        "module_count": len(course.modules),
        "lesson_count": len(lessons),
        "published_lesson_count": sum(1 for l in lessons if l.status == "published"),  # noqa: E741
        "assessment_count": len(course.assessments),
        "enrollment_count": counts.get("enrollments", 0),
        "completion_count": counts.get("completions", 0),
        "is_featured": course.is_featured,
        "published_at": iso(course.published_at),
        "updated_at": iso(course.updated_at),
    }


def live_lesson_fields(lesson: CourseLesson) -> dict[str, Any]:
    return {
        "title": lesson.title,
        "summary": lesson.summary,
        "body": lesson.body or [],
        "estimated_minutes": lesson.estimated_minutes,
        "is_preview": lesson.is_preview,
        "completion_required": lesson.completion_required,
    }


def lesson_admin_summary(lesson: CourseLesson, drafts: bool = True) -> dict[str, Any]:
    """``drafts``: show the working copy (staff who may read drafts) or the live content."""
    if drafts and lesson.draft:
        data = {**lesson.draft}
        version = {
            "title": data.get("title", lesson.title),
            "summary": data.get("summary", lesson.summary),
            "is_preview": data.get("is_preview", lesson.is_preview),
            "completion_required": data.get("completion_required", lesson.completion_required),
            "estimated_minutes": data.get("estimated_minutes", lesson.estimated_minutes),
            "minutes": data.get("estimated_minutes")
            or content.reading_minutes(data.get("body", lesson.body)),
        }
    else:
        version = {
            "title": lesson.title,
            "summary": lesson.summary,
            "is_preview": lesson.is_preview,
            "completion_required": lesson.completion_required,
            "estimated_minutes": lesson.estimated_minutes,
            "minutes": lesson_minutes(lesson),
        }
    return {
        "id": lesson.id,
        "module_id": lesson.module_id,
        "slug": lesson.slug,
        **version,
        "status": lesson.status,
        "has_draft_changes": lesson.draft is not None,
        "live_revision": lesson.live_revision,
        "position": lesson.position,
        "updated_at": iso(lesson.updated_at),
    }


def module_dict(module: CourseModule, drafts: bool = True) -> dict[str, Any]:
    return {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "objectives": module.objectives or [],
        "position": module.position,
        "lessons": [lesson_admin_summary(lesson, drafts) for lesson in module.lessons],
    }


def course_detail(course: Course, actor: User) -> dict[str, Any]:
    from .assessments import assessment_summary

    counts = _counts([course.id]).get(course.id, {})
    return {
        **course_summary(course, counts),
        "subtitle": course.subtitle,
        "summary": course.summary,
        "description": course.description or [],
        "outcomes": course.outcomes or [],
        "prerequisites": course.prerequisites or [],
        "audience": course.audience or [],
        "level": course.level,
        "estimated_minutes": course.estimated_minutes,
        "total_minutes": total_minutes(course),
        "category_id": course.category_id,
        "author_id": course.author_id,
        "author": {"id": course.author.id, "name": course.author.display_name}
        if course.author
        else None,
        "topic_ids": [t.id for t in course.topics],
        "cover_media_id": course.cover_media_id,
        "cover": _media(course.cover_media_id),
        "social_image_id": course.social_image_id,
        "access_days": course.access_days,
        "product_id": course.product_id,
        "product_files": [
            {
                "id": f.public_id,
                "title": f.title,
                "format": f.current_version.file_format.upper() if f.current_version else "",
                "status": f.status,
            }
            for f in (course.product.files if course.product else [])
        ],
        "certificate_enabled": course.certificate_enabled,
        "featured_order": course.featured_order,
        "seo_title": course.seo_title,
        "meta_description": course.meta_description,
        "noindex": course.noindex,
        "first_published_at": iso(course.first_published_at),
        "archived_at": iso(course.archived_at),
        "lock_version": course.lock_version,
        "modules": [
            module_dict(m, P.COURSES_VIEW_DRAFTS.value in effective_permissions(actor))
            for m in course.modules
        ],
        "assessments": [assessment_summary(a) for a in course.assessments],
        "readiness": readiness(course),
        "can": can(actor),
        "created_at": iso(course.created_at),
    }


def list_courses(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(Course)
    if args.get("status") in ("draft", "scheduled", "published", "archived"):
        stmt = stmt.where(Course.status == args["status"])
    elif args.get("status") != "all":
        stmt = stmt.where(Course.status != "archived")
    if args.get("access") in COURSE_ACCESS:
        stmt = stmt.where(Course.access_type == args["access"])
    if q := (args.get("q") or "").strip()[:100]:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Course.title).like(like) | Course.slug.like(like))
    if str(args.get("category_id") or "").isdigit():
        stmt = stmt.where(Course.category_id == int(args["category_id"]))
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    sort = {
        "title": Course.title.asc(),
        "published": Course.published_at.desc().nulls_last(),
    }.get(args.get("sort"), Course.updated_at.desc())
    courses = db.session.scalars(
        stmt.order_by(sort, Course.id.desc()).limit(size).offset((page - 1) * size)
    ).all()
    counts = _counts([c.id for c in courses])
    items = [course_summary(c, counts.get(c.id)) for c in courses]
    return items, {"page": page, "page_size": size, "total": total}


# ---- validation -------------------------------------------------------------------------

DETAIL_FIELDS = {
    "title",
    "slug",
    "subtitle",
    "summary",
    "description",
    "outcomes",
    "prerequisites",
    "audience",
    "level",
    "estimated_minutes",
    "category_id",
    "author_id",
    "topic_ids",
    "cover_media_id",
    "social_image_id",
    "access_type",
    "availability",
    "enrollment_open",
    "access_days",
    "product_id",
    "certificate_enabled",
    "is_featured",
    "featured_order",
    "seo_title",
    "meta_description",
    "noindex",
}
_TEXT_LIMITS = {
    "title": 200,
    "subtitle": 240,
    "summary": 400,
    "seo_title": 200,
    "meta_description": 320,
}


def _text_list(value: Any, field: str, errors: dict) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        errors[field] = ["Use a list of at most 20 short items."]
        return []
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        item = item.strip()
        if len(item) > 300 or plain_text_problem(item):
            errors[field] = ["Each item must be plain text of at most 300 characters."]
            continue
        out.append(item)
    return out


def _positive(value: Any, field: str, errors: dict, high: int) -> int | None:
    if value in (None, ""):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= high:
        errors[field] = [f"Use a whole number from 1 to {high}, or leave it empty."]
        return None
    return value


def _clean(data: dict[str, Any], course: Course | None) -> dict[str, Any]:
    errors: dict[str, Any] = {}
    unknown = set(data) - DETAIL_FIELDS - {"lock_version"}
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean: dict[str, Any] = {}
    for field, limit in _TEXT_LIMITS.items():
        if field not in data:
            continue
        value = data[field]
        if value is None and field in ("seo_title", "meta_description"):
            clean[field] = None
            continue
        if not isinstance(value, str):
            errors[field] = ["Must be text."]
            continue
        value = value.strip()
        if field == "title" and not value:
            errors[field] = ["A title is required."]
        elif len(value) > limit:
            errors[field] = [f"At most {limit} characters."]
        elif problem := plain_text_problem(value):
            errors[field] = [problem]
        clean[field] = value or (None if field in ("seo_title", "meta_description") else "")
    if "slug" in data:
        slug = data["slug"]
        if not isinstance(slug, str) or not SLUG_RE.match(slug) or len(slug) > 200:
            errors["slug"] = ["Use lowercase letters, numbers and hyphens."]
        elif course is not None and course.first_published_at and slug != course.slug:
            errors["slug"] = ["Published courses keep their address so links keep working."]
        elif db.session.scalar(
            select(Course.id).where(Course.slug == slug, Course.id != (course.id if course else 0))
        ):
            errors["slug"] = ["Another course already uses this address."]
        else:
            clean["slug"] = slug
    if "description" in data:
        try:
            clean["description"] = validate_blocks(data["description"])
        except ValidationError as exc:
            errors["description"] = (
                exc.details.get("body") if isinstance(exc.details, dict) else [exc.message]
            )
    for field in ("outcomes", "prerequisites", "audience"):
        if field in data:
            clean[field] = _text_list(data[field], field, errors)
    for field, choices in (
        ("level", COURSE_LEVELS),
        ("access_type", COURSE_ACCESS),
        ("availability", COURSE_AVAILABILITY),
    ):
        if field in data:
            if data[field] not in choices:
                errors[field] = [f"Choose one of: {', '.join(choices)}."]
            else:
                clean[field] = data[field]
    for field in ("enrollment_open", "certificate_enabled", "is_featured", "noindex"):
        if field in data:
            if not isinstance(data[field], bool):
                errors[field] = ["Must be true or false."]
            else:
                clean[field] = data[field]
    if "estimated_minutes" in data:
        clean["estimated_minutes"] = _positive(
            data["estimated_minutes"], "estimated_minutes", errors, 10000
        )
    if "access_days" in data:
        clean["access_days"] = _positive(data["access_days"], "access_days", errors, 3650)
    if "featured_order" in data:
        value = data["featured_order"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1000:
            errors["featured_order"] = ["Use a number from 0 to 1000."]
        else:
            clean["featured_order"] = value
    for field in ("category_id", "author_id", "cover_media_id", "social_image_id", "product_id"):
        if field in data:
            value = data[field]
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                errors[field] = ["Choose an item from the list."]
            else:
                clean[field] = value
    if "topic_ids" in data:
        ids = data["topic_ids"]
        if (
            not isinstance(ids, list)
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
            or len(ids) > 10
        ):
            errors["topic_ids"] = ["Choose at most 10 topics."]
        else:
            clean["topic_ids"] = list(dict.fromkeys(ids))
    _check_refs(clean, course, errors)
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return clean


def _check_refs(clean: dict[str, Any], course: Course | None, errors: dict) -> None:
    from ..admin.media_admin import media_ref_problems

    media = {k: clean[k] for k in ("cover_media_id", "social_image_id") if clean.get(k)}
    for key, problem in media_ref_problems(media).items():
        errors[key] = [problem]
    if clean.get("author_id"):
        author = db.session.get(Author, clean["author_id"])
        if author is None or author.status != "active":
            errors["author_id"] = ["Choose an active author or instructor."]
    if clean.get("category_id"):
        category = db.session.get(CourseCategory, clean["category_id"])
        if category is None or not category.is_active:
            errors["category_id"] = ["Choose an active category."]
    if clean.get("topic_ids"):
        found = set(
            db.session.scalars(
                select(Topic.id).where(Topic.id.in_(clean["topic_ids"]), Topic.status == "active")
            )
        )
        if set(clean["topic_ids"]) - found:
            errors["topic_ids"] = ["One or more topics are not active."]
    if clean.get("product_id"):
        product = db.session.get(Product, clean["product_id"])
        other = db.session.scalar(
            select(Course.id).where(
                Course.product_id == clean["product_id"], Course.id != (course.id if course else 0)
            )
        )
        if product is None or product.status == "archived":
            errors["product_id"] = ["Choose an existing course product."]
        elif product.product_type != "course":
            errors["product_id"] = ["Link a product of type “Online course”."]
        elif other:
            errors["product_id"] = ["This product already belongs to another course."]


def _apply(course: Course, clean: dict[str, Any]) -> None:
    for key, value in clean.items():
        if key == "topic_ids":
            course.topics = (
                list(db.session.scalars(select(Topic).where(Topic.id.in_(value)))) if value else []
            )
        else:
            setattr(course, key, value)


def _snapshot(course: Course) -> dict[str, Any]:
    data = {k: getattr(course, k) for k in DETAIL_FIELDS - {"topic_ids"}}
    data["topic_ids"] = sorted(t.id for t in course.topics)
    return data


def _check_lock(course: Course, data: dict[str, Any]) -> None:
    lock = data.get("lock_version")
    if lock is not None and lock != course.lock_version:
        raise ConflictError(
            "Someone else saved this course while you were editing.",
            details={"code": "edit_conflict", "lock_version": course.lock_version},
        )


# ---- commands ---------------------------------------------------------------------------


def create(data: dict[str, Any], actor: User) -> Course:
    require(actor, P.COURSES_CREATE)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    data = dict(data)
    if "slug" not in data and isinstance(data.get("title"), str):
        base = slugify(data["title"]) or "course"
        slug, n = base, 2
        while db.session.scalar(select(Course.id).where(Course.slug == slug)):
            slug, n = f"{base}-{n}"[:200], n + 1
        data["slug"] = slug
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValidationError(
            "Some fields need attention.", details={"title": ["A title is required."]}
        )
    clean = _clean(data, None)
    course = Course(public_id=secrets.token_hex(8), created_by_id=actor.id, updated_by_id=actor.id)
    _apply(course, clean)
    db.session.add(course)
    db.session.flush()
    audit_service.record(
        "course.created", "course", course.id, actor=actor, details={"title": course.title}
    )
    return course


def update(course: Course, data: dict[str, Any], actor: User) -> Course:
    require(actor, P.COURSES_EDIT)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    if course.status == "archived":
        raise ConflictError("Restore this course before editing it.")
    _check_lock(course, data)
    clean = _clean(data, course)
    before = _snapshot(course)
    _apply(course, clean)
    course.updated_by_id = actor.id
    course.lock_version += 1
    db.session.flush()
    changes = audit_service.changed_fields(before, _snapshot(course))
    if changes:
        audit_service.record("course.updated", "course", course.id, actor=actor, details=changes)
        touch_public(course, "course_updated", actor)
    return course


def publish(course: Course, data: dict[str, Any], actor: User) -> Course:
    """Publish now, or schedule when ``publish_at`` is in the future."""
    require(actor, P.COURSES_PUBLISH)
    if course.status == "archived":
        raise ConflictError("Restore this course before publishing it.")
    state = readiness(course)
    if not state["publishable"]:
        raise ValidationError(
            "This course isn't ready to publish.", details={"readiness": state["issues"]}
        )
    errors: dict[str, Any] = {}
    from ..commerce.product_admin import _parse_dt

    at = _parse_dt((data or {}).get("publish_at"), "publish_at", errors)
    if errors:
        raise ValidationError(details=errors)
    now = _now()
    if at is not None and at > now:
        course.status, course.published_at = "scheduled", at
        action = "course.scheduled"
    else:
        course.status, course.published_at = "published", now
        course.first_published_at = course.first_published_at or now
        action = "course.published"
        record_public_change("course", course.id, "course_published", actor)
    course.lock_version += 1
    course.updated_by_id = actor.id
    audit_service.record(
        action, "course", course.id, actor=actor, details={"published_at": iso(course.published_at)}
    )
    return course


def unpublish(course: Course, actor: User) -> Course:
    require(actor, P.COURSES_PUBLISH)
    if course.status not in ("published", "scheduled"):
        raise ConflictError("This course is not published or scheduled.")
    was_public = course.status == "published"
    course.status = "draft"
    course.lock_version += 1
    if was_public:
        record_public_change("course", course.id, "course_unpublished", actor)
    audit_service.record("course.unpublished", "course", course.id, actor=actor)
    return course


def archive(course: Course, actor: User) -> Course:
    require(actor, P.COURSES_ARCHIVE)
    if course.status == "archived":
        return course
    was_public = course.status == "published"
    course.status, course.archived_at = "archived", _now()
    course.lock_version += 1
    if was_public:
        record_public_change("course", course.id, "course_archived", actor)
    audit_service.record("course.archived", "course", course.id, actor=actor)
    return course


def restore(course: Course, actor: User) -> Course:
    require(actor, P.COURSES_ARCHIVE)
    if course.status != "archived":
        raise ConflictError("Only archived courses can be restored.")
    course.status, course.archived_at = "draft", None
    course.lock_version += 1
    audit_service.record("course.restored", "course", course.id, actor=actor)
    return course


def delete(course: Course, actor: User) -> None:
    """Delete a course that was never published and has no learners."""
    require(actor, P.COURSES_ARCHIVE)
    if course.first_published_at is not None:
        raise ConflictError("Published courses can't be deleted; archive them instead.")
    if db.session.scalar(
        select(func.count(CourseEnrollment.id)).where(CourseEnrollment.course_id == course.id)
    ):
        raise ConflictError("This course has learners; archive it instead.")
    audit_service.record(
        "course.deleted", "course", course.id, actor=actor, details={"title": course.title}
    )
    db.session.delete(course)


def duplicate(course: Course, actor: User) -> Course:
    """A draft copy with the same curriculum and assessments (no learners, no product)."""
    require(actor, P.COURSES_CREATE)
    base = f"{course.slug}-copy"[:190]
    slug, n = base, 2
    while db.session.scalar(select(Course.id).where(Course.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    copy = Course(
        public_id=secrets.token_hex(8),
        slug=slug,
        title=f"{course.title} (copy)"[:200],
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    for field in DETAIL_FIELDS - {"title", "slug", "topic_ids", "product_id", "is_featured"}:
        setattr(copy, field, getattr(course, field))
    copy.topics = list(course.topics)
    db.session.add(copy)
    db.session.flush()
    lesson_map: dict[int, int] = {}
    for module in course.modules:
        new_module = CourseModule(
            course_id=copy.id,
            title=module.title,
            description=module.description,
            objectives=list(module.objectives or []),
            position=module.position,
        )
        db.session.add(new_module)
        db.session.flush()
        for lesson in module.lessons:
            # The editors' latest version (draft included); files stay with the product.
            source = {**live_lesson_fields(lesson), **(lesson.draft or {})}
            body = [b for b in source["body"] or [] if b.get("type") != "download"]
            new_lesson = CourseLesson(
                course_id=copy.id,
                module_id=new_module.id,
                slug=lesson.slug,
                title=source["title"],
                summary=source["summary"],
                body=body,
                estimated_minutes=source["estimated_minutes"],
                status="draft",
                is_preview=source["is_preview"],
                completion_required=source["completion_required"],
                position=lesson.position,
                updated_by_id=actor.id,
            )
            db.session.add(new_lesson)
            db.session.flush()
            lesson_map[lesson.id] = new_lesson.id
    for assessment in course.assessments:
        new_assessment = Assessment(
            course_id=copy.id,
            lesson_id=lesson_map.get(assessment.lesson_id),
            kind=assessment.kind,
            title=assessment.title,
            description=assessment.description,
            passing_score=assessment.passing_score,
            max_attempts=assessment.max_attempts,
            show_answers=assessment.show_answers,
            required_for_completion=assessment.required_for_completion,
            status="draft",
            position=assessment.position,
        )
        db.session.add(new_assessment)
        db.session.flush()
        for q in assessment.questions:
            db.session.add(
                AssessmentQuestion(
                    assessment_id=new_assessment.id,
                    kind=q.kind,
                    prompt=q.prompt,
                    help_text=q.help_text,
                    options=list(q.options or []),
                    correct=list(q.correct or []),
                    explanation=q.explanation,
                    settings=dict(q.settings or {}),
                    points=q.points,
                    required=q.required,
                    position=q.position,
                )
            )
    db.session.flush()
    audit_service.record(
        "course.duplicated", "course", copy.id, actor=actor, details={"source_id": course.id}
    )
    return copy


def publish_due(now: datetime | None = None) -> dict[str, list]:
    """Promote scheduled courses whose time has come (conditional update: no double run)."""
    now = now or _now()
    published, failed = [], []
    due = db.session.scalars(
        select(Course.id).where(Course.status == "scheduled", Course.published_at <= now)
    ).all()
    for course_id in due:
        try:
            with db.session.begin_nested():
                result = db.session.execute(
                    sql_update(Course)
                    .where(Course.id == course_id, Course.status == "scheduled")
                    .values(status="published", lock_version=Course.lock_version + 1)
                )
                if result.rowcount != 1:
                    continue
                course = db.session.get(Course, course_id)
                db.session.refresh(course)
                course.first_published_at = course.first_published_at or course.published_at
                record_public_change("course", course.id, "scheduled_published", None)
                audit_service.record(
                    "course.published",
                    "course",
                    course.id,
                    details={"by": "scheduler", "published_at": iso(course.published_at)},
                )
                published.append(course.slug)
        except Exception as exc:  # keep going; visible in the audit log
            failed.append(course_id)
            audit_service.record(
                "scheduler.failed", "course", course_id, details={"error": type(exc).__name__}
            )
    return {"published": published, "failed": failed}


# ---- categories -------------------------------------------------------------------------


def category_dict(category: CourseCategory, usage: int = 0) -> dict[str, Any]:
    return {
        "id": category.id,
        "slug": category.slug,
        "name": category.name,
        "description": category.description,
        "sort_order": category.sort_order,
        "is_active": category.is_active,
        "course_count": usage,
    }


def list_categories() -> list[dict[str, Any]]:
    usage = dict(
        db.session.execute(
            select(Course.category_id, func.count(Course.id)).group_by(Course.category_id)
        ).all()
    )
    return [
        category_dict(c, usage.get(c.id, 0))
        for c in db.session.scalars(
            select(CourseCategory).order_by(CourseCategory.sort_order, CourseCategory.name)
        )
    ]


def save_category(
    data: dict[str, Any], actor: User, category: CourseCategory | None = None
) -> CourseCategory:
    require(actor, P.COURSES_EDIT)
    errors: dict[str, Any] = {}
    name = data.get("name", category.name if category else None)
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 120
        or plain_text_problem(name)
    ):
        errors["name"] = ["A plain-text name of at most 120 characters is required."]
    slug = data.get("slug") or (category.slug if category else slugify(name or ""))
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        errors["slug"] = ["Use lowercase letters, numbers and hyphens."]
    elif db.session.scalar(
        select(CourseCategory.id).where(
            CourseCategory.slug == slug, CourseCategory.id != (category.id if category else 0)
        )
    ):
        errors["slug"] = ["Another category uses this address."]
    description = data.get("description", category.description if category else "")
    if (
        not isinstance(description, str)
        or len(description) > 400
        or plain_text_problem(description)
    ):
        errors["description"] = ["At most 400 characters of plain text."]
    sort_order = data.get("sort_order", category.sort_order if category else 0)
    if not isinstance(sort_order, int) or isinstance(sort_order, bool):
        errors["sort_order"] = ["Must be a number."]
    is_active = data.get("is_active", category.is_active if category else True)
    if not isinstance(is_active, bool):
        errors["is_active"] = ["Must be true or false."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    created = category is None
    category = category or CourseCategory()
    category.name, category.slug, category.description = name.strip(), slug, description.strip()
    category.sort_order, category.is_active = sort_order, is_active
    db.session.add(category)
    db.session.flush()
    audit_service.record(
        "course_category.created" if created else "course_category.updated",
        "course_category",
        category.id,
        actor=actor,
    )
    record_public_change("course_category", category.id, "course_category_saved", actor)
    return category


def delete_category(category: CourseCategory, actor: User) -> None:
    require(actor, P.COURSES_EDIT)
    if db.session.scalar(select(func.count(Course.id)).where(Course.category_id == category.id)):
        raise ConflictError("Courses use this category; move them first or deactivate it.")
    audit_service.record("course_category.deleted", "course_category", category.id, actor=actor)
    db.session.delete(category)
