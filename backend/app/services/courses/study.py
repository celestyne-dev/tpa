"""Private study tools for learners (Batch 09.1).

Notes, highlights, bookmarks, saved checklist ticks, the reading position and reading
preferences belong to one customer. Rules, enforced here for every request:

- Creating or changing anything tied to a lesson needs current access to the course
  (``learning.require_access``: verified email, active enrolment, usable entitlement).
  Expired, refunded or revoked access blocks it, and bookmarks are only links: opening
  one goes through the same check.
- A learner's own notes stay readable and deletable after access ends, but saved
  excerpts (highlight quotes, passages a note points at) are hidden while the learner
  can't open the course or the lesson isn't published, so nothing protected leaks.
- Records are looked up by the owner's id plus a random public id: another learner's
  id answers 404. Staff endpoints never return these records.
- Checklist ticks are reading aids; they only affect completion when an editor marks a
  checklist *required* (the lesson then needs every item ticked).
- The reading position is written by the reader at most every few seconds, never on
  every scroll event, and never completes a lesson.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import (
    Course,
    CourseEnrollment,
    CourseLesson,
    Customer,
    LearnerBookmark,
    LearnerHighlight,
    LearnerNote,
    LearnerPreference,
    LessonProgress,
)
from ...models.courses import HIGHLIGHT_COLORS
from ...utils.errors import NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from ..serializers import iso
from . import anchors, content

MAX_NOTE = 10_000
MAX_NOTES_PER_COURSE = 1000
MAX_HIGHLIGHTS_PER_COURSE = 2000
READING_DEFAULTS = {
    "font_size": "medium",
    "line_spacing": "standard",
    "width": "standard",
    "theme": "light",
}
READING_CHOICES = {
    "font_size": ("small", "medium", "large"),
    "line_spacing": ("standard", "comfortable"),
    "width": ("standard", "wide"),
    "theme": ("light", "warm", "dark"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _public_id() -> str:
    return secrets.token_urlsafe(12)


def _learning():
    from . import learning

    return learning


def _lesson_for(customer: Customer, course: Course, lesson_slug: str):
    learning = _learning()
    enrollment = learning.require_access(customer, course)
    return enrollment, learning._find_lesson(course, lesson_slug)


# ---- access and serialisation -------------------------------------------------------------


def access_by_course(customer: Customer) -> dict[int, bool]:
    """Which of the customer's courses they can open right now."""
    learning = _learning()
    verified = customer.email_verified_at is not None and customer.status == "active"
    out = {}
    for enrollment in db.session.scalars(
        select(CourseEnrollment).where(CourseEnrollment.customer_id == customer.id)
    ):
        out[enrollment.course_id] = (
            verified
            and enrollment.course.status in ("published", "archived")
            and learning.access_state(enrollment, customer) == "active"
        )
    return out


def _lesson_ref(lesson: CourseLesson | None, title: str, open_: bool) -> dict[str, Any]:
    live = lesson is not None and lesson.status == "published"
    return {
        "slug": lesson.slug if live and open_ else None,
        "title": (lesson.title if live else None) or title or "Removed lesson",
        "available": live and open_,
    }


def _anchor_out(anchor: dict | None, status: str | None, visible: bool) -> dict | None:
    if not anchor:
        return None
    if not visible:
        return {"hidden": True, "status": status}
    return {
        "block": anchor.get("block"),
        "quote": anchor.get("quote"),
        "prefix": anchor.get("prefix"),
        "suffix": anchor.get("suffix"),
        "start": anchor.get("start"),
        "end": anchor.get("end"),
        "status": status,
    }


def note_dict(note: LearnerNote, open_: bool, course: Course | None = None) -> dict[str, Any]:
    course = course or db.session.get(Course, note.course_id)
    lesson = db.session.get(CourseLesson, note.lesson_id) if note.lesson_id else None
    ref = _lesson_ref(lesson, note.lesson_title, open_)
    return {
        "id": note.public_id,
        "course": {"slug": course.slug, "title": course.title},
        "lesson": ref,
        "body": note.body,
        "anchor": _anchor_out(note.anchor, note.anchor_status, ref["available"]),
        "created_at": iso(note.created_at),
        "updated_at": iso(note.updated_at),
    }


