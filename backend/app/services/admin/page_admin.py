"""CMS pages and the homepage builder: drafts, publishing, revisions and templates.

Draft vs published
------------------
The ``page_sections`` rows and the page's own columns are the working draft.
Saving a draft never changes the website. Publish validates the draft and
stores it as ``Page.published_snapshot``; only snapshots are public. Every
publish is kept as a revision, so earlier versions can be restored (into the
draft, then published again).

Conflicts: every draft write bumps ``lock_version``; clients send the version
they loaded and get 409 ``edit_conflict`` instead of overwriting newer work.

The homepage is the system page with slug ``home`` (path ``/``). It uses the
homepage.* permissions; every other page uses pages.*.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms import routing
from ...cms.sections import SECTION_TYPES, SINGLE_USE, check_section, section_types_schema
from ...cms.templates import PAGE_TEMPLATES
from ...extensions import db
from ...models import (
    AffiliateLink,
    Article,
    Author,
    GlobalCta,
    Page,
    PageRevision,
    PageSection,
    Product,
    ProductCollection,
    Redirect,
    ReusableSection,
    Topic,
    User,
)
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE, is_https_url, plain_text_problem, slugify
from .. import audit_service, page_render
from ..publication_service import record_public_change
from ..serializers import iso
from .article_admin import EditConflict

HOME_SLUG = "home"
MAX_SECTIONS = 40
MAX_REVISIONS = 50
SCHEDULE_GRACE = timedelta(minutes=1)

PERMISSIONS = {
    "home": {
        "view": P.HOMEPAGE_VIEW,
        "edit": P.HOMEPAGE_EDIT,
        "publish": P.HOMEPAGE_PUBLISH,
    },
    "page": {
        "view": P.PAGES_VIEW,
        "edit": P.PAGES_EDIT,
        "publish": P.PAGES_PUBLISH,
        "create": P.PAGES_CREATE,
    },
}


def _now() -> datetime:
    return datetime.now(UTC)


def is_home(page: Page) -> bool:
    return page.slug == HOME_SLUG


# ---- permissions ---------------------------------------------------------------------------


def capabilities(page: Page, user: User) -> dict[str, bool]:
    perms = effective_permissions(user)
    rules = PERMISSIONS["home" if is_home(page) else "page"]
    can = {action: perm.value in perms for action, perm in rules.items()}
    archived = page.status == "archived"
    return {
        "view": can["view"],
        "edit": can["edit"] and not archived,
        "publish": can["publish"] and not archived,
        "unpublish": can["publish"] and page.status == "published" and not is_home(page),
        "archive": can["publish"] and not is_home(page) and not archived,
        "restore": can["publish"] and archived,
        "duplicate": P.PAGES_CREATE.value in perms and not is_home(page),
        "change_slug": can["edit"] and not is_home(page) and not archived,
        "restore_revisions": can["edit"] and not archived,
        "manage_shared": P.REUSABLE_SECTIONS_MANAGE.value in perms,
    }


def require(page: Page, user: User, action: str) -> None:
    if not capabilities(page, user).get(action):
        raise ForbiddenError("You do not have permission to do this on this page.")


def can_view_pages(user: User) -> bool:
    return P.PAGES_VIEW.value in effective_permissions(user)


# ---- serialisation -------------------------------------------------------------------------


def section_dict(s: PageSection) -> dict[str, Any]:
    shared = s.reusable
    return {
        "id": s.id,
        "key": s.key,
        "name": s.name or "",
        "section_type": shared.section_type if shared else s.section_type,
        "type_label": SECTION_TYPES.get(shared.section_type if shared else s.section_type, {}).get(
            "label", s.section_type
        ),
        "variant": shared.variant if shared else s.variant,
        "content": shared.content if shared else s.content,
        "design": shared.design if shared else (s.design or {}),
        "visibility": s.visibility or {},
        "is_visible": s.is_visible,
        "display_order": s.display_order,
        "reusable_section_id": s.reusable_section_id,
        "reusable_name": shared.name if shared else None,
        "updated_at": iso(s.updated_at),
    }


def _user_ref(user: User | None) -> dict[str, Any] | None:
    return {"id": user.id, "name": user.display_name} if user else None


def page_summary(p: Page) -> dict[str, Any]:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "path": p.path,
        "live_path": p.published_path if p.status == "published" else None,
        "status": p.status,
        "template": p.template,
        "template_label": PAGE_TEMPLATES.get(p.template, {}).get(
            "label", "Homepage" if is_home(p) else p.template
        ),
        "is_system": p.is_system,
        "is_home": is_home(p),
        "parent_id": p.parent_id,
        "noindex": p.noindex,
        "seo_title": p.seo_title,
        "meta_description": p.meta_description,
        "section_count": len(p.sections),
        "has_unpublished_changes": page_render.has_unpublished_changes(p),
        "published_at": iso(p.published_at),
        "scheduled_at": iso(p.scheduled_at),
        "draft_updated_at": iso(p.draft_updated_at),
        "updated_at": iso(p.updated_at),
        "updated_by": _user_ref(p.updated_by),
        "rendered_publicly": p.status == "published" or is_home(p),
        "overrides_builtin": p.path in routing.OVERRIDABLE_PATHS,
    }


# Batch 02 name kept for existing callers.
def page_dict(p: Page, *, with_sections: bool = False) -> dict[str, Any]:
    data = page_summary(p)
    if with_sections:
        data["sections"] = [section_dict(s) for s in p.sections]
    return data


def warnings_for(page: Page) -> list[str]:
    out = []
    if page.path in routing.OVERRIDABLE_PATHS and page.status != "published":
        out.append(f"Publishing this page replaces the built-in {page.path} page on the website.")
    if page.path and page.status != "archived":
        redirect = db.session.scalar(select(Redirect).where(Redirect.source_path == page.path))
        if redirect and page.published_path != page.path:
            out.append(
                f"A redirect from {page.path} exists. "
                "It will be removed when this page is published."
            )
    if page.status == "published" and page.published_path and page.path != page.published_path:
        out.append(
            f"The address changes from {page.published_path} to {page.path} when you publish; "
            "a permanent redirect will be created automatically."
        )
    if page.parent_id and page.parent and page.parent.status != "published":
        out.append("The parent page is not published, so breadcrumbs will skip it.")
    return out


def page_detail(page: Page, user: User) -> dict[str, Any]:
    data = page_summary(page)
    snapshot_page = (page.published_snapshot or {}).get("page") or {}
    data.update(
        lock_version=page.lock_version,
        canonical_url=page.canonical_url,
        social_title=page.social_title,
        social_description=page.social_description,
        social_image_id=page.social_image_id,
        parent=page_summary(page.parent) if page.parent else None,
        first_published_at=iso(page.first_published_at),
        published_by=_user_ref(page.published_by),
        live_title=snapshot_page.get("title") if page.status == "published" else None,
        sections=[section_dict(s) for s in page.sections],
        capabilities=capabilities(page, user),
        warnings=warnings_for(page),
        revision_count=db.session.scalar(
            select(func.count(PageRevision.id)).where(PageRevision.page_id == page.id)
        ),
    )
    return data


# ---- queries -------------------------------------------------------------------------------


def list_pages(args: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    args = args or {}
    stmt = select(Page).order_by(Page.is_system.desc(), Page.path, Page.title)
    if args.get("status"):
        stmt = stmt.where(Page.status == args["status"])
    else:
        stmt = stmt.where(Page.status != "archived")
    if args.get("q"):
        term = f"%{args['q'].strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Page.title).like(term), Page.path.like(term)))
    if args.get("exclude_home"):
        stmt = stmt.where(Page.slug != HOME_SLUG)
    return [page_summary(p) for p in db.session.scalars(stmt)]


def get_page(page_id: int) -> Page:
    page = db.session.get(Page, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    return page


def section_types() -> list[dict[str, Any]]:
    return section_types_schema()


def templates() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "label": t["label"],
            "description": t["description"],
            "sections": [SECTION_TYPES[s["section_type"]]["label"] for s in t["sections"]],
        }
        for key, t in PAGE_TEMPLATES.items()
    ]


# ---- paths and slugs ------------------------------------------------------------------------


def _ancestors(parent: Page | None) -> list[Page]:
    chain, seen = [], set()
    while parent is not None:
        if parent.id in seen:
            break
        seen.add(parent.id)
        chain.append(parent)
        parent = parent.parent
    return list(reversed(chain))


def _compute_path(slug: str, parent: Page | None) -> str:
    return routing.page_path([p.slug for p in _ancestors(parent)] + [slug])


def _descendants(page: Page) -> list[Page]:
    out, frontier = [], [page.id]
    while frontier:
        children = db.session.scalars(select(Page).where(Page.parent_id.in_(frontier))).all()
        children = [c for c in children if c.id not in {o.id for o in out} and c.id != page.id]
        out += children
        frontier = [c.id for c in children]
    return out


def path_problems(
    slug: str, parent_id: int | None, *, page: Page | None = None
) -> tuple[str | None, dict[str, list[str]]]:
    """Return (path, errors) for a slug under a parent, checking every routing rule."""
    errors: dict[str, list[str]] = {}
    parent = db.session.get(Page, parent_id) if parent_id else None
    if parent_id and parent is None:
        errors["parent_id"] = ["That parent page no longer exists."]
    if parent is not None:
        if is_home(parent):
            errors["parent_id"] = ["Pages cannot be placed under the homepage."]
        elif parent.status == "archived":
            errors["parent_id"] = ["Choose a parent page that is not archived."]
        elif page is not None and (
            parent.id == page.id or parent.id in {d.id for d in _descendants(page)}
        ):
            errors["parent_id"] = ["A page cannot be placed under itself or its own sub-pages."]
        elif len(_ancestors(parent)) >= routing.MAX_DEPTH:
            errors["parent_id"] = [f"Pages can be nested at most {routing.MAX_DEPTH} levels deep."]
    if problem := routing.slug_problem(slug, top_level=parent is None):
        errors["slug"] = [problem]
    if errors:
        return None, errors
    path = _compute_path(slug, parent)
    exclude = page.id if page else -1
    taken_slug = db.session.scalar(select(Page.id).where(Page.slug == slug, Page.id != exclude))
    if taken_slug:
        errors["slug"] = ["Another page already uses this slug."]
    clash = db.session.scalar(
        select(Page).where(or_(Page.path == path, Page.published_path == path), Page.id != exclude)
    )
    if clash is not None:
        errors["slug"] = [f"{path} is already used by the page “{clash.title}”."]
    return path, errors


def slug_check(slug: str, parent_id: int | None, exclude_id: int | None) -> dict[str, Any]:
    page = db.session.get(Page, exclude_id) if exclude_id else None
    path, errors = path_problems(slug, parent_id, page=page)
    return {
        "slug": slug,
        "path": path,
        "available": not errors,
        "errors": errors,
        "overrides_builtin": path in routing.OVERRIDABLE_PATHS if path else False,
    }


# ---- validation ----------------------------------------------------------------------------


def _ref_errors(refs, prefix: str) -> dict[str, list[str]]:
    from .media_admin import media_ref_problems

    errors: dict[str, list[str]] = {}
    media = {f"{prefix}.{path}": value for kind, value, path in refs.items if kind == "media"}
    for key, problem in media_ref_problems(media).items():
        errors.setdefault(key, []).append(problem)
    checks = {
        "article": (Article, "This article no longer exists."),
        "topic": (Topic, "This topic no longer exists."),
        "author": (Author, "This author no longer exists."),
        "cta": (GlobalCta, "This saved call to action no longer exists."),
        "reusable": (ReusableSection, "This shared section no longer exists."),
        "product": (Product, "This product no longer exists."),
        "product_collection": (ProductCollection, "This collection no longer exists."),
        "affiliate_link": (AffiliateLink, "This affiliate link no longer exists."),
    }
    for kind, (model, message) in checks.items():
        wanted = refs.ids(kind)
        if not wanted:
            continue
        found = set(db.session.scalars(select(model.id).where(model.id.in_(wanted))))
        for k, value, path in refs.items:
            if k == kind and value not in found:
                errors.setdefault(f"{prefix}.{path}", []).append(message)
    return errors


def _clean_meta(page: Page, data: dict[str, Any], errors: dict[str, list[str]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    limits = {
        "title": 200,
        "seo_title": 200,
        "meta_description": 320,
        "social_title": 200,
        "social_description": 320,
    }
    for field, limit in limits.items():
        if field not in data:
            continue
        value = data[field]
        if value is None:
            value = ""
        if not isinstance(value, str):
            errors[f"page.{field}"] = ["Must be text."]
            continue
        value = " ".join(value.split())
        if field == "title" and not value:
            errors["page.title"] = ["A title is required."]
        elif len(value) > limit:
            errors[f"page.{field}"] = [f"Must be at most {limit} characters."]
        elif value and (problem := plain_text_problem(value)):
            errors[f"page.{field}"] = [problem]
        out[field] = value or (None if field != "title" else value)
    if "noindex" in data:
        if not isinstance(data["noindex"], bool):
            errors["page.noindex"] = ["Must be true or false."]
        else:
            out["noindex"] = data["noindex"]
    if "canonical_url" in data:
        value = (data["canonical_url"] or "").strip()
        if value and not is_https_url(value):
            errors["page.canonical_url"] = ["Use a full https:// address, or leave empty."]
        out["canonical_url"] = value or None
    if "social_image_id" in data:
        value = data["social_image_id"]
        if value not in (None, "") and (not isinstance(value, int) or isinstance(value, bool)):
            errors["page.social_image_id"] = ["Choose an image from the media library."]
        else:
            from .media_admin import media_ref_problems

            if value:
                for _, problem in media_ref_problems({"x": value}).items():
                    errors["page.social_image_id"] = [problem]
            out["social_image_id"] = value or None
    slug_given = "slug" in data or "parent_id" in data
    if slug_given and not is_home(page):
        slug = data.get("slug", page.slug)
        parent_id = data.get("parent_id", page.parent_id)
        if not isinstance(slug, str) or (
            parent_id is not None
            and (not isinstance(parent_id, int) or isinstance(parent_id, bool))
        ):
            errors["page.slug"] = ["Invalid address."]
        else:
            path, problems = path_problems(slug.strip(), parent_id, page=page)
            for key, msgs in problems.items():
                errors[f"page.{key}"] = msgs
            out.update(slug=slug.strip(), parent_id=parent_id, path=path)
    elif slug_given and (
        data.get("slug", page.slug) != page.slug or data.get("parent_id") is not None
    ):
        errors["page.slug"] = ["The homepage address cannot be changed."]
    return out


def _clean_sections(
    current: list[PageSection], items: Any, errors: dict[str, list[str]]
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        errors["sections"] = ["Sections must be a list."]
        return []
    if len(items) > MAX_SECTIONS:
        errors["sections"] = [f"A page can have at most {MAX_SECTIONS} sections."]
    existing = {s.id: s for s in current}
    shared = {
        r.id: r
        for r in db.session.scalars(
            select(ReusableSection).where(
                ReusableSection.id.in_(
                    [i.get("reusable_section_id") for i in items if isinstance(i, dict)] or [0]
                )
            )
        )
    }
    clean: list[dict[str, Any]] = []
    used_types: dict[str, int] = {}
    keys: set[str] = set()
    for index, item in enumerate(items):
        prefix = f"sections.{index}"
        if not isinstance(item, dict):
            errors[prefix] = ["Each section must be an object."]
            continue
        sid = item.get("id")
        if sid is not None and sid not in existing:
            errors[prefix] = ["This section belongs to another page or was deleted."]
            continue
        name = item.get("name") or ""
        if not isinstance(name, str) or len(name) > 120 or plain_text_problem(name or "x"):
            errors[f"{prefix}.name"] = ["Use a plain-text name of up to 120 characters."]
            name = ""
        is_visible = item.get("is_visible", True)
        if not isinstance(is_visible, bool):
            errors[f"{prefix}.is_visible"] = ["Must be true or false."]
            is_visible = True
        shared_id = item.get("reusable_section_id")
        if shared_id:
            target = shared.get(shared_id)
            if target is None:
                errors[f"{prefix}.reusable_section_id"] = ["This shared section no longer exists."]
                continue
            section_type = target.section_type
            from ...cms.design import validate_visibility

            visibility, vis_errors = validate_visibility(item.get("visibility"))
            for key, msgs in vis_errors.items():
                errors[f"{prefix}.{key}"] = msgs
            entry = {
                "section_type": section_type,
                "variant": target.variant,
                "content": {},
                "design": {},
                "visibility": visibility,
                "reusable_section_id": shared_id,
            }
        else:
            section_type = item.get("section_type")
            if section_type not in SECTION_TYPES or SECTION_TYPES[section_type].get(
                "reusable_only"
            ):
                errors[f"{prefix}.section_type"] = ["Unknown section type."]
                continue
            cleaned, problems, refs = check_section(
                section_type,
                item.get("variant"),
                item.get("content"),
                item.get("design"),
                item.get("visibility"),
            )
            for key, msgs in problems.items():
                scoped = key == "content" or key.startswith(
                    ("design", "visibility", "variant", "section_type")
                )
                errors[f"{prefix}.{key}" if scoped else f"{prefix}.content.{key}"] = msgs
            for key, msgs in _ref_errors(refs, f"{prefix}.content").items():
                errors.setdefault(key, []).extend(msgs)
            entry = {**cleaned, "section_type": section_type, "reusable_section_id": None}
        if section_type in SINGLE_USE and is_visible:
            used_types[section_type] = used_types.get(section_type, 0) + 1
            if used_types[section_type] > 1:
                errors[f"{prefix}.section_type"] = [
                    f"Only one visible {SECTION_TYPES[section_type]['label'].lower()} per page."
                ]
        key = existing[sid].key if sid else None
        if key is None:
            base = (item.get("key") or section_type).replace("_", "-")
            base = base if SLUG_RE.match(base) else slugify(base) or "section"
            key, n = base, 2
            taken = {s.key for s in current} | keys
            while key in taken:
                key, n = f"{base}-{n}", n + 1
        keys.add(key)
        clean.append({**entry, "id": sid, "key": key, "name": name, "is_visible": is_visible})
    return clean


def _check_lock(page: Page, lock_version: Any) -> None:
    if lock_version is None:
        raise ValidationError(details={"lock_version": ["Reload the page and try again."]})
    if lock_version != page.lock_version:
        raise EditConflict(
            "This page was changed by someone else since you opened it.",
            details={
                "lock_version": page.lock_version,
                "updated_by": page.updated_by.display_name if page.updated_by else None,
                "updated_at": iso(page.draft_updated_at or page.updated_at),
            },
        )


def _touch(page: Page, actor: User | None) -> None:
    page.lock_version += 1
    page.draft_updated_at = _now()
    page.updated_by_id = actor.id if actor else None


def _apply_sections(page: Page, clean: list[dict[str, Any]]) -> None:
    keep = {c["id"] for c in clean if c.get("id")}
    for section in list(page.sections):
        if section.id not in keep:
            page.sections.remove(section)
    db.session.flush()
    rows = {s.id: s for s in page.sections}
    for order, item in enumerate(clean):
        row = rows.get(item["id"]) if item.get("id") else None
        if row is None:
            row = PageSection(key=item["key"])
            page.sections.append(row)
        row.name = item["name"] or None
        row.section_type = item["section_type"]
        row.variant = item["variant"]
        row.content = item["content"]
        row.design = item["design"]
        row.visibility = item["visibility"]
        row.is_visible = item["is_visible"]
        row.reusable_section_id = item["reusable_section_id"]
        row.display_order = order
    db.session.flush()
    page.sections.sort(key=lambda s: s.display_order)


def _apply_meta(page: Page, meta: dict[str, Any]) -> None:
    old_path = page.path
    for field, value in meta.items():
        setattr(page, field, value)
    if "path" in meta and meta["path"] != old_path:
        for child in _descendants(page):
            child.path = _compute_path(child.slug, child.parent)


def save_draft(page: Page, data: dict[str, Any], actor: User) -> Page:
    require(page, actor, "edit")
    _check_lock(page, data.get("lock_version"))
    errors: dict[str, list[str]] = {}
    meta = _clean_meta(page, data.get("page") or {}, errors)
    if (
        meta.get("slug", page.slug) != page.slug
        or meta.get("parent_id", page.parent_id) != page.parent_id
    ):
        require(page, actor, "change_slug")
    clean = _clean_sections(page.sections, data["sections"], errors) if "sections" in data else None
    if errors:
        raise ValidationError(
            "Some fields need attention before the draft can be saved.", details=errors
        )
    before_hash = page_render.doc_hash(page_render.draft_document(page))
    _apply_meta(page, meta)
    if clean is not None:
        _apply_sections(page, clean)
    db.session.flush()
    if page_render.doc_hash(page_render.draft_document(page)) != before_hash:
        _touch(page, actor)
        audit_service.record(
            "page.draft_saved",
            "page",
            page.id,
            actor=actor,
            details={"sections": len(page.sections), "fields": sorted(meta)},
        )
    return page


# ---- revisions ----------------------------------------------------------------------------


def _record_revision(
    page: Page, kind: str, doc: dict, actor: User | None, summary: str = ""
) -> PageRevision:
    number = (
        db.session.scalar(
            select(func.max(PageRevision.number)).where(PageRevision.page_id == page.id)
        )
        or 0
    ) + 1
    revision = PageRevision(
        page_id=page.id,
        number=number,
        kind=kind,
        summary=summary[:200] or None,
        snapshot=copy.deepcopy(doc),
        created_by_id=actor.id if actor else None,
    )
    db.session.add(revision)
    db.session.flush()
    # Keep history bounded (scheduled revisions are never pruned while pending).
    stale = db.session.scalars(
        select(PageRevision)
        .where(PageRevision.page_id == page.id, PageRevision.id != page.scheduled_revision_id)
        .order_by(PageRevision.number.desc())
        .offset(MAX_REVISIONS)
    ).all()
    for old in stale:
        db.session.delete(old)
    return revision


def revision_dict(r: PageRevision, *, with_snapshot: bool = False) -> dict[str, Any]:
    labels = {
        "published": "Published",
        "scheduled": "Scheduled",
        "draft_backup": "Draft saved before a restore",
        "scheduled_published": "Published on schedule",
    }
    data = {
        "id": r.id,
        "number": r.number,
        "kind": r.kind,
        "kind_label": labels.get(r.kind, r.kind),
        "summary": r.summary,
        "title": (r.snapshot.get("page") or {}).get("title"),
        "section_count": len(r.snapshot.get("sections", [])),
        "created_at": iso(r.created_at),
        "created_by": _user_ref(r.created_by),
    }
    if with_snapshot:
        data["sections"] = [
            {
                "key": s.get("key"),
                "name": s.get("name"),
                "section_type": s.get("section_type"),
                "type_label": SECTION_TYPES.get(s.get("section_type"), {}).get("label"),
                "is_visible": s.get("is_visible", True),
                "heading": (s.get("content") or {}).get("heading"),
            }
            for s in r.snapshot.get("sections", [])
        ]
    return data


def list_revisions(page: Page) -> list[dict[str, Any]]:
    stmt = (
        select(PageRevision)
        .where(PageRevision.page_id == page.id)
        .order_by(PageRevision.number.desc())
    )
    return [revision_dict(r) for r in db.session.scalars(stmt)]


def get_revision(page: Page, revision_id: int) -> PageRevision:
    revision = db.session.get(PageRevision, revision_id)
    if revision is None or revision.page_id != page.id:
        raise NotFoundError("Revision not found.")
    return revision


def _load_document_into_draft(page: Page, doc: dict[str, Any]) -> None:
    meta = {
        k: v
        for k, v in (doc.get("page") or {}).items()
        if k
        in (
            "title",
            "seo_title",
            "meta_description",
            "noindex",
            "canonical_url",
            "social_title",
            "social_description",
            "social_image_id",
        )
    }
    for field, value in meta.items():
        setattr(page, field, value)
    page.sections.clear()
    db.session.flush()
    live_shared = set(db.session.scalars(select(ReusableSection.id)))
    for order, s in enumerate(doc.get("sections", [])):
        shared_id = s.get("reusable_section_id")
        if shared_id and shared_id not in live_shared:
            continue
        page.sections.append(
            PageSection(
                key=s["key"],
                name=s.get("name") or None,
                section_type=s["section_type"],
                variant=s.get("variant") or SECTION_TYPES[s["section_type"]]["defaults"]["variant"],
                content=copy.deepcopy(s.get("content") or {}),
                design=copy.deepcopy(s.get("design") or {}),
                visibility=copy.deepcopy(s.get("visibility") or {}),
                is_visible=s.get("is_visible", True),
                reusable_section_id=shared_id,
                display_order=order,
            )
        )
    db.session.flush()


def restore_revision(page: Page, revision: PageRevision, actor: User, lock_version: Any) -> Page:
    require(page, actor, "restore_revisions")
    _check_lock(page, lock_version)
    if page_render.has_unpublished_changes(page) and page.sections:
        _record_revision(
            page,
            "draft_backup",
            page_render.draft_document(page),
            actor,
            f"Draft before restoring revision #{revision.number}",
        )
    _load_document_into_draft(page, revision.snapshot)
    _touch(page, actor)
    audit_service.record(
        "page.revision_restored",
        "page",
        page.id,
        actor=actor,
        details={"revision": revision.number},
    )
    return page


# ---- publishing ---------------------------------------------------------------------------


def _validate_for_publish(page: Page, doc: dict[str, Any]) -> None:
    errors: dict[str, list[str]] = {}
    items = [dict(s, id=None) for s in doc["sections"]]
    # Re-validate everything (references may have been deleted since the draft was saved).
    _clean_sections([], items, errors)
    if not any(s.get("is_visible", True) for s in doc["sections"]):
        errors["sections"] = ["Add at least one visible section before publishing."]
    if not (doc["page"].get("title") or "").strip():
        errors["page.title"] = ["A title is required."]
    if not is_home(page):
        path = doc["page"].get("path")
        clash = db.session.scalar(
            select(Page).where(Page.published_path == path, Page.id != page.id)
        )
        if clash is not None:
            errors["page.slug"] = [f"{path} is live as “{clash.title}”. Choose another address."]
    if errors:
        raise ValidationError("This page cannot be published yet.", details=errors)


def _publish_document(
    page: Page, doc: dict[str, Any], actor: User | None, kind: str
) -> PageRevision:
    _validate_for_publish(page, doc)
    old_path = page.published_path if page.status == "published" else None
    new_path = "/" if is_home(page) else doc["page"]["path"]
    now = _now()
    page.published_snapshot = copy.deepcopy(doc)
    page.status = "published"
    page.published_path = new_path
    page.published_at = now
    page.first_published_at = page.first_published_at or now
    page.published_by_id = actor.id if actor else None
    page.archived_at = None
    db.session.flush()
    from .. import redirect_service

    if old_path and old_path != new_path:
        redirect_service.create_slug_redirect(old_path, new_path, actor)
        # Live sub-pages move with their parent.
        for child in _descendants(page):
            if child.status != "published" or not child.published_path:
                continue
            if child.published_path.startswith(old_path + "/"):
                moved = new_path + child.published_path[len(old_path) :]
                redirect_service.create_slug_redirect(child.published_path, moved, actor)
                child.published_path = moved
                snap = copy.deepcopy(child.published_snapshot or {})
                if snap.get("page"):
                    snap["page"]["path"] = moved
                child.published_snapshot = snap
    else:
        for r in db.session.scalars(select(Redirect).where(Redirect.source_path == new_path)):
            db.session.delete(r)
    revision = _record_revision(page, kind, doc, actor)
    record_public_change("page", page.id, "page_published", actor)
    audit_service.record(
        "page.published",
        "page",
        page.id,
        actor=actor,
        details={"path": new_path, "revision": revision.number, "by": kind},
    )
    return revision


def publish(page: Page, actor: User, lock_version: Any) -> Page:
    require(page, actor, "publish")
    _check_lock(page, lock_version)
    _publish_document(page, page_render.draft_document(page), actor, "published")
    if page.scheduled_at:
        page.scheduled_at = None
        page.scheduled_revision_id = None
    page.lock_version += 1
    return page


def schedule(page: Page, when: datetime, actor: User, lock_version: Any) -> Page:
    require(page, actor, "publish")
    _check_lock(page, lock_version)
    if when.tzinfo is None:
        raise ValidationError(details={"scheduled_at": ["Include a time zone."]})
    if when <= _now() + SCHEDULE_GRACE:
        raise ValidationError(details={"scheduled_at": ["Choose a time in the future."]})
    doc = page_render.draft_document(page)
    _validate_for_publish(page, doc)
    revision = _record_revision(page, "scheduled", doc, actor, f"Scheduled for {when.isoformat()}")
    page.scheduled_at = when
    page.scheduled_revision_id = revision.id
    page.lock_version += 1
    audit_service.record(
        "page.scheduled", "page", page.id, actor=actor, details={"at": when.isoformat()}
    )
    return page


def unschedule(page: Page, actor: User) -> Page:
    require(page, actor, "publish")
    page.scheduled_at = None
    page.scheduled_revision_id = None
    page.lock_version += 1
    audit_service.record("page.unscheduled", "page", page.id, actor=actor)
    return page


def publish_due(now: datetime | None = None) -> dict[str, list]:
    """Publish pages whose scheduled time has passed (called by `flask publish-due`)."""
    now = now or _now()
    published, failed = [], []
    for page in db.session.scalars(
        select(Page).where(Page.scheduled_at.is_not(None), Page.scheduled_at <= now)
    ).all():
        revision = db.session.get(PageRevision, page.scheduled_revision_id or 0)
        try:
            with db.session.begin_nested():
                if revision is None:
                    raise ValueError("missing scheduled revision")
                _publish_document(page, revision.snapshot, None, "scheduled_published")
                page.scheduled_at = None
                page.scheduled_revision_id = None
                page.lock_version += 1
            published.append(page.published_path)
        except Exception as exc:  # recorded and visible in the audit log
            failed.append(page.id)
            page.scheduled_at = None
            audit_service.record(
                "scheduler.failed", "page", page.id, details={"error": type(exc).__name__}
            )
    return {"published": published, "failed": failed}


def unpublish(page: Page, actor: User) -> Page:
    require(page, actor, "unpublish")
    page.status = "draft"
    page.published_path = None
    page.scheduled_at = None
    page.scheduled_revision_id = None
    page.lock_version += 1
    record_public_change("page", page.id, "page_unpublished", actor)
    audit_service.record("page.unpublished", "page", page.id, actor=actor)
    return page


def discard_draft(page: Page, actor: User) -> Page:
    require(page, actor, "edit")
    if page.status != "published" or not page.published_snapshot:
        raise ConflictError("Only published pages have a live version to go back to.")
    snap = page.published_snapshot
    _load_document_into_draft(page, snap)
    meta = snap.get("page") or {}
    if not is_home(page):
        page.slug, page.parent_id, page.path = meta["slug"], meta.get("parent_id"), meta["path"]
    _touch(page, actor)
    audit_service.record("page.draft_discarded", "page", page.id, actor=actor)
    return page


def archive(page: Page, actor: User) -> Page:
    require(page, actor, "archive")
    was_live = page.status == "published"
    page.status = "archived"
    page.archived_at = _now()
    page.published_path = None
    page.scheduled_at = None
    page.scheduled_revision_id = None
    page.lock_version += 1
    if was_live:
        record_public_change("page", page.id, "page_archived", actor)
    audit_service.record("page.archived", "page", page.id, actor=actor)
    return page


def restore(page: Page, actor: User) -> Page:
    require(page, actor, "restore")
    clash = db.session.scalar(select(Page).where(Page.path == page.path, Page.id != page.id))
    if clash is not None:
        raise ConflictError(
            f"{page.path} is now used by “{clash.title}”. Change one of the addresses first."
        )
    page.status = "draft"
    page.archived_at = None
    page.lock_version += 1
    audit_service.record("page.restored", "page", page.id, actor=actor)
    return page


# ---- creation -------------------------------------------------------------------------------


def _template_sections(template: str) -> list[dict[str, Any]]:
    out = []
    for spec in PAGE_TEMPLATES[template]["sections"]:
        clean, errors, _ = check_section(
            spec["section_type"], spec["variant"], spec["content"], spec.get("design")
        )
        assert not errors, (template, spec["section_type"], errors)
        out.append({**clean, "section_type": spec["section_type"], "name": spec["name"]})
    return out


def create_page(data: dict[str, Any], actor: User) -> Page:
    if P.PAGES_CREATE.value not in effective_permissions(actor):
        raise ForbiddenError("You do not have permission to create pages.")
    errors: dict[str, list[str]] = {}
    title = " ".join((data.get("title") or "").split())
    if not title:
        errors["title"] = ["A title is required."]
    elif len(title) > 200 or plain_text_problem(title):
        errors["title"] = ["Use a plain-text title of up to 200 characters."]
    template = data.get("template") or "standard"
    if template not in PAGE_TEMPLATES:
        errors["template"] = [f"Use one of: {', '.join(PAGE_TEMPLATES)}."]
    slug = (data.get("slug") or slugify(title)).strip()
    path, path_errors = path_problems(slug, data.get("parent_id"))
    errors.update(path_errors)
    if errors:
        raise ValidationError("The page could not be created.", details=errors)
    page = Page(
        slug=slug,
        title=title,
        status="draft",
        template=template,
        parent_id=data.get("parent_id"),
        path=path,
        lock_version=1,
        draft_updated_at=_now(),
        updated_by_id=actor.id,
    )
    db.session.add(page)
    db.session.flush()
    for order, spec in enumerate(_template_sections(template)):
        key = f"{spec['section_type'].replace('_', '-')}-{order + 1}"
        page.sections.append(
            PageSection(
                key=key,
                name=spec["name"],
                section_type=spec["section_type"],
                variant=spec["variant"],
                content=spec["content"],
                design=spec["design"],
                visibility=spec["visibility"],
                display_order=order,
            )
        )
    db.session.flush()
    audit_service.record(
        "page.created", "page", page.id, actor=actor, details={"path": path, "template": template}
    )
    return page


def duplicate(page: Page, actor: User) -> Page:
    require(page, actor, "duplicate")
    base, n = f"{page.slug}-copy", 2
    slug = base
    while db.session.scalar(select(Page.id).where(Page.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    path, errors = path_problems(slug, page.parent_id)
    if errors:
        raise ValidationError("The page could not be duplicated.", details=errors)
    copy_page = Page(
        slug=slug,
        title=f"Copy of {page.title}"[:200],
        status="draft",
        template=page.template,
        parent_id=page.parent_id,
        path=path,
        seo_title=page.seo_title,
        meta_description=page.meta_description,
        noindex=page.noindex,
        social_title=page.social_title,
        social_description=page.social_description,
        social_image_id=page.social_image_id,
        lock_version=1,
        draft_updated_at=_now(),
        updated_by_id=actor.id,
    )
    db.session.add(copy_page)
    db.session.flush()
    for s in page.sections:
        copy_page.sections.append(
            PageSection(
                key=s.key,
                name=s.name,
                section_type=s.section_type,
                variant=s.variant,
                content=copy.deepcopy(s.content),
                design=copy.deepcopy(s.design or {}),
                visibility=copy.deepcopy(s.visibility or {}),
                is_visible=s.is_visible,
                reusable_section_id=s.reusable_section_id,
                display_order=s.display_order,
            )
        )
    db.session.flush()
    audit_service.record(
        "page.duplicated", "page", copy_page.id, actor=actor, details={"from": page.id}
    )
    return copy_page


def ensure_home(actor: User | None = None) -> Page:
    """The homepage row (created from the built-in defaults on a fresh installation)."""
    page = db.session.scalar(select(Page).where(Page.slug == HOME_SLUG))
    if page is not None:
        return page
    page = Page(
        slug=HOME_SLUG,
        title="Homepage",
        status="draft",
        template="home",
        is_system=True,
        path="/",
        lock_version=1,
    )
    db.session.add(page)
    db.session.flush()
    _load_document_into_draft(page, page_render.default_home_document())
    return page


def preview(page: Page, data: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the saved draft, or unsaved edits sent by the editor, without saving."""
    doc = page_render.draft_document(page)
    errors: dict[str, list[str]] = {}
    if data and "sections" in data:
        items = data["sections"] if isinstance(data["sections"], list) else []
        clean = _clean_sections(page.sections, items, errors)
        doc["sections"] = [{k: c[k] for k in page_render.SECTION_FIELDS} for c in clean]
    if data and isinstance(data.get("page"), dict):
        for key in ("title", "seo_title", "meta_description"):
            if isinstance(data["page"].get(key), str):
                doc["page"][key] = data["page"][key]
    resolved = page_render.resolve_document(doc, preview=True, published_at=page.published_at)
    return {"page": resolved, "errors": errors}


