from __future__ import annotations

from ..utils.errors import NotFoundError
from .content_repository import Record, get_repository


def _published_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for article in get_repository().list_articles():
        if article.get("status") != "published":
            continue
        for slug in {article["topic_slug"], *article.get("secondary_topic_slugs", [])}:
            counts[slug] = counts.get(slug, 0) + 1
    return counts


def list_topics(featured: bool | None = None) -> list[Record]:
    counts = _published_counts()
    topics = get_repository().list_topics()
    if featured is not None:
        topics = [t for t in topics if bool(t.get("featured")) is featured]
    return [{**t, "article_count": counts.get(t["slug"], 0)} for t in topics]


def get_topic(slug: str) -> Record:
    for topic in list_topics():
        if topic["slug"] == slug:
            return topic
    raise NotFoundError(f"Topic '{slug}' was not found.")


def topic_lookup() -> dict[str, Record]:
    return {t["slug"]: t for t in get_repository().list_topics()}
