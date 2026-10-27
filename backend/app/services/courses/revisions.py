"""Lesson drafts, publication and revision history (Batch 09.1).

The live columns of ``CourseLesson`` hold what learners read. Editors change a working
copy (``CourseLesson.draft``; None when it equals the live content), so saving never
changes a published lesson. Publishing copies the working copy to the live columns,
stores an immutable numbered ``LessonRevision``, re-indexes the lesson for search and
re-matches learners' highlights and passage notes. Restoring copies an earlier revision
back into the working copy (and can publish it straight away). Every save checks
``lock_version`` so two editors can't silently overwrite each other; publication,
restoration and discarding are written to the audit log.
"""

from __future__ import annotations

import difflib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Course, CourseLesson, LessonRevision, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import expand_body, iso
from . import content
from .admin import require, touch_public

DRAFT_FIELDS = (
    "title",
    "summary",
    "body",
    "estimated_minutes",
    "is_preview",
    "completion_required",
)


class EditConflictError(ConflictError):
    code = "edit_conflict"
    message = "Someone else saved this lesson after you opened it."


def _now() -> datetime:
    return datetime.now(UTC)


def live_snapshot(lesson: CourseLesson) -> dict[str, Any]:
    return {
        "title": lesson.title,
        "summary": lesson.summary or "",
        "body": lesson.body or [],
        "estimated_minutes": lesson.estimated_minutes,
        "is_preview": bool(lesson.is_preview),
        "completion_required": bool(lesson.completion_required),
    }


def revision_snapshot(revision: LessonRevision) -> dict[str, Any]:
    return {
        "title": revision.title,
        "summary": revision.summary or "",
        "body": revision.body or [],
        "estimated_minutes": revision.estimated_minutes,
        "is_preview": bool(revision.is_preview),
        "completion_required": bool(revision.completion_required),
    }


def working(lesson: CourseLesson) -> dict[str, Any]:
    """The editors' current version (the draft, or the live content when unchanged)."""
    if lesson.draft:
        return {
            field: lesson.draft.get(field, value) for field, value in live_snapshot(lesson).items()
        }
    return live_snapshot(lesson)


def _user_name(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.session.get(User, user_id)
    return (user.display_name or user.email) if user is not None else None


def check_lock(lesson: CourseLesson, data: dict[str, Any]) -> None:
    version = data.get("lock_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValidationError(
            details={"lock_version": ["Reload the lesson before saving (missing version)."]}
        )
    if version != lesson.lock_version:
        raise EditConflictError(
            details={
                "lock_version": lesson.lock_version,
                "saved_at": iso(lesson.draft_saved_at or lesson.updated_at),
                "saved_by": _user_name(lesson.draft_saved_by_id or lesson.updated_by_id),
            }
        )


def store_working(lesson: CourseLesson, new: dict[str, Any], actor: User) -> None:
    lesson.draft = None if new == live_snapshot(lesson) else new
    lesson.lock_version += 1
    lesson.draft_saved_at = _now()
    lesson.draft_saved_by_id = actor.id
    lesson.updated_by_id = actor.id


def _next_number(lesson: CourseLesson) -> int:
    last = db.session.scalar(
        select(func.max(LessonRevision.number)).where(LessonRevision.lesson_id == lesson.id)
    )
    return (last or 0) + 1


def _editable(course: Course) -> None:
    if course.status == "archived":
        raise ConflictError("Restore this course before changing its curriculum.")


def _after_live_change(course: Course, lesson: CourseLesson, actor: User) -> None:
    from . import search, study

    search.reindex_lesson(lesson)
    study.reanchor_lesson(lesson)
    touch_public(course, "course_curriculum", actor)


def publish(
    course: Course,
    lesson: CourseLesson,
    actor: User,
    *,
    note: str = "",
    action: str = "published",
    restored_from: int | None = None,
) -> LessonRevision | None:
    """Make the working copy live. Returns the new revision (None if nothing changed)."""
    require(actor, P.COURSES_PUBLISH_LESSONS)
    _editable(course)
    current = working(lesson)
    if not current["body"]:
        raise ValidationError("Add some content before publishing this lesson.")
    if not isinstance(note, str) or len(note) > 300:
        raise ValidationError(details={"note": ["At most 300 characters."]})
    changed = lesson.draft is not None or lesson.live_revision is None
    was_live = lesson.status == "published"
    if not changed and was_live:
        return None
    revision = None
    if changed:
        for field, value in current.items():
            setattr(lesson, field, value)
        revision = LessonRevision(
            lesson_id=lesson.id,
            number=_next_number(lesson),
            action=action,
            note=note.strip(),
            restored_from=restored_from,
            created_by_id=actor.id,
            **current,
        )
        db.session.add(revision)
        lesson.live_revision = revision.number
        lesson.content_published_at = _now()
        lesson.draft = None
        lesson.lock_version += 1
        lesson.updated_by_id = actor.id
    lesson.status = "published"
    db.session.flush()
    audit_service.record(
        "course.lesson_published",
        "course",
        course.id,
        actor=actor,
        details={
            "lesson_id": lesson.id,
            "title": lesson.title,
            "revision": lesson.live_revision,
            "new_revision": changed,
            **({"restored_from": restored_from} if restored_from else {}),
        },
    )
    _after_live_change(course, lesson, actor)
    return revision


def unpublish(course: Course, lesson: CourseLesson, actor: User) -> None:
    require(actor, P.COURSES_PUBLISH_LESSONS)
    _editable(course)
    if lesson.status != "published":
        return
    lesson.status = "draft"
    db.session.flush()
    audit_service.record(
        "course.lesson_unpublished",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title},
    )
    from . import search

    search.reindex_lesson(lesson)
    touch_public(course, "course_curriculum", actor)