# ---- Batch 02 section endpoints (still supported; they edit the draft) ------------------------


def get_section(page: Page, section_id: int) -> PageSection:
    section = db.session.get(PageSection, section_id)
    if section is None or section.page_id != page.id:
        raise NotFoundError("Section not found.")
    return section


def _as_items(page: Page) -> list[dict[str, Any]]:
    return [{"id": s.id, **page_render.section_doc(s)} for s in page.sections]


def update_page(page: Page, data: dict[str, Any], actor: User) -> Page:
    meta = {k: data[k] for k in ("title", "seo_title", "meta_description", "noindex") if k in data}
    if data.get("status") == "published" and page.status != "published":
        publish(page, actor, page.lock_version)
    elif data.get("status") == "archived":
        archive(page, actor)
    if meta:
        save_draft(page, {"lock_version": page.lock_version, "page": meta}, actor)
    return page


def update_section(section: PageSection, data: dict[str, Any], actor: User) -> PageSection:
    page = section.page
    items = _as_items(page)
    for item in items:
        if item["id"] == section.id:
            item.update(
                {
                    k: v
                    for k, v in data.items()
                    if k in ("variant", "content", "is_visible", "design", "visibility", "name")
                }
            )
    try:
        save_draft(page, {"lock_version": page.lock_version, "sections": items}, actor)
    except ValidationError as exc:
        index = next(i for i, it in enumerate(items) if it["id"] == section.id)
        prefix = f"sections.{index}."
        details = {
            k[len(prefix) :].replace("content.", "", 1): v
            for k, v in (exc.details or {}).items()
            if k.startswith(prefix)
        }
        raise ValidationError(
            "The section content is invalid.", details=details or exc.details
        ) from exc
    return section


def create_section(page: Page, data: dict[str, Any], actor: User) -> PageSection:
    key = data["key"]
    if not SLUG_RE.match(key):
        raise ValidationError(details={"key": ["Use lowercase letters, numbers and hyphens."]})
    if any(s.key == key for s in page.sections):
        raise ConflictError(details={"key": ["Already used on this page."]})
    items = _as_items(page) + [
        {
            "key": key,
            "section_type": data["section_type"],
            "variant": data.get("variant"),
            "content": data.get("content") or {},
            "is_visible": data.get("is_visible", True),
        }
    ]
    save_draft(page, {"lock_version": page.lock_version, "sections": items}, actor)
    return next(s for s in page.sections if s.key == key)


def reorder_sections(page: Page, ordered_ids: list[int], actor: User) -> Page:
    current = {s.id: s for s in page.sections}
    if sorted(ordered_ids) != sorted(current):
        raise ValidationError(details={"order": ["Provide every section id exactly once."]})
    by_id = {item["id"]: item for item in _as_items(page)}
    save_draft(
        page,
        {"lock_version": page.lock_version, "sections": [by_id[i] for i in ordered_ids]},
        actor,
    )
    return page
