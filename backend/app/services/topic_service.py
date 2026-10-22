"""Public topic queries (database-backed)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..models import Topic
from ..utils.errors import NotFoundError
from .article_service import published_topic_counts
from .serializers import public_topic


def list_topics(featured: bool | None = None) -> list[dict[str, Any]]:
    stmt = select(Topic).where(Topic.status == "active").order_by(Topic.display_order, Topic.name)
    if featured is not None:
        stmt = stmt.where(Topic.featured.is_(featured))
    counts = published_topic_counts()
    return [public_topic(t, counts.get(t.id, 0)) for t in db.session.scalars(stmt)]


def get_topic(slug: str) -> dict[str, Any]:
    topic = db.session.scalar(select(Topic).where(Topic.slug == slug, Topic.status == "active"))
    if topic is None:
        raise NotFoundError(f"Topic '{slug}' was not found.")
    return public_topic(topic, published_topic_counts().get(topic.id, 0))