def highlight_dict(
    highlight: LearnerHighlight, open_: bool, course: Course | None = None
) -> dict[str, Any]:
    course = course or db.session.get(Course, highlight.course_id)
    lesson = db.session.get(CourseLesson, highlight.lesson_id) if highlight.lesson_id else None
    ref = _lesson_ref(lesson, highlight.lesson_title, open_)
    return {
        "id": highlight.public_id,
        "course": {"slug": course.slug, "title": course.title},
        "lesson": ref,
        "color": highlight.color,
        "anchor": _anchor_out(highlight.anchor, highlight.anchor_status, ref["available"]),
        "status": highlight.anchor_status,
        "created_at": iso(highlight.created_at),
        "updated_at": iso(highlight.updated_at),
    }


def lesson_state(customer: Customer, lesson: CourseLesson, row: LessonProgress) -> dict:
    """Study data the reader needs for one lesson (the learner has access)."""
    notes = db.session.scalars(
        select(LearnerNote)
        .where(LearnerNote.customer_id == customer.id, LearnerNote.lesson_id == lesson.id)
        .order_by(LearnerNote.created_at)
    ).all()
    highlights = db.session.scalars(
        select(LearnerHighlight)
        .where(LearnerHighlight.customer_id == customer.id, LearnerHighlight.lesson_id == lesson.id)
        .order_by(LearnerHighlight.created_at)
    ).all()
    course = db.session.get(Course, lesson.course_id)
    bookmarked = db.session.scalar(
        select(LearnerBookmark.id).where(
            LearnerBookmark.customer_id == customer.id, LearnerBookmark.lesson_id == lesson.id
        )
    )
    valid_items = content.checklist_item_ids(lesson.body)
    return {
        "notes": [note_dict(n, True, course) for n in notes],
        "highlights": [highlight_dict(h, True, course) for h in highlights],
        "bookmarked": bookmarked is not None,
        "checklist": [i for i in (row.checklist or []) if i in valid_items],
        "position": row.position,
    }


# ---- notes ---------------------------------------------------------------------------------


