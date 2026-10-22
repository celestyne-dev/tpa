"""Shared (reusable) sections and global calls to action.

A page section can *link* to a shared section instead of holding its own
content. Editing the shared section then updates every linked page. When an
editor saves with ``propagate=False``, linked pages are detached first: they
keep an inline copy of the previous version (draft and live), and only new
uses get the change.

Section groups list other shared sections. Groups may not include themselves,
directly or through other groups, and nesting is limited.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import func, select

from ...cms.design import DESIGN_OPTIONS
from ...cms.sections import SECTION_TYPES, check_section
from ...extensions import db
from ...models import GlobalCta, Page, PageSection, ReusableSection, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import is_https_url, is_internal_path, plain_text_problem
from .. import audit_service
from ..page_render import MAX_GROUP_DEPTH
from ..publication_service import record_public_change
from ..serializers import iso
from .article_admin import EditConflict
from .page_admin import _ref_errors, _user_ref

BUTTON_STYLES = tuple(DESIGN_OPTIONS["button_style"]["choices"])


# ---- usage ----------------------------------------------------------------------------------


def _walk(value: Any, key: str) -> set[int]:
    found: set[int] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key and isinstance(v, int):
                found.add(v)
            else:
                found |= _walk(v, key)
    elif isinstance(value, list):
        for item in value:
            found |= _walk(item, key)
    return found


def _groups_including(shared_id: int) -> list[ReusableSection]:
    return [
        g
        for g in db.session.scalars(
            select(ReusableSection).where(ReusableSection.section_type == "section_group")
        )
        if shared_id in ((g.content or {}).get("items") or [])
    ]


def reusable_usage(shared: ReusableSection) -> list[dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    for section in db.session.scalars(
        select(PageSection).where(PageSection.reusable_section_id == shared.id)
    ):
        page = section.page
        pages.setdefault(
            page.id,
            {"type": "page", "id": page.id, "title": page.title, "path": page.path, "live": False},
        )
    for page in db.session.scalars(select(Page).where(Page.status == "published")):
        snapshot = page.published_snapshot or {}
        if any(s.get("reusable_section_id") == shared.id for s in snapshot.get("sections", [])):
            entry = pages.setdefault(
                page.id,
                {"type": "page", "id": page.id, "title": page.title, "path": page.path},
            )
            entry["live"] = True
    usage = list(pages.values())
    usage += [
        {"type": "group", "id": g.id, "title": g.name, "path": None, "live": None}
        for g in _groups_including(shared.id)
    ]
    return usage


def reusable_dict(r: ReusableSection, *, with_usage: bool = True) -> dict[str, Any]:
    data = {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "section_type": r.section_type,
        "type_label": SECTION_TYPES.get(r.section_type, {}).get("label", r.section_type),
        "variant": r.variant,
        "content": r.content,
        "design": r.design or {},
        "lock_version": r.lock_version,
        "updated_at": iso(r.updated_at),
        "updated_by": _user_ref(r.updated_by),
    }
    if with_usage:
        usage = reusable_usage(r)
        data["usage"] = usage
        data["live_pages"] = sum(1 for u in usage if u.get("live"))
    return data


def list_reusable() -> list[dict[str, Any]]:
    return [
        reusable_dict(r)
        for r in db.session.scalars(select(ReusableSection).order_by(ReusableSection.name))
    ]


def get_reusable(shared_id: int) -> ReusableSection:
    shared = db.session.get(ReusableSection, shared_id)
    if shared is None:
        raise NotFoundError("Shared section not found.")
    return shared


# ---- validation -----------------------------------------------------------------------------


def _cycle_problem(shared_id: int | None, items: list[int]) -> str | None:
    graph = {
        g.id: list((g.content or {}).get("items") or [])
        for g in db.session.scalars(
            select(ReusableSection).where(ReusableSection.section_type == "section_group")
        )
    }
    if shared_id is not None:
        graph[shared_id] = items
        if shared_id in items:
            return "A group cannot include itself."

    def depth(node: int, path: tuple[int, ...]) -> int:
        if node in path:
            raise RecursionError
        children = graph.get(node, [])
        return 1 + max((depth(c, (*path, node)) for c in children), default=0)

    try:
        levels = max((depth(i, (shared_id,) if shared_id else ()) for i in items), default=0)
    except RecursionError:
        return "This would create a loop: a group cannot include a group that includes it."
    if levels > MAX_GROUP_DEPTH - 1:
        return f"Groups can be nested at most {MAX_GROUP_DEPTH} levels deep."
    return None


def _clean(data: dict[str, Any], existing: ReusableSection | None) -> dict[str, Any]:
    errors: dict[str, Any] = {}
    out: dict[str, Any] = {}
    name = " ".join((data.get("name", existing.name if existing else "") or "").split())
    if not name or len(name) > 120 or plain_text_problem(name):
        errors["name"] = ["Use a plain-text name of up to 120 characters."]
    else:
        clash = db.session.scalar(
            select(ReusableSection.id).where(
                func.lower(ReusableSection.name) == name.lower(),
                ReusableSection.id != (existing.id if existing else -1),
            )
        )
        if clash:
            errors["name"] = ["Another shared section already uses this name."]
    out["name"] = name
    description = data.get("description", existing.description if existing else "") or ""
    if len(description) > 300 or plain_text_problem(description):
        errors["description"] = ["Use plain text of up to 300 characters."]
    out["description"] = description.strip() or None
    section_type = existing.section_type if existing else data.get("section_type")
    if section_type not in SECTION_TYPES or section_type in ("hero", "page_header"):
        errors["section_type"] = ["Choose a section type that can be shared."]
        raise ValidationError("The shared section is invalid.", details=errors)
    clean, problems, refs = check_section(
        section_type,
        data.get("variant", existing.variant if existing else None),
        data.get("content", existing.content if existing else {}),
        data.get("design", existing.design if existing else None),
    )
    for key, msgs in problems.items():
        if key.startswith("visibility"):
            continue
        scoped = key.startswith(("design", "variant"))
        errors[key if scoped else f"content.{key}"] = msgs
    errors.update(_ref_errors(refs, "content"))
    if section_type == "section_group":
        items = clean["content"].get("items") or []
        if problem := _cycle_problem(existing.id if existing else None, items):
            errors["content.items"] = [problem]
    if errors:
        raise ValidationError("The shared section is invalid.", details=errors)
    out.update(
        section_type=section_type,
        variant=clean["variant"],
        content=clean["content"],
        design=clean["design"],
    )
    return out


def create_reusable(data: dict[str, Any], actor: User) -> ReusableSection:
    clean = _clean(data, None)
    shared = ReusableSection(**clean, updated_by_id=actor.id)
    db.session.add(shared)
    db.session.flush()
    audit_service.record(
        "shared_section.created",
        "reusable_section",
        shared.id,
        actor=actor,
        details={"name": shared.name, "type": shared.section_type},
    )
    return shared


def create_from_section(section: PageSection, name: str, actor: User) -> ReusableSection:
    """Turn an existing page section into a shared section and link the page to it."""
    shared = create_reusable(
        {
            "name": name,
            "section_type": section.section_type,
            "variant": section.variant,
            "content": section.content,
            "design": section.design,
        },
        actor,
    )
    section.reusable_section_id = shared.id
    section.content, section.design = {}, {}
    page = section.page
    page.lock_version += 1
    return shared


def _detach_usages(shared: ReusableSection) -> int:
    """Give every linked page an inline copy of the current version."""
    frozen = {
        "section_type": shared.section_type,
        "variant": shared.variant,
        "content": copy.deepcopy(shared.content),
        "design": copy.deepcopy(shared.design or {}),
    }
    count = 0
    for section in db.session.scalars(
        select(PageSection).where(PageSection.reusable_section_id == shared.id)
    ):
        section.reusable_section_id = None
        section.section_type = frozen["section_type"]
        section.variant = frozen["variant"]
        section.content = copy.deepcopy(frozen["content"])
        section.design = copy.deepcopy(frozen["design"])
        section.page.lock_version += 1
        count += 1
    for page in db.session.scalars(select(Page).where(Page.published_snapshot.is_not(None))):
        snapshot = copy.deepcopy(page.published_snapshot)
        changed = False
        for s in snapshot.get("sections", []):
            if s.get("reusable_section_id") == shared.id:
                s.update(copy.deepcopy(frozen), reusable_section_id=None)
                changed = True
        if changed:
            page.published_snapshot = snapshot
            count += 1
    return count


def update_reusable(shared: ReusableSection, data: dict[str, Any], actor: User) -> dict:
    if data.get("lock_version") != shared.lock_version:
        raise EditConflict(
            "This shared section was changed by someone else since you opened it.",
            details={
                "lock_version": shared.lock_version,
                "updated_by": shared.updated_by.display_name if shared.updated_by else None,
            },
        )
    clean = _clean(data, shared)
    propagate = data.get("propagate", True)
    live_before = sum(1 for u in reusable_usage(shared) if u.get("live"))
    detached = 0
    if not propagate:
        detached = _detach_usages(shared)
    for field, value in clean.items():
        setattr(shared, field, value)
    shared.lock_version += 1
    shared.updated_by_id = actor.id
    db.session.flush()
    groups_live = any(
        u.get("live") for g in _groups_including(shared.id) for u in reusable_usage(g)
    )
    if (propagate and live_before) or groups_live:
        record_public_change("reusable_section", shared.id, "shared_section_updated", actor)
    audit_service.record(
        "shared_section.updated",
        "reusable_section",
        shared.id,
        actor=actor,
        details={"propagate": bool(propagate), "detached": detached},
    )
    return {"propagated": bool(propagate), "detached": detached}


def delete_reusable(shared: ReusableSection, actor: User) -> None:
    usage = reusable_usage(shared)
    if usage:
        raise ConflictError(
            "This shared section is still in use. Remove it from these pages first.",
            details={"usage": usage},
        )
    audit_service.record(
        "shared_section.deleted",
        "reusable_section",
        shared.id,
        actor=actor,
        details={"name": shared.name},
    )
    db.session.delete(shared)


# ---- global calls to action ---------------------------------------------------------------


def cta_usage(cta: GlobalCta) -> list[dict[str, Any]]:
    usage = []
    for page in db.session.scalars(select(Page)):
        draft = any(cta.id in _walk(s.content, "cta_id") for s in page.sections)
        live = page.status == "published" and cta.id in _walk(page.published_snapshot, "cta_id")
        if draft or live:
            usage.append(
                {
                    "type": "page",
                    "id": page.id,
                    "title": page.title,
                    "path": page.path,
                    "live": live,
                }
            )
    for shared in db.session.scalars(select(ReusableSection)):
        if cta.id in _walk(shared.content, "cta_id"):
            usage.append(
                {"type": "shared_section", "id": shared.id, "title": shared.name, "live": None}
            )
    return usage


def cta_dict(cta: GlobalCta) -> dict[str, Any]:
    return {
        "id": cta.id,
        "name": cta.name,
        "label": cta.label,
        "url": cta.url,
        "style": cta.style,
        "description": cta.description,
        "updated_at": iso(cta.updated_at),
        "usage": cta_usage(cta),
    }


def list_ctas() -> list[dict[str, Any]]:
    return [cta_dict(c) for c in db.session.scalars(select(GlobalCta).order_by(GlobalCta.name))]


def get_cta(cta_id: int) -> GlobalCta:
    cta = db.session.get(GlobalCta, cta_id)
    if cta is None:
        raise NotFoundError("Call to action not found.")
    return cta


def _clean_cta(data: dict[str, Any], existing: GlobalCta | None) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}

    def text(field: str, limit: int, required: bool = True) -> str:
        value = data.get(field, getattr(existing, field) if existing else "") or ""
        value = " ".join(str(value).split())
        if required and not value:
            errors[field] = ["This field is required."]
        elif len(value) > limit:
            errors[field] = [f"Must be at most {limit} characters."]
        elif value and plain_text_problem(value):
            errors[field] = ["Use plain text."]
        return value

    out = {
        "name": text("name", 120),
        "label": text("label", 60),
        "description": text("description", 300, required=False) or None,
    }
    url = (data.get("url", existing.url if existing else "") or "").strip()
    if not (is_internal_path(url) or is_https_url(url)):
        errors["url"] = ["Use a site path starting with / or a full https:// link."]
    out["url"] = url
    style = data.get("style", existing.style if existing else "primary") or "primary"
    if style not in BUTTON_STYLES:
        errors["style"] = [f"Use one of: {', '.join(BUTTON_STYLES)}."]
    out["style"] = style
    if out["name"] and db.session.scalar(
        select(GlobalCta.id).where(
            func.lower(GlobalCta.name) == out["name"].lower(),
            GlobalCta.id != (existing.id if existing else -1),
        )
    ):
        errors["name"] = ["Another call to action already uses this name."]
    if errors:
        raise ValidationError("The call to action is invalid.", details=errors)
    return out


def create_cta(data: dict[str, Any], actor: User) -> GlobalCta:
    cta = GlobalCta(**_clean_cta(data, None), updated_by_id=actor.id)
    db.session.add(cta)
    db.session.flush()
    audit_service.record(
        "cta.created", "global_cta", cta.id, actor=actor, details={"name": cta.name}
    )
    return cta


def update_cta(cta: GlobalCta, data: dict[str, Any], actor: User) -> GlobalCta:
    clean = _clean_cta(data, cta)
    before = {k: getattr(cta, k) for k in clean}
    for field, value in clean.items():
        setattr(cta, field, value)
    cta.updated_by_id = actor.id
    changes = audit_service.changed_fields(before, clean)
    if changes:
        audit_service.record("cta.updated", "global_cta", cta.id, actor=actor, details=changes)
        live = any(u.get("live") for u in cta_usage(cta)) or any(
            u["type"] == "shared_section" for u in cta_usage(cta)
        )
        if live and ({"label", "url", "style"} & set(changes)):
            record_public_change("global_cta", cta.id, "cta_updated", actor)
    return cta


def delete_cta(cta: GlobalCta, actor: User) -> None:
    usage = cta_usage(cta)
    if usage:
        raise ConflictError(
            "This call to action is still used. Replace it in these sections first.",
            details={"usage": usage},
        )
    audit_service.record(
        "cta.deleted", "global_cta", cta.id, actor=actor, details={"name": cta.name}
    )
    db.session.delete(cta)
