"""Course content search without an external service (Batch 09.1).

What can be found depends on who asks, decided on the server:

- everyone: published catalogue data (course title, subtitle, summary) and lessons marked
  as free previews of published courses;
- signed-in learners: additionally the titles and live text of published lessons in the
  courses they can currently open (active enrolment, verified email, usable entitlement
  for premium courses — the same check as reading the lesson).

Only live, published lesson text is indexed (``course_lesson_search``); drafts, answer
keys, assessments and learners' notes are never part of it. PostgreSQL uses its English
full-text search with a GIN index; other databases (SQLite in development and tests)
fall back to case-insensitive substring matching of every word.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import and_, func, or_, select

from ...extensions import db
from ...models import (
    Course,
    CourseEnrollment,
    CourseLesson,
    CourseModule,
    Customer,
    LessonSearchDocument,
)
from ...utils.errors import ValidationError
from . import content

MAX_QUERY = 120
LIMIT = 20
_WORD = re.compile(r"[\w'’-]+", re.UNICODE)


def reindex_lesson(lesson: CourseLesson) -> None:
    """Keep the index row in step with the lesson's live state."""
    doc = db.session.get(LessonSearchDocument, lesson.id)
    if lesson.status != "published":
        if doc is not None:
            db.session.delete(doc)
        return
    text = content.lesson_text(lesson.body)
    if doc is None:
        db.session.add(
            LessonSearchDocument(lesson_id=lesson.id, course_id=lesson.course_id, content=text)
        )
    else:
        doc.content, doc.course_id = text, lesson.course_id


def _terms(query: Any) -> tuple[str, list[str]]:
    if not isinstance(query, str):
        raise ValidationError(details={"q": ["Enter something to search for."]})
    query = content.normalize(query)[:MAX_QUERY]
    terms = [t.lower() for t in _WORD.findall(query) if len(t) > 1][:8]
    if not terms:
        raise ValidationError(details={"q": ["Enter at least one word of two letters or more."]})
    return query, terms


def _like(column, terms: list[str]):
    return and_(*(func.lower(column).contains(t, autoescape=True) for t in terms))


def _text_match(query: str, terms: list[str]):
    if db.session.get_bind().dialect.name == "postgresql":
        return func.to_tsvector("english", LessonSearchDocument.content).op("@@")(
            func.websearch_to_tsquery("english", query)
        )
    return _like(LessonSearchDocument.content, terms)


def snippet(text: str, terms: list[str], width: int = 180) -> str:
    """A short extract around the first matching word (plain text)."""
    lower = text.lower()
    hits = [lower.find(t) for t in terms if lower.find(t) >= 0]
    if not hits:
        return text[:width].rstrip() + ("…" if len(text) > width else "")
    start = max(0, min(hits) - width // 3)
    end = min(len(text), start + width)
    piece = text[start:end].strip()
    return ("…" if start else "") + piece + ("…" if end < len(text) else "")


def accessible_course_ids(customer: Customer | None) -> set[int]:
    if customer is None or customer.email_verified_at is None or customer.status != "active":
        return set()
    from . import learning

    learning.sync(customer)
    ids = set()
    for enrollment in db.session.scalars(
        select(CourseEnrollment).where(CourseEnrollment.customer_id == customer.id)
    ):
        if enrollment.course.status in ("published", "archived") and (
            learning.access_state(enrollment, customer) == "active"
        ):
            ids.add(enrollment.course_id)
    return ids


def search(query: Any, customer: Customer | None = None) -> dict[str, Any]:
    query, terms = _terms(query)
    allowed = accessible_course_ids(customer)
    courses = db.session.scalars(
        select(Course)
        .where(
            Course.status == "published",
            or_(
                _like(Course.title, terms),
                _like(Course.subtitle, terms),
                _like(Course.summary, terms),
            ),
        )
        .order_by(Course.title)
        .limit(10)
    ).all()
    lesson_text = or_(
        _like(CourseLesson.title, terms),
        _like(CourseModule.title, terms),
        _text_match(query, terms),
    )
    visible = or_(
        and_(Course.status == "published", CourseLesson.is_preview.is_(True)),
        CourseLesson.course_id.in_(allowed or {0}),
    )
    rows = db.session.execute(
        select(CourseLesson, CourseModule, Course, LessonSearchDocument)
        .join(LessonSearchDocument, LessonSearchDocument.lesson_id == CourseLesson.id)
        .join(CourseModule, CourseModule.id == CourseLesson.module_id)
        .join(Course, Course.id == CourseLesson.course_id)
        .where(
            CourseLesson.status == "published",
            Course.status.in_(("published", "archived")),
            visible,
            lesson_text,
        )
        .order_by(Course.title, CourseModule.position, CourseLesson.position)
        .limit(LIMIT)
    ).all()
    lessons = [
        {
            "course": {"slug": course.slug, "title": course.title},
            "module": module.title,
            "slug": lesson.slug,
            "title": lesson.title,
            "snippet": snippet(doc.content, terms),
            "access": "enrolled" if course.id in allowed else "preview",
        }
        for lesson, module, course, doc in rows
    ]
    return {
        "query": query,
        "terms": terms,
        "signed_in": customer is not None,
        "courses": [
            {
                "slug": c.slug,
                "title": c.title,
                "summary": c.summary,
                "access_type": c.access_type,
                "enrolled": c.id in allowed,
            }
            for c in courses
        ],
        "lessons": lessons,
    }
