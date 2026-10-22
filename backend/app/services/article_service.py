from __future__ import annotations

import math
from typing import Any

from ..utils.errors import NotFoundError
from .content_repository import Record, get_repository
from .topic_service import topic_lookup

WORDS_PER_MINUTE = 225


def reading_time(body: list[Record]) -> int:
    words = 0
    for block in body:
        text = (
            " ".join(block.get("items", []))
            if block.get("type") == "list"
            else block.get("text", "")
        )
        words += len(text.split())
    return max(1, round(words / WORDS_PER_MINUTE))


def _enrich(article: Record, topics: dict[str, Record]) -> Record:
    topic = topics.get(article["topic_slug"])
    seo = article.get("seo") or {}
    legacy = article.get("legacy") or {}
    return {
        **article,
        "reading_time_minutes": article.get("reading_time_minutes")
        or reading_time(article["body"]),
        "topic": {"slug": topic["slug"], "name": topic["name"]} if topic else None,
        "canonical_url": seo.get("canonical_url") or legacy.get("canonical_url"),
    }


def _published() -> list[Record]:
    topics = topic_lookup()
    items = [
        _enrich(a, topics)
        for a in get_repository().list_articles()
        if a.get("status") == "published"
    ]
    return sorted(items, key=lambda a: a["published_at"], reverse=True)


def list_articles(
    *, topic: str | None = None, featured: bool | None = None, page: int = 1, page_size: int = 12
) -> tuple[list[Record], dict[str, Any]]:
    items = _published()
    if topic:
        items = [
            a
            for a in items
            if a["topic_slug"] == topic or topic in a.get("secondary_topic_slugs", [])
        ]
    if featured is not None:
        items = [a for a in items if bool(a.get("featured")) is featured]

    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    return items[start : start + page_size], pagination


def get_article(slug: str) -> Record:
    for article in _published():
        if article["slug"] == slug:
            return article
    raise NotFoundError(f"Article '{slug}' was not found.")


def related_articles(article: Record, limit: int = 3) -> list[Record]:
    """Same primary topic first, then shared secondary topics, then most recent."""
    own = {article["topic_slug"], *article.get("secondary_topic_slugs", [])}

    def score(other: Record) -> int:
        if other["topic_slug"] == article["topic_slug"]:
            return 2
        theirs = {other["topic_slug"], *other.get("secondary_topic_slugs", [])}
        return 1 if own & theirs else 0

    others = [a for a in _published() if a["id"] != article["id"]]
    # sorted() is stable, so recency order is preserved within each score.
    return sorted(others, key=score, reverse=True)[:limit]
