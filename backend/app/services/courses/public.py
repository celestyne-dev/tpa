"""Public course catalogue: what anyone (and the prerenderer) may see.

Only published courses are listed. Course pages show marketing content and the syllabus
(module and lesson titles); lesson content is never part of these payloads, except for
lessons explicitly marked as free previews, which are fetched separately. Prices come
from the linked commerce product (server-authoritative), never from the course.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import Course, CourseCategory, CourseLesson, MediaAsset, Topic
from ...models.courses import COURSE_LEVELS
from ...utils.errors import NotFoundError
from ..serializers import _author_profile, expand_body, iso
from .admin import lesson_minutes, published_lessons, total_minutes

SORTS = ("featured", "newest", "title", "shortest")


def _image(media_id: int | None, preset: str = "responsive") -> dict | None:
    asset = db.session.get(MediaAsset, media_id) if media_id else None
    if asset is None or asset.visibility != "public" or asset.status == "archived":
        return None
    return asset.as_image(preset)


def _pricing(course: Course) -> dict[str, Any]:
    if course.access_type == "free":
        return {"is_free": True, "product": None, "prices": [], "purchasable": False}
    from ..commerce import catalogue

    product = course.product
    data = catalogue.public_product(product) if product is not None else None
    if data is None:  # product unpublished or missing: not buyable, no price shown
        return {"is_free": False, "product": None, "prices": [], "purchasable": False}
    return {
        "is_free": False,
        "product": {
            "id": data["id"],
            "slug": data["slug"],
            "title": data["title"],
            "type": data["type"],
        },
        "prices": data["prices"],
        "purchasable": data["purchasable"] and course.availability == "available",
        "access": data.get("access"),
    }


def course_card(course: Course) -> dict[str, Any]:
    lessons = published_lessons(course)
    return {
        "slug": course.slug,
        "title": course.title,
        "subtitle": course.subtitle,
        "summary": course.summary,
        "cover": _image(course.cover_media_id),
        "access_type": course.access_type,
        "availability": course.availability,
        "level": course.level,
        "total_minutes": total_minutes(course),
        "lesson_count": len(lessons),
        "category": {"slug": course.category.slug, "name": course.category.name}
        if course.category and course.category.is_active
        else None,
        "topics": [{"slug": t.slug, "name": t.name} for t in course.topics if t.status == "active"],
        "featured": course.is_featured,
        "certificate": course.certificate_enabled,
        "published_at": iso(course.first_published_at or course.published_at),
        **_pricing(course),
    }


def _syllabus(course: Course, *, include_drafts: bool = False) -> list[dict[str, Any]]:
    modules = []
    for module in course.modules:
        lessons = [l for l in module.lessons if include_drafts or l.status == "published"]  # noqa: E741
        if not lessons:
            continue
        modules.append(
            {
                "title": module.title,
                "description": module.description,
                "objectives": module.objectives or [],
                "lessons": [
                    {
                        "title": lesson.title,
                        "slug": lesson.slug if lesson.is_preview else None,
                        "minutes": lesson_minutes(lesson),
                        "preview": lesson.is_preview,
                        **({"status": lesson.status} if include_drafts else {}),
                    }
                    for lesson in lessons
                ],
            }
        )
    return modules


def course_detail(course: Course, *, preview: bool = False) -> dict[str, Any]:
    author = course.author if course.author and course.author.status == "active" else None
    assessments = [a for a in course.assessments if preview or a.status == "published"]
    return {
        **course_card(course),
        "description": expand_body(course.description or []),
        "outcomes": course.outcomes or [],
        "prerequisites": course.prerequisites or [],
        "audience": course.audience or [],
        "author": _author_profile(author) if author else None,
        "syllabus": _syllabus(course, include_drafts=preview),
        "module_count": len([m for m in _syllabus(course, include_drafts=preview)]),
        "assessment_count": len(assessments),
        "quiz_count": sum(1 for a in assessments if a.kind == "quiz"),
        "enrollment_open": course.enrollment_open,
        "access_days": course.access_days if course.access_type == "free" else None,
        "seo": {
            "title": course.seo_title or course.title,
            "description": course.meta_description or course.summary,
            "image": _image(course.social_image_id, "social")
            or _image(course.cover_media_id, "social"),
            "noindex": course.noindex,
        },
        "updated_at": iso(course.updated_at),
        "preview": preview,
        "related": [] if preview else related(course),
    }


def related(course: Course, limit: int = 3) -> list[dict[str, Any]]:
    topic_ids = {t.id for t in course.topics}
    candidates = db.session.scalars(
        select(Course).where(Course.status == "published", Course.id != course.id)
    ).all()

    def score(other: Course) -> tuple:
        shared = len(topic_ids & {t.id for t in other.topics})
        same = int(course.category_id is not None and other.category_id == course.category_id)
        return (same + shared, other.is_featured, other.published_at or other.created_at)

    ranked = sorted(candidates, key=score, reverse=True)
    return [course_card(c) for c in ranked if score(c)[0] > 0][:limit] or [
        course_card(c) for c in ranked
    ][:limit]


def published_by_slug(slug: str) -> Course:
    course = db.session.scalar(
        select(Course).where(Course.slug == slug, Course.status == "published")
    )
    if course is None:
        raise NotFoundError("Course not found.")
    return course


def list_public(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    courses = db.session.scalars(select(Course).where(Course.status == "published")).all()
    all_courses = list(courses)
    q = (args.get("q") or "").strip().lower()[:100]
    if q:
        courses = [
            c
            for c in courses
            if q in c.title.lower()
            or q in c.summary.lower()
            or q in c.subtitle.lower()
            or any(q in o.lower() for o in c.outcomes or [])
        ]
    if args.get("category"):
        courses = [c for c in courses if c.category and c.category.slug == args["category"]]
    if args.get("topic"):
        courses = [c for c in courses if any(t.slug == args["topic"] for t in c.topics)]
    if args.get("access") in ("free", "premium"):
        courses = [c for c in courses if c.access_type == args["access"]]
    if args.get("level") in COURSE_LEVELS:
        courses = [c for c in courses if c.level == args["level"]]
    sort = args.get("sort") if args.get("sort") in SORTS else "featured"
    if sort == "newest":
        courses.sort(key=lambda c: c.first_published_at or c.published_at, reverse=True)
    elif sort == "title":
        courses.sort(key=lambda c: c.title.lower())
    elif sort == "shortest":
        courses.sort(key=total_minutes)
    else:
        courses.sort(
            key=lambda c: (
                not c.is_featured,
                c.featured_order,
                -(c.first_published_at or c.published_at).timestamp(),
            )
        )
    used_categories = {c.category_id for c in all_courses if c.category_id}
    categories = (
        db.session.scalars(
            select(CourseCategory)
            .where(CourseCategory.id.in_(used_categories), CourseCategory.is_active.is_(True))
            .order_by(CourseCategory.sort_order, CourseCategory.name)
        ).all()
        if used_categories
        else []
    )
    topics = sorted(
        {(t.slug, t.name) for c in all_courses for t in c.topics if t.status == "active"},
        key=lambda pair: pair[1],
    )
    meta = {
        "total": len(courses),
        "categories": [{"slug": c.slug, "name": c.name} for c in categories],
        "topics": [{"slug": slug, "name": name} for slug, name in topics],
        "sorts": list(SORTS),
    }
    return [course_card(c) for c in courses], meta


def preview_lesson(course_slug: str, lesson_slug: str) -> dict[str, Any]:
    course = published_by_slug(course_slug)
    lesson = db.session.scalar(
        select(CourseLesson).where(
            CourseLesson.course_id == course.id,
            CourseLesson.slug == lesson_slug,
            CourseLesson.status == "published",
            CourseLesson.is_preview.is_(True),
        )
    )
    if lesson is None:
        raise NotFoundError("Lesson not found.")
    # Worksheets stay behind enrolment even in a free preview.
    body = [b for b in expand_body(lesson.body or []) if b.get("type") != "download"]
    return {
        "course": {
            "slug": course.slug,
            "title": course.title,
            **_pricing(course),
            "access_type": course.access_type,
        },
        "lesson": {
            "slug": lesson.slug,
            "title": lesson.title,
            "summary": lesson.summary,
            "minutes": lesson_minutes(lesson),
            "body": body,
        },
    }


def sitemap_entries() -> list[dict[str, Any]]:
    rows = db.session.execute(
        select(Course.slug, Course.updated_at).where(
            Course.status == "published", Course.noindex.is_(False)
        )
    ).all()
    return [{"path": f"/courses/{slug}", "lastmod": iso(updated)} for slug, updated in rows]


def published_count() -> int:
    return db.session.scalar(select(func.count(Course.id)).where(Course.status == "published")) or 0


def topic_ids_in_use() -> set[int]:
    return set(
        db.session.scalars(select(Topic.id).join(Course.topics).where(Course.status == "published"))
    )
