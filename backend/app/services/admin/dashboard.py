"""Dashboard overview built only from real database records."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...auth.decorators import has_permission
from ...auth.permissions import Permission
from ...extensions import db
from ...models import Article, AuditLog, Author, Tag, Topic, User
from .. import publication_service
from ..serializers import iso
from .article_admin import admin_summary, status_counts


def audit_entry(e: AuditLog) -> dict[str, Any]:
    return {
        "id": e.id,
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "details": e.details,
        "actor": {"id": e.actor.id, "display_name": e.actor.display_name, "email": e.actor.email}
        if e.actor
        else None,
        "ip_address": e.ip_address,
        "created_at": iso(e.created_at),
    }


def overview(user: User) -> dict[str, Any]:
    counts = status_counts()
    recent = db.session.scalars(
        select(Article).order_by(Article.updated_at.desc(), Article.id.desc()).limit(8)
    ).all()
    data: dict[str, Any] = {
        "articles": {"total": sum(counts.values()), **counts},
        "topics_total": db.session.scalar(select(func.count(Topic.id))) or 0,
        "authors_total": db.session.scalar(select(func.count(Author.id))) or 0,
        "tags_total": db.session.scalar(select(func.count(Tag.id))) or 0,
        "recent_articles": [admin_summary(a) for a in recent],
        "recent_audit": None,
        "publishing": publication_service.status(),
    }
    if has_permission(user, Permission.AUDIT_READ):
        entries = db.session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(10)
        ).all()
        data["recent_audit"] = [audit_entry(e) for e in entries]
    return data