def _note_body(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError(details={"body": ["Write your note as text."]})
    value = value.strip()
    if not value or len(value) > MAX_NOTE:
        raise ValidationError(details={"body": [f"Write between 1 and {MAX_NOTE} characters."]})
    if problem := plain_text_problem(value):
        raise ValidationError(details={"body": [problem]})
    return value


def _own(model, customer: Customer, public_id: str):
    row = db.session.scalar(
        select(model).where(model.public_id == public_id, model.customer_id == customer.id)
    )
    if row is None:
        raise NotFoundError("Not found.")
    return row


def _cap(model, customer: Customer, course: Course, limit: int, label: str) -> None:
    count = db.session.scalar(
        select(func.count(model.id)).where(
            model.customer_id == customer.id, model.course_id == course.id
        )
    )
    if count >= limit:
        raise ValidationError(f"You can keep up to {limit} {label} per course.")


def create_note(customer: Customer, course: Course, lesson_slug: str, data: Any) -> dict:
    enrollment, lesson = _lesson_for(customer, course, lesson_slug)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    if set(data) - {"body", "anchor"}:
        raise ValidationError("Unknown fields.")
    _cap(LearnerNote, customer, course, MAX_NOTES_PER_COURSE, "notes")
    body = _note_body(data.get("body"))
    anchor = anchors.create(lesson.body, data["anchor"]) if data.get("anchor") else None
    note = LearnerNote(
        public_id=_public_id(),
        customer_id=customer.id,
        course_id=course.id,
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        body=body,
        anchor=anchor,
        anchor_status="anchored" if anchor else None,
    )
    db.session.add(note)
    enrollment.last_activity_at = _now()
    db.session.flush()
    return note_dict(note, True, course)


def update_note(customer: Customer, public_id: str, data: Any) -> dict:
    note = _own(LearnerNote, customer, public_id)
    if not isinstance(data, dict) or set(data) - {"body", "anchor"}:
        raise ValidationError("Send the note text.")
    if "body" in data:
        note.body = _note_body(data["body"])
    if "anchor" in data:
        if data["anchor"] is not None:
            raise ValidationError(details={"anchor": ["A passage can only be removed."]})
        note.anchor, note.anchor_status = None, None
    note.updated_at = _now()
    db.session.flush()
    return note_dict(note, access_by_course(customer).get(note.course_id, False))


def delete_note(customer: Customer, public_id: str) -> None:
    db.session.delete(_own(LearnerNote, customer, public_id))


# ---- highlights ----------------------------------------------------------------------------


def _color(value: Any) -> str:
    if value not in HIGHLIGHT_COLORS:
        raise ValidationError(details={"color": [f"Choose one of: {', '.join(HIGHLIGHT_COLORS)}."]})
    return value


def create_highlight(customer: Customer, course: Course, lesson_slug: str, data: Any) -> dict:
    enrollment, lesson = _lesson_for(customer, course, lesson_slug)
    if not isinstance(data, dict) or set(data) - {"anchor", "color"}:
        raise ValidationError("Send the passage and a colour.")
    _cap(LearnerHighlight, customer, course, MAX_HIGHLIGHTS_PER_COURSE, "highlights")
    anchor = anchors.create(lesson.body, data.get("anchor"))
    existing = next(
        (
            h
            for h in db.session.scalars(
                select(LearnerHighlight).where(
                    LearnerHighlight.customer_id == customer.id,
                    LearnerHighlight.lesson_id == lesson.id,
                    LearnerHighlight.anchor_status == "anchored",
                )
            )
            if h.anchor.get("block") == anchor["block"]
            and h.anchor.get("start") == anchor["start"]
            and h.anchor.get("end") == anchor["end"]
        ),
        None,
    )
    if existing is not None:  # the same passage twice: keep one, update its colour
        existing.color = _color(data.get("color", existing.color))
        db.session.flush()
        return highlight_dict(existing, True, course)
    highlight = LearnerHighlight(
        public_id=_public_id(),
        customer_id=customer.id,
        course_id=course.id,
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        color=_color(data.get("color", "yellow")),
        anchor=anchor,
        anchor_status="anchored",
        anchored_revision=lesson.live_revision,
    )
    db.session.add(highlight)
    enrollment.last_activity_at = _now()
    db.session.flush()
    return highlight_dict(highlight, True, course)


def update_highlight(customer: Customer, public_id: str, data: Any) -> dict:
    highlight = _own(LearnerHighlight, customer, public_id)
    if not isinstance(data, dict) or set(data) != {"color"}:
        raise ValidationError("Send the new colour.")
    highlight.color = _color(data["color"])
    highlight.updated_at = _now()
    db.session.flush()
    return highlight_dict(highlight, access_by_course(customer).get(highlight.course_id, False))


def delete_highlight(customer: Customer, public_id: str) -> None:
    db.session.delete(_own(LearnerHighlight, customer, public_id))


def reanchor_lesson(lesson: CourseLesson) -> dict[str, int]:
    """After a lesson is (re)published: re-match every learner's anchors on it."""
    counts = {"kept": 0, "moved": 0, "orphaned": 0}
    rows = list(
        db.session.scalars(select(LearnerHighlight).where(LearnerHighlight.lesson_id == lesson.id))
    ) + list(
        db.session.scalars(
            select(LearnerNote).where(
                LearnerNote.lesson_id == lesson.id, LearnerNote.anchor.is_not(None)
            )
        )
    )
    for row in rows:
        found = anchors.resolve(row.anchor, lesson.body)
        if found is None:
            row.anchor_status = "orphaned"
            counts["orphaned"] += 1
            continue
        moved = (found["block"], found["start"]) != (
            row.anchor.get("block"),
            row.anchor.get("start"),
        )
        counts["moved" if moved else "kept"] += 1
        row.anchor, row.anchor_status = found, "anchored"
        if isinstance(row, LearnerHighlight):
            row.anchored_revision = lesson.live_revision
        row.lesson_title = lesson.title
    return counts


# ---- bookmarks, checklists, position ---------------------------------------------------------


def set_bookmark(customer: Customer, course: Course, lesson_slug: str, on: Any) -> dict:
    _, lesson = _lesson_for(customer, course, lesson_slug)
    if not isinstance(on, bool):
        raise ValidationError(details={"bookmarked": ["Must be true or false."]})
    existing = db.session.scalar(
        select(LearnerBookmark).where(
            LearnerBookmark.customer_id == customer.id, LearnerBookmark.lesson_id == lesson.id
        )
    )
    if on and existing is None:
        from sqlalchemy.exc import IntegrityError

        try:
            with db.session.begin_nested():
                db.session.add(
                    LearnerBookmark(
                        customer_id=customer.id, course_id=course.id, lesson_id=lesson.id
                    )
                )
                db.session.flush()
        except IntegrityError:
            pass  # saved by a concurrent request
    elif not on and existing is not None:
        db.session.delete(existing)
    return {"bookmarked": on}


def set_checklist_item(
    customer: Customer, course: Course, lesson_slug: str, item_id: str, data: Any
) -> dict:
    learning = _learning()
    enrollment, lesson = _lesson_for(customer, course, lesson_slug)
    valid = content.checklist_item_ids(lesson.body)
    if item_id not in valid:
        raise NotFoundError("Checklist item not found.")
    if not isinstance(data, dict) or not isinstance(data.get("checked"), bool):
        raise ValidationError(details={"checked": ["Must be true or false."]})
    row = learning._lesson_row(enrollment, lesson)
    ticked = set(row.checklist or [])
    (ticked.add if data["checked"] else ticked.discard)(item_id)
    row.checklist = sorted(ticked)
    learning._touch(enrollment, lesson)
    return {"checklist": [i for i in row.checklist if i in valid]}


def save_position(customer: Customer, course: Course, lesson_slug: str, data: Any) -> dict:
    learning = _learning()
    enrollment, lesson = _lesson_for(customer, course, lesson_slug)
    if not isinstance(data, dict) or set(data) - {"block", "percent"}:
        raise ValidationError("Send the block and percentage read.")
    block, percent = data.get("block"), data.get("percent")
    uids = {b.get("uid") for b in lesson.body or []}
    if block is not None and block not in uids:
        raise ValidationError(details={"block": ["Unknown block."]})
    if not isinstance(percent, int | float) or isinstance(percent, bool) or not 0 <= percent <= 100:
        raise ValidationError(details={"percent": ["Use a number from 0 to 100."]})
    row = learning._lesson_row(enrollment, lesson)
    row.position = {"block": block, "percent": round(float(percent), 1)}
    row.position_saved_at = row.last_viewed_at = _now()
    learning._touch(enrollment, lesson)
    return {"position": row.position}


# ---- preferences ---------------------------------------------------------------------------


def get_preferences(customer: Customer) -> dict:
    row = db.session.scalar(
        select(LearnerPreference).where(LearnerPreference.customer_id == customer.id)
    )
    return {**READING_DEFAULTS, **((row.reading if row else None) or {})}


def save_preferences(customer: Customer, data: Any) -> dict:
    if not isinstance(data, dict) or not data or set(data) - set(READING_CHOICES):
        raise ValidationError("Send reading preferences.")
    for key, value in data.items():
        if value not in READING_CHOICES[key]:
            raise ValidationError(details={key: [f"Choose {', '.join(READING_CHOICES[key])}."]})
    row = db.session.scalar(
        select(LearnerPreference).where(LearnerPreference.customer_id == customer.id)
    )
    if row is None:
        row = LearnerPreference(customer_id=customer.id, reading={})
        db.session.add(row)
    row.reading = {**READING_DEFAULTS, **(row.reading or {}), **data}
    db.session.flush()
    return dict(row.reading)


# ---- notebook ------------------------------------------------------------------------------


def _filters(args: dict) -> tuple[str | None, str]:
    course = args.get("course") or None
    q = content.normalize(str(args.get("q") or ""))[:120].lower()
    return course, q


def notebook(customer: Customer, args: dict | None = None) -> dict[str, Any]:
    """The learner's notes, highlights, bookmarks and checklist activity (own data only)."""
    args = args or {}
    course_slug, q = _filters(args)
    access = access_by_course(customer)
    course_ids = set(access)
    for model in (LearnerNote, LearnerHighlight, LearnerBookmark):
        course_ids |= set(
            db.session.scalars(select(model.course_id).where(model.customer_id == customer.id))
        )
    courses = {
        c.id: c for c in db.session.scalars(select(Course).where(Course.id.in_(course_ids or {0})))
    }
    wanted = {cid for cid, c in courses.items() if course_slug in (None, c.slug)}

    def match(*texts: str | None) -> bool:
        return not q or any(q in (t or "").lower() for t in texts)

    notes = []
    for note in db.session.scalars(
        select(LearnerNote)
        .where(LearnerNote.customer_id == customer.id, LearnerNote.course_id.in_(wanted or {0}))
        .order_by(LearnerNote.updated_at.desc())
    ):
        item = note_dict(note, access.get(note.course_id, False), courses[note.course_id])
        quote = (item["anchor"] or {}).get("quote")
        if match(item["body"], quote, item["lesson"]["title"], item["course"]["title"]):
            notes.append(item)
    highlights = []
    for highlight in db.session.scalars(
        select(LearnerHighlight)
        .where(
            LearnerHighlight.customer_id == customer.id,
            LearnerHighlight.course_id.in_(wanted or {0}),
        )
        .order_by(LearnerHighlight.created_at.desc())
    ):
        item = highlight_dict(
            highlight, access.get(highlight.course_id, False), courses[highlight.course_id]
        )
        quote = (item["anchor"] or {}).get("quote")
        if match(quote, item["lesson"]["title"], item["course"]["title"]):
            highlights.append(item)
    bookmarks = []
    for bookmark, lesson in db.session.execute(
        select(LearnerBookmark, CourseLesson)
        .join(CourseLesson, CourseLesson.id == LearnerBookmark.lesson_id)
        .where(
            LearnerBookmark.customer_id == customer.id,
            LearnerBookmark.course_id.in_(wanted or {0}),
        )
        .order_by(LearnerBookmark.created_at.desc())
    ):
        course = courses[bookmark.course_id]
        open_ = access.get(course.id, False)
        ref = _lesson_ref(lesson, lesson.title, open_)
        if match(ref["title"], course.title):
            bookmarks.append(
                {
                    "course": {"slug": course.slug, "title": course.title},
                    "lesson": ref,
                    "access": "active" if open_ else "ended",
                    "created_at": iso(bookmark.created_at),
                }
            )
    checklists = []
    for row, enrollment in db.session.execute(
        select(LessonProgress, CourseEnrollment)
        .join(CourseEnrollment, CourseEnrollment.id == LessonProgress.enrollment_id)
        .where(
            CourseEnrollment.customer_id == customer.id,
            CourseEnrollment.course_id.in_(wanted or {0}),
        )
    ):
        if not row.checklist:
            continue
        lesson = db.session.get(CourseLesson, row.lesson_id)
        if lesson is None or lesson.status != "published":
            continue
        open_ = access.get(enrollment.course_id, False)
        lists = []
        for block in lesson.body or []:
            if block.get("type") != "checklist":
                continue
            items = block.get("items", [])
            done = [i for i in items if isinstance(i, dict) and i.get("id") in row.checklist]
            if done:
                lists.append(
                    {
                        "title": (block.get("title") or "Checklist") if open_ else "Checklist",
                        "done": len(done),
                        "total": len(items),
                        "required": bool(block.get("required")),
                    }
                )
        course = courses[enrollment.course_id]
        ref = _lesson_ref(lesson, lesson.title, open_)
        if lists and match(ref["title"], course.title, *(entry["title"] for entry in lists)):
            checklists.append(
                {
                    "course": {"slug": course.slug, "title": course.title},
                    "lesson": ref,
                    "lists": lists,
                    "updated_at": iso(row.last_viewed_at),
                }
            )
    return {
        "courses": [
            {"slug": c.slug, "title": c.title, "access": access.get(c.id, False)}
            for c in sorted(courses.values(), key=lambda c: c.title.lower())
        ],
        "notes": notes,
        "highlights": highlights,
        "bookmarks": bookmarks,
        "checklists": checklists,
    }


# ---- export --------------------------------------------------------------------------------


def _export_sections(customer: Customer, course_slug: str | None) -> list[tuple[str, list[str]]]:
    data = notebook(customer, {"course": course_slug} if course_slug else {})
    sections: dict[str, list[str]] = {}
    for item in data["highlights"]:
        quote = (item["anchor"] or {}).get("quote")
        line = f"Highlight ({item['color']}) — {item['lesson']['title']}: "
        line += f"“{quote}”" if quote else "[excerpt hidden while you can't open this course]"
        if item["status"] == "orphaned":
            line += " (saved excerpt; the lesson text has changed)"
        sections.setdefault(item["course"]["title"], []).append(line)
    for item in data["notes"]:
        quote = (item["anchor"] or {}).get("quote")
        header = f"Note — {item['lesson']['title']}"
        if quote:
            header += f" (on “{quote}”)"
        sections.setdefault(item["course"]["title"], []).append(f"{header}:\n{item['body']}")
    for item in data["bookmarks"]:
        sections.setdefault(item["course"]["title"], []).append(
            f"Bookmarked lesson: {item['lesson']['title']}"
        )
    return sorted(sections.items(), key=lambda pair: pair[0].lower())


def export(customer: Customer, fmt: str, course_slug: str | None = None) -> tuple[bytes, str, str]:
    """The learner's own notes, highlight excerpts and bookmarks as text or PDF."""
    if fmt not in ("txt", "pdf"):
        raise ValidationError(details={"format": ["Use txt or pdf."]})
    sections = _export_sections(customer, course_slug)
    stamp = _now().strftime("%Y-%m-%d")
    title = "My study notebook — Think Positive Always"
    if fmt == "txt":
        lines = [title, f"Exported {stamp}", ""]
        if not sections:
            lines.append("You haven't saved any notes, highlights or bookmarks yet.")
        for course, entries in sections:
            lines += [course, "=" * min(len(course), 60), ""]
            for entry in entries:
                lines += [entry, ""]
        return (
            ("\n".join(lines) + "\n").encode(),
            "text/plain; charset=utf-8",
            f"study-notebook-{stamp}.txt",
        )
    from .pdf import Page, render_pages, wrap

    pages = [Page(width=612, height=792)]  # US Letter, portrait
    y = 740.0

    def write(text: str, *, size: float = 10.5, font: str = "regular", gap: float = 4) -> None:
        nonlocal y
        for line in text.split("\n") or [""]:
            for piece in wrap(line, font, size, 504, max_lines=200) or [""]:
                if y < 56:
                    pages.append(Page(width=612, height=792))
                    y = 740.0
                pages[-1].text(piece, x=54, y=y, size=size, font=font)
                y -= size + 4
        y -= gap

    write(title, size=18, font="bold")
    write(f"Exported {stamp}", size=10, gap=12)
    if not sections:
        write("You haven't saved any notes, highlights or bookmarks yet.")
    for course, entries in sections:
        write(course, size=14, font="bold", gap=6)
        for entry in entries:
            write(entry, gap=8)
    return render_pages(pages, title), "application/pdf", f"study-notebook-{stamp}.pdf"


# ---- personal data -------------------------------------------------------------------------


def export_data(customer: Customer) -> dict[str, Any]:
    """For the account data export: everything saved, including hidden excerpts (the
    learner's own records), plus reading preferences."""
    notes = [
        {
            "course_id": n.course_id,
            "lesson": n.lesson_title,
            "body": n.body,
            "passage": (n.anchor or {}).get("quote"),
            "created_at": iso(n.created_at),
            "updated_at": iso(n.updated_at),
        }
        for n in db.session.scalars(
            select(LearnerNote).where(LearnerNote.customer_id == customer.id)
        )
    ]
    highlights = [
        {
            "course_id": h.course_id,
            "lesson": h.lesson_title,
            "color": h.color,
            "passage": h.anchor.get("quote"),
            "status": h.anchor_status,
            "created_at": iso(h.created_at),
        }
        for h in db.session.scalars(
            select(LearnerHighlight).where(LearnerHighlight.customer_id == customer.id)
        )
    ]
    bookmarks = [
        {"course_id": b.course_id, "lesson_id": b.lesson_id, "created_at": iso(b.created_at)}
        for b in db.session.scalars(
            select(LearnerBookmark).where(LearnerBookmark.customer_id == customer.id)
        )
    ]
    return {
        "notes": notes,
        "highlights": highlights,
        "bookmarks": bookmarks,
        "reading_preferences": get_preferences(customer),
    }


def erase(customer: Customer) -> None:
    """Account deletion: remove every private study record of the customer."""
    for model in (LearnerNote, LearnerHighlight, LearnerBookmark, LearnerPreference):
        for row in db.session.scalars(select(model).where(model.customer_id == customer.id)):
            db.session.delete(row)
    for row in db.session.scalars(
        select(LessonProgress).where(
            LessonProgress.enrollment_id.in_(
                select(CourseEnrollment.id).where(CourseEnrollment.customer_id == customer.id)
            )
        )
    ):
        row.checklist, row.position = [], None