def discard_draft(course: Course, lesson: CourseLesson, data: dict, actor: User) -> None:
    require(actor, P.COURSES_EDIT_DRAFTS)
    _editable(course)
    check_lock(lesson, data)
    if lesson.draft is None:
        return
    lesson.draft = None
    lesson.lock_version += 1
    lesson.draft_saved_at, lesson.draft_saved_by_id = _now(), actor.id
    audit_service.record(
        "course.lesson_draft_discarded",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title},
    )


def get_revision(lesson: CourseLesson, number: int) -> LessonRevision:
    revision = db.session.scalar(
        select(LessonRevision).where(
            LessonRevision.lesson_id == lesson.id, LessonRevision.number == number
        )
    )
    if revision is None:
        raise NotFoundError("Revision not found.")
    return revision


def restore(
    course: Course, lesson: CourseLesson, number: int, data: dict, actor: User
) -> LessonRevision | None:
    """Copy revision ``number`` into the working copy; optionally publish it at once."""
    require(actor, P.COURSES_RESTORE_REVISIONS)
    _editable(course)
    check_lock(lesson, data)
    revision = get_revision(lesson, number)
    publish_now = data.get("publish", False)
    if not isinstance(publish_now, bool):
        raise ValidationError(details={"publish": ["Must be true or false."]})
    if publish_now:
        require(actor, P.COURSES_PUBLISH_LESSONS)
    store_working(lesson, revision_snapshot(revision), actor)
    db.session.flush()
    audit_service.record(
        "course.lesson_revision_restored",
        "course",
        course.id,
        actor=actor,
        details={"lesson_id": lesson.id, "title": lesson.title, "revision": number},
    )
    if publish_now:
        return publish(
            course,
            lesson,
            actor,
            note=f"Restored revision {number}",
            action="restored",
            restored_from=number,
        )
    return None


# ---- history and comparison --------------------------------------------------------------


def revision_summary(lesson: CourseLesson, revision: LessonRevision) -> dict[str, Any]:
    return {
        "number": revision.number,
        "title": revision.title,
        "action": revision.action,
        "note": revision.note,
        "restored_from": revision.restored_from,
        "created_at": iso(revision.created_at),
        "created_by": _user_name(revision.created_by_id),
        "live": revision.number == lesson.live_revision and lesson.status == "published",
    }


def history(lesson: CourseLesson, actor: User) -> list[dict[str, Any]]:
    require(actor, P.COURSES_VIEW_REVISIONS)
    rows = db.session.scalars(
        select(LessonRevision)
        .where(LessonRevision.lesson_id == lesson.id)
        .order_by(LessonRevision.number.desc())
    )
    return [revision_summary(lesson, r) for r in rows]


def revision_detail(lesson: CourseLesson, number: int, actor: User) -> dict[str, Any]:
    require(actor, P.COURSES_VIEW_REVISIONS)
    revision = get_revision(lesson, number)
    snapshot = revision_snapshot(revision)
    return {
        **revision_summary(lesson, revision),
        **snapshot,
        "preview_body": expand_body(snapshot["body"]),
    }


def _version(lesson: CourseLesson, spec: str, actor: User) -> tuple[dict[str, Any], str]:
    if spec == "draft":
        require(actor, P.COURSES_VIEW_DRAFTS)
        return working(lesson), "Draft"
    if spec == "live":
        if lesson.live_revision is None:
            raise NotFoundError("This lesson has never been published.")
        return live_snapshot(lesson), f"Live (revision {lesson.live_revision})"
    try:
        number = int(spec)
    except (TypeError, ValueError):
        raise NotFoundError("Revision not found.") from None
    return revision_snapshot(get_revision(lesson, number)), f"Revision {number}"


def _signature(block: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in block.items() if k != "uid"}, sort_keys=True)


def _label(block: dict[str, Any]) -> str:
    return content.block_text(block) or block.get("type", "").replace("_", " ").capitalize()


def compare(lesson: CourseLesson, left: str, right: str, actor: User) -> dict[str, Any]:
    """Field changes and a block-by-block comparison of two versions."""
    require(actor, P.COURSES_VIEW_REVISIONS)
    before, before_label = _version(lesson, left, actor)
    after, after_label = _version(lesson, right, actor)
    fields = [
        {"field": field, "before": before[field], "after": after[field]}
        for field in DRAFT_FIELDS
        if field != "body" and before[field] != after[field]
    ]
    old, new = before["body"], after["body"]
    keys = lambda blocks: [b.get("uid") or _signature(b) for b in blocks]  # noqa: E731
    matcher = difflib.SequenceMatcher(None, keys(old), keys(new), autojunk=False)
    blocks: list[dict[str, Any]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for a, b in zip(old[i1:i2], new[j1:j2], strict=True):
                status = "unchanged" if _signature(a) == _signature(b) else "changed"
                blocks.append(
                    {
                        "status": status,
                        "type": b.get("type"),
                        "before": _label(a),
                        "after": _label(b),
                    }
                )
            continue
        for a in old[i1:i2]:
            blocks.append({"status": "removed", "type": a.get("type"), "before": _label(a)})
        for b in new[j1:j2]:
            blocks.append({"status": "added", "type": b.get("type"), "after": _label(b)})
    counts = {
        s: sum(1 for b in blocks if b["status"] == s) for s in ("added", "removed", "changed")
    }
    return {
        "left": {"spec": left, "label": before_label},
        "right": {"spec": right, "label": after_label},
        "fields": fields,
        "blocks": blocks,
        "counts": counts,
        "identical": not fields and not any(counts.values()),
    }
