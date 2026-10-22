"""Dashboard overview built only from real database records."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...auth.decorators import has_any_permission, has_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Article, AuditLog, Author, Tag, Topic, User
from .. import publication_service
from ..serializers import iso
from .article_admin import admin_summary, scope_filter, status_counts


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
    data: dict[str, Any] = {
        "articles": None,
        "topics_total": db.session.scalar(select(func.count(Topic.id))) or 0,
        "authors_total": db.session.scalar(select(func.count(Author.id))) or 0,
        "tags_total": db.session.scalar(select(func.count(Tag.id))) or 0,
        "recent_articles": None,
        "recent_audit": None,
        "publishing": publication_service.status(),
    }
    if has_any_permission(
        user, P.ARTICLES_VIEW, P.ARTICLES_CREATE, P.ARTICLES_EDIT_OWN, P.ARTICLES_EDIT_ANY
    ):
        counts = status_counts(user)
        stmt = select(Article).order_by(Article.updated_at.desc(), Article.id.desc()).limit(8)
        if (scope := scope_filter(user)) is not None:
            stmt = stmt.where(scope)
        data["articles"] = {"total": sum(counts.values()), **counts}
        data["recent_articles"] = [admin_summary(a) for a in db.session.scalars(stmt).all()]
    if has_permission(user, P.AUDIT_VIEW):
        entries = db.session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(10)
        ).all()
        data["recent_audit"] = [audit_entry(e) for e in entries]
    return data


def analytics_summary() -> dict[str, Any]:
    """Content analytics computed from editorial records (no traffic or sales data exists yet)."""
    from ...models import Article as A
    from ...models import Topic as T

    by_topic = db.session.execute(
        select(T.name, func.count(A.id))
        .join(A, A.primary_topic_id == T.id)
        .where(A.status == "published")
        .group_by(T.name)
        .order_by(func.count(A.id).desc(), T.name)
    ).all()
    published = db.session.scalars(
        select(A.published_at).where(A.status == "published", A.published_at.is_not(None))
    ).all()
    per_month: dict[str, int] = {}
    for value in published:
        key = value.strftime("%Y-%m")
        per_month[key] = per_month.get(key, 0) + 1
    return {
        "articles_by_status": status_counts(),
        "published_by_topic": [{"topic": name, "count": n} for name, n in by_topic],
        "published_by_month": [{"month": k, "count": per_month[k]} for k in sorted(per_month)],
        "note": "Traffic, audience and revenue analytics arrive with the analytics module.",
    }
