"""CMS pages and structured sections (configuration only in Batch 02)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...cms.sections import SECTION_TYPES, validate_section
from ...extensions import db
from ...models import Page, PageSection, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE
from .. import audit_service
from ..serializers import iso

# Pages whose public rendering already reads section data. None yet: the public
# homepage still renders its approved design from code (page builder: Batch 04).
RENDERED_PAGES: frozenset[str] = frozenset()


def section_dict(s: PageSection) -> dict[str, Any]:
    return {
        "id": s.id,
        "key": s.key,
        "section_type": s.section_type,
        "type_label": SECTION_TYPES.get(s.section_type, {}).get("label", s.section_type),
        "variant": s.variant,
        "content": s.content,
        "is_visible": s.is_visible,
        "display_order": s.display_order,
        "updated_at": iso(s.updated_at),
    }


def page_dict(p: Page, *, with_sections: bool = False) -> dict[str, Any]:
    data = {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "status": p.status,
        "seo_title": p.seo_title,
        "meta_description": p.meta_description,
        "noindex": p.noindex,
        "section_count": len(p.sections),
        "rendered_publicly": p.slug in RENDERED_PAGES,
        "updated_at": iso(p.updated_at),
    }
    if with_sections:
        data["sections"] = [section_dict(s) for s in p.sections]
    return data


def section_types() -> list[dict[str, Any]]:
    return [
        {
            "type": key,
            "label": spec["label"],
            "variants": spec["variants"],
            "fields": [{"name": n, **f} for n, f in spec["fields"].items()],
        }
        for key, spec in SECTION_TYPES.items()
    ]


def list_pages() -> list[dict[str, Any]]:
    return [page_dict(p) for p in db.session.scalars(select(Page).order_by(Page.title))]


def get_page(page_id: int) -> Page:
    page = db.session.get(Page, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    return page


PAGE_FIELDS = ("title", "status", "seo_title", "meta_description", "noindex")


def update_page(page: Page, data: dict[str, Any], actor: User) -> Page:
    before = {f: getattr(page, f) for f in PAGE_FIELDS}
    for f in PAGE_FIELDS:
        if f in data:
            setattr(page, f, data[f])
    changes = audit_service.changed_fields(before, {f: getattr(page, f) for f in PAGE_FIELDS})
    if changes:
        audit_service.record("page.updated", "page", page.id, actor=actor, details=changes)
    return page


def get_section(page: Page, section_id: int) -> PageSection:
    section = db.session.get(PageSection, section_id)
    if section is None or section.page_id != page.id:
        raise NotFoundError("Section not found.")
    return section


def update_section(section: PageSection, data: dict[str, Any], actor: User) -> PageSection:
    variant = data.get("variant", section.variant)
    content = data.get("content", section.content)
    section.content = validate_section(section.section_type, variant, content)
    section.variant = variant
    if "is_visible" in data:
        section.is_visible = data["is_visible"]
    audit_service.record(
        "page_section.updated",
        "page_section",
        section.id,
        actor=actor,
        details={"page_id": section.page_id, "key": section.key, "fields": sorted(data)},
    )
    return section


def create_section(page: Page, data: dict[str, Any], actor: User) -> PageSection:
    key = data["key"]
    if not SLUG_RE.match(key):
        raise ValidationError(details={"key": ["Use lowercase letters, numbers and hyphens."]})
    if any(s.key == key for s in page.sections):
        raise ConflictError(details={"key": ["Already used on this page."]})
    variant = (
        data.get("variant")
        or SECTION_TYPES.get(data["section_type"], {}).get("variants", ["default"])[0]
    )
    content = validate_section(data["section_type"], variant, data.get("content") or {})
    section = PageSection(
        key=key,
        section_type=data["section_type"],
        variant=variant,
        content=content,
        is_visible=data.get("is_visible", True),
        display_order=max([s.display_order for s in page.sections], default=-1) + 1,
    )
    page.sections.append(section)
    db.session.flush()
    audit_service.record(
        "page_section.created",
        "page_section",
        section.id,
        actor=actor,
        details={"page_id": page.id, "key": key},
    )
    return section


def reorder_sections(page: Page, ordered_ids: list[int], actor: User) -> Page:
    current = {s.id: s for s in page.sections}
    if sorted(ordered_ids) != sorted(current):
        raise ValidationError(details={"order": ["Provide every section id exactly once."]})
    for index, sid in enumerate(ordered_ids):
        current[sid].display_order = index
    audit_service.record(
        "page.sections_reordered", "page", page.id, actor=actor, details={"order": ordered_ids}
    )
    db.session.flush()
    db.session.refresh(page)
    return page
