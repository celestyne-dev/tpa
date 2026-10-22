"""Model → dict conversion shared by public and admin services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..cms.blocks import blocks_word_count, media_ids, related_ids
from ..extensions import db
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


def _image_with_alt(asset: MediaAsset | None, alt: str | None) -> dict[str, Any] | None:
    if asset is None or asset.visibility != "public":
        return None
    image = asset.as_image()
    if image and alt:
        image["alt"] = alt
    return image


def expand_body(body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve media ids and related-article ids for public rendering.

    Blocks whose images no longer exist are dropped rather than rendered broken.
    Related articles are limited to currently published ones.
    """
    ids = media_ids(body)
    assets = (
        {a.id: a for a in db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))}
        if ids
        else {}
    )
    rel_ids = related_ids(body)
    related = (
        {
            a.id: a
            for a in db.session.scalars(
                select(Article).where(Article.id.in_(rel_ids), Article.status == "published")
            )
        }
        if rel_ids
        else {}
    )
    out: list[dict[str, Any]] = []
    for block in body or []:
        kind = block.get("type")
        if kind == "image":
            image = _image_with_alt(assets.get(block.get("media_id")), block.get("alt"))
            if image is None:
                continue
            out.append({**block, "image": image})
        elif kind == "gallery":
            items = []
            for item in block.get("items", []):
                image = _image_with_alt(assets.get(item.get("media_id")), item.get("alt"))
                if image:
                    items.append({**item, "image": image})
            if items:
                out.append({**block, "items": items})
        elif kind == "related":
            articles = [
                public_article(related[i], include_body=False)
                for i in block.get("article_ids", [])
                if i in related
            ]
            if articles:
                out.append({**block, "articles": articles})
        elif kind == "resource" and block.get("media_id"):
            out.append({**block, "image": _image_with_alt(assets.get(block["media_id"]), None)})
        else:
            out.append(block)
    return out


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
        social_source = article.social_image or article.featured_image
        og = social_source.as_image("social") if social_source else None
        seo = {
            k: v
            for k, v in {
                "title": article.seo_title,
                "description": article.meta_description,
                "canonical_url": article.canonical_url,
                "no_index": article.noindex or None,
                "og_image": og,
                "og_title": article.social_title,
                "og_description": article.social_description,
            }.items()
            if v
        }
        data.update(
            subtitle=article.subtitle,
            tags=[t.name for t in article.tags],
            body=expand_body(article.body or []),
            canonical_url=article.canonical_url,
            seo=seo or None,
            first_published_at=iso(article.first_published_at),
            author_profile=_author_profile(article.author),
        )
    return data


def _author_profile(author: Author | None) -> dict[str, Any] | None:
    """Only real author records produce Person structured data on the frontend."""
    if author is None:
        return None
    portrait = author.profile_image.as_image("avatar") if author.profile_image else None
    return {
        "slug": author.slug,
        "name": author.display_name,
        "bio": author.bio,
        "image": portrait,
        "is_person": author.is_person,
    }


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
