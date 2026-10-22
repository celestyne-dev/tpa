"""Public article queries. Only published articles whose publish time has passed are visible."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select

from ..extensions import db
from ..models import Article, Topic, article_topics
from ..utils.errors import NotFoundError
from .serializers import public_article


def _now() -> datetime:
    return datetime.now(UTC)


def published_filter():
    return (Article.status == "published") & (Article.published_at <= _now())


def _topic_filter(slug: str):
    return or_(
        Article.primary_topic.has(Topic.slug == slug),
        Article.secondary_topics.any(Topic.slug == slug),
    )


def published_topic_counts() -> dict[int, int]:
    """Published article count per topic (primary or secondary, counted once)."""
    pairs: set[tuple[int, int]] = set()
    rows = db.session.execute(
        select(Article.id, Article.primary_topic_id).where(published_filter())
    )
    for article_id, topic_id in rows:
        if topic_id:
            pairs.add((article_id, topic_id))
    secondary = db.session.execute(
        select(article_topics.c.article_id, article_topics.c.topic_id)
        .join(Article, Article.id == article_topics.c.article_id)
        .where(published_filter())
    )
    pairs.update((a, t) for a, t in secondary)
    counts: dict[int, int] = {}
    for _, topic_id in pairs:
        counts[topic_id] = counts.get(topic_id, 0) + 1
    return counts


def list_articles(
    *, topic: str | None = None, featured: bool | None = None, page: int = 1, page_size: int = 12
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conditions = [published_filter()]
    if topic:
        conditions.append(_topic_filter(topic))
    if featured is not None:
        conditions.append(Article.featured.is_(featured))

    total = db.session.scalar(select(func.count(Article.id)).where(*conditions)) or 0
    stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [public_article(a, include_body=False) for a in db.session.scalars(stmt)]
    total_pages = max(1, math.ceil(total / page_size))
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    return items, pagination


def get_article_model(slug: str) -> Article:
    article = db.session.scalar(select(Article).where(Article.slug == slug, published_filter()))
    if article is None:
        raise NotFoundError(f"Article '{slug}' was not found.")
    return article


def get_article(slug: str) -> dict[str, Any]:
    return public_article(get_article_model(slug))


def related_articles(slug: str, limit: int = 3) -> list[dict[str, Any]]:
    """Same primary topic first, then shared secondary topics, then most recent."""
    article = get_article_model(slug)
    own = {t.id for t in article.secondary_topics} | {article.primary_topic_id}
    candidates = db.session.scalars(
        select(Article)
        .where(published_filter(), Article.id != article.id)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .limit(60)
    ).all()

    def score(other: Article) -> int:
        if other.primary_topic_id and other.primary_topic_id == article.primary_topic_id:
            return 2
        theirs = {t.id for t in other.secondary_topics} | {other.primary_topic_id}
        return 1 if own & theirs else 0

    ranked = sorted(candidates, key=score, reverse=True)[:limit]
    return [public_article(a, include_body=False) for a in ranked]
