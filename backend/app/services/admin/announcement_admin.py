"""Site announcements: a slim, accessible banner above the header (never a popup).

Announcements can be scheduled. The public build includes enabled announcements
that have not ended; the scheduler queues a rebuild when one starts or ends, and
the browser hides any that expire between builds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import Announcement, User
from ...models.cms import ANNOUNCEMENT_TARGETS, ANNOUNCEMENT_VARIANTS
from ...utils.errors import NotFoundError, ValidationError
from ...utils.validation import is_https_url, is_internal_path, plain_text_problem
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso

MAX_PATHS = 20
EDITABLE = (
    "name",
    "message",
    "cta_label",
    "cta_url",
    "variant",
    "target",
    "target_paths",
    "starts_at",
    "ends_at",
    "is_enabled",
    "is_dismissible",
)


def _now() -> datetime:
    return datetime.now(UTC)


def state(a: Announcement, now: datetime | None = None) -> str:
    now = now or _now()
    if not a.is_enabled:
        return "disabled"
    if a.ends_at and a.ends_at <= now:
        return "ended"
    if a.starts_at and a.starts_at > now:
        return "scheduled"
    return "active"


def announcement_dict(a: Announcement) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "message": a.message,
        "cta_label": a.cta_label,
        "cta_url": a.cta_url,
        "variant": a.variant,
        "target": a.target,
        "target_paths": a.target_paths or [],
        "starts_at": iso(a.starts_at),
        "ends_at": iso(a.ends_at),
        "is_enabled": a.is_enabled,
        "is_dismissible": a.is_dismissible,
        "display_order": a.display_order,
        "state": state(a),
        "updated_at": iso(a.updated_at),
    }


def list_announcements() -> list[dict[str, Any]]:
    stmt = select(Announcement).order_by(Announcement.display_order, Announcement.id)
    return [announcement_dict(a) for a in db.session.scalars(stmt)]


def get_announcement(announcement_id: int) -> Announcement:
    a = db.session.get(Announcement, announcement_id)
    if a is None:
        raise NotFoundError("Announcement not found.")
    return a


def _text(data, field, limit, errors, required=False):
    value = data.get(field)
    value = " ".join(str(value or "").split())
    if required and not value:
        errors[field] = ["This field is required."]
    elif len(value) > limit:
        errors[field] = [f"Must be at most {limit} characters."]
    elif value and plain_text_problem(value):
        errors[field] = ["Use plain text."]
    return value


def _dt(data, field, errors):
    value = data.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            errors[field] = ["Use a valid date and time."]
            return None
    if parsed.tzinfo is None:
        errors[field] = ["Include a time zone."]
        return None
    return parsed


def _clean(data: dict[str, Any], existing: Announcement | None) -> dict[str, Any]:
    merged = {f: getattr(existing, f) for f in EDITABLE} if existing else {}
    merged.update({k: v for k, v in data.items() if k in EDITABLE})
    errors: dict[str, list[str]] = {}
    out = {
        "name": _text(merged, "name", 120, errors, required=True),
        "message": _text(merged, "message", 240, errors, required=True),
        "cta_label": _text(merged, "cta_label", 60, errors) or None,
    }
    url = (merged.get("cta_url") or "").strip() or None
    if url and not (is_internal_path(url) or is_https_url(url)):
        errors["cta_url"] = ["Use a site path starting with / or a full https:// link."]
    if bool(url) != bool(out["cta_label"]):
        errors["cta_label" if not out["cta_label"] else "cta_url"] = [
            "A link needs both text and an address."
        ]
    out["cta_url"] = url
    variant = merged.get("variant") or "sage"
    if variant not in ANNOUNCEMENT_VARIANTS:
        errors["variant"] = [f"Use one of: {', '.join(ANNOUNCEMENT_VARIANTS)}."]
    target = merged.get("target") or "all"
    if target not in ANNOUNCEMENT_TARGETS:
        errors["target"] = [f"Use one of: {', '.join(ANNOUNCEMENT_TARGETS)}."]
    paths = merged.get("target_paths") or []
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        errors["target_paths"] = ["Must be a list of site paths."]
        paths = []
    paths = list(dict.fromkeys(p.strip() for p in paths if p.strip()))
    if any(not is_internal_path(p) for p in paths):
        errors["target_paths"] = ["Use site paths starting with /."]
    if len(paths) > MAX_PATHS:
        errors["target_paths"] = [f"At most {MAX_PATHS} paths."]
    if target == "paths" and not paths:
        errors["target_paths"] = ["Add at least one page address."]
    starts, ends = _dt(merged, "starts_at", errors), _dt(merged, "ends_at", errors)
    if starts and ends and ends <= starts:
        errors["ends_at"] = ["The end must be after the start."]
    for flag in ("is_enabled", "is_dismissible"):
        if flag in merged and not isinstance(merged[flag], bool):
            errors[flag] = ["Must be true or false."]
    if errors:
        raise ValidationError("The announcement is invalid.", details=errors)
    out.update(
        variant=variant,
        target=target,
        target_paths=paths if target == "paths" else [],
        starts_at=starts,
        ends_at=ends,
        is_enabled=bool(merged.get("is_enabled", False)),
        is_dismissible=bool(merged.get("is_dismissible", True)),
    )
    return out


def _affects_public(before: bool, after: Announcement) -> bool:
    return before or (after.is_enabled and state(after) != "ended")


def create_announcement(data: dict[str, Any], actor: User) -> Announcement:
    clean = _clean(data, None)
    order = (db.session.scalar(select(func.max(Announcement.display_order))) or 0) + 1
    a = Announcement(**clean, display_order=order, updated_by_id=actor.id)
    db.session.add(a)
    db.session.flush()
    audit_service.record(
        "announcement.created", "announcement", a.id, actor=actor, details={"name": a.name}
    )
    if _affects_public(False, a):
        record_public_change("announcement", a.id, "announcement_created", actor)
    return a


def update_announcement(a: Announcement, data: dict[str, Any], actor: User) -> Announcement:
    was_public = a.is_enabled and state(a) != "ended"
    clean = _clean(data, a)
    before = {k: getattr(a, k) for k in clean}
    for field, value in clean.items():
        setattr(a, field, value)
    changes = audit_service.changed_fields(before, clean)
    if changes:
        a.revision += 1
        a.updated_by_id = actor.id
        audit_service.record(
            "announcement.updated", "announcement", a.id, actor=actor, details=changes
        )
        if _affects_public(was_public, a):
            record_public_change("announcement", a.id, "announcement_updated", actor)
    return a


def delete_announcement(a: Announcement, actor: User) -> None:
    was_public = a.is_enabled and state(a) != "ended"
    audit_service.record(
        "announcement.deleted", "announcement", a.id, actor=actor, details={"name": a.name}
    )
    db.session.delete(a)
    if was_public:
        record_public_change("announcement", a.id, "announcement_deleted", actor)


def reorder(ids: list[int], actor: User) -> None:
    current = {a.id: a for a in db.session.scalars(select(Announcement))}
    if sorted(ids) != sorted(current):
        raise ValidationError(details={"order": ["Provide every announcement id exactly once."]})
    for index, aid in enumerate(ids):
        current[aid].display_order = index
    audit_service.record("announcement.reordered", "announcement", actor=actor)
    if any(a.is_enabled and state(a) != "ended" for a in current.values()):
        record_public_change("announcement", None, "announcements_reordered", actor)


def public_announcements(now: datetime | None = None) -> list[dict[str, Any]]:
    """Enabled announcements that have not ended (the browser re-checks the dates)."""
    now = now or _now()
    out = []
    stmt = select(Announcement).where(Announcement.is_enabled.is_(True))
    for a in db.session.scalars(stmt.order_by(Announcement.display_order, Announcement.id)):
        if a.ends_at and a.ends_at <= now:
            continue
        out.append(
            {
                "id": f"{a.id}-{a.revision}",
                "message": a.message,
                "cta": {"label": a.cta_label, "href": a.cta_url} if a.cta_url else None,
                "variant": a.variant,
                "dismissible": a.is_dismissible,
                "target": a.target,
                "paths": a.target_paths or [],
                "starts_at": iso(a.starts_at),
                "ends_at": iso(a.ends_at),
            }
        )
    return out


def boundaries() -> list[datetime]:
    out = []
    for a in db.session.scalars(select(Announcement).where(Announcement.is_enabled.is_(True))):
        out += [t for t in (a.starts_at, a.ends_at) if t]
    return out
