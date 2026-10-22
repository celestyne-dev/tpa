"""Helpers shared by admin services."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.sql import Select

from ...extensions import db
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE, slugify


def paginate(stmt: Select, page: int, page_size: int) -> tuple[list[Any], dict[str, Any]]:
    total = db.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    total_pages = max(1, math.ceil(total / page_size))
    return items, {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def get_or_404(model, ident: int, label: str):
    obj = db.session.get(model, ident)
    if obj is None:
        raise NotFoundError(f"{label} not found.")
    return obj


def resolve_slug(model, requested: str | None, fallback_source: str, *, exclude_id=None) -> str:
    slug = (requested or "").strip() or slugify(fallback_source)
    if not slug or not SLUG_RE.match(slug):
        raise ValidationError(details={"slug": ["Use lowercase letters, numbers and hyphens."]})
    stmt = select(model.id).where(model.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if db.session.scalar(stmt) is not None:
        raise ConflictError("That slug is already in use.", details={"slug": ["Already in use."]})
    return slug
