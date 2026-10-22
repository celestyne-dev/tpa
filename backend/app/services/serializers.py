"""Model → dict conversion shared by public and admin services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..cms.blocks import blocks_word_count
from ..models import Article, Author, MediaAsset, Tag, Topic

WORDS_PER_MINUTE = 225
FALLBACK_IMAGE = {
    "src": "/og/default.png",
    "alt": "Think Positive Always",
    "width": 1200,
    "height": 630,
}


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def reading_time(body: list[dict[str, Any]]) -> int:
    return max(1, round(blocks_word_count(body) / WORDS_PER_MINUTE))


def media_dict(asset: MediaAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "id": asset.id,
        "filename": asset.filename,
        "mime_type": asset.mime_type,
        "url": asset.public_url,
        "alt_text": asset.alt_text,
        "width": asset.width,
        "height": asset.height,
        "size_bytes": asset.size_bytes,
        "visibility": asset.visibility,
        "created_at": iso(asset.created_at),
    }


def author_ref(author: Author | None) -> dict[str, Any] | None:
    return {"slug": author.slug, "name": author.display_name} if author else None


def topic_ref(topic: Topic | None) -> dict[str, Any] | None:
    return {"slug": topic.slug, "name": topic.name} if topic else None


def public_article(article: Article, *, include_body: bool = True) -> dict[str, Any]:
    """Public article shape (unchanged from Batch 01)."""
    image = (
        article.featured_image.as_image() if article.featured_image else None
    ) or FALLBACK_IMAGE
    data: dict[str, Any] = {
        "id": str(article.id),
        "slug": article.slug,
        "title": article.title,
        "excerpt": article.excerpt,
        "topic_slug": article.primary_topic.slug if article.primary_topic else None,
        "topic": topic_ref(article.primary_topic),
        "secondary_topic_slugs": [t.slug for t in article.secondary_topics],
        "author": author_ref(article.author) or {"slug": "tpa", "name": "Think Positive Always"},
        "published_at": iso(article.published_at),
        "updated_at": iso(article.updated_at),
        "featured": article.featured,
        "reading_time_minutes": reading_time(article.body or []),
        "image": image,
        "source": article.source,
    }
    if include_body:
        og = article.social_image.as_image() if article.social_image else None
        seo = {
            k: v
            for k, v in {
                "title": article.seo_title,
                "description": article.meta_description,
                "canonical_url": article.canonical_url,
                "no_index": article.noindex or None,
                "og_image": og,
            }.items()
            if v
        }
        data.update(
            subtitle=article.subtitle,
            tags=[t.name for t in article.tags],
            body=article.body or [],
            canonical_url=article.canonical_url,
            seo=seo or None,
        )
    return data


def public_topic(topic: Topic, article_count: int) -> dict[str, Any]:
    seo = {
        k: v
        for k, v in {"title": topic.seo_title, "description": topic.seo_description}.items()
        if v
    }
    return {
        "slug": topic.slug,
        "name": topic.name,
        "description": topic.description,
        "intro": topic.intro,
        "icon": topic.icon,
        "featured": topic.featured,
        "article_count": article_count,
        "seo": seo or None,
    }


def tag_dict(tag: Tag, usage: int | None = None) -> dict[str, Any]:
    data = {"id": tag.id, "name": tag.name, "slug": tag.slug, "description": tag.description}
    if usage is not None:
        data["article_count"] = usage
    return data
