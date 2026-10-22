"""Topics, tags and authors management with referential-integrity safeguards.

Records still used by articles cannot be deleted; they can be archived or
their articles reassigned first. Nothing is silently detached.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from ...extensions import db
from ...models import Article, Author, MediaAsset, Tag, Topic, User, article_tags, article_topics
from ...utils.errors import ConflictError, ValidationError
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso, media_dict
from .common import get_or_404, resolve_slug

TOPIC_ICONS = (
    "sun",
    "sprout",
    "gem",
    "sunrise",
    "heart-handshake",
    "calendar-check",
    "flame",
    "leaf",
)


# ---- usage counts -------------------------------------------------------


def topic_usage(topic_id: int) -> int:
    primary = select(Article.id).where(Article.primary_topic_id == topic_id)
    secondary = select(article_topics.c.article_id).where(article_topics.c.topic_id == topic_id)
    return db.session.scalar(select(func.count()).select_from(primary.union(secondary).subquery()))


def author_usage(author_id: int) -> int:
    return db.session.scalar(select(func.count(Article.id)).where(Article.author_id == author_id))


def tag_usage(tag_id: int) -> int:
    return db.session.scalar(
        select(func.count()).select_from(article_tags).where(article_tags.c.tag_id == tag_id)
    )


# ---- serializers ------------------------------------------------------------


def topic_dict(t: Topic) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
        "intro": t.intro,
        "icon": t.icon,
        "featured": t.featured,
        "display_order": t.display_order,
        "status": t.status,
        "featured_image_id": t.featured_image_id,
        "seo_title": t.seo_title,
        "seo_description": t.seo_description,
        "article_count": topic_usage(t.id),
        "updated_at": iso(t.updated_at),
    }


def author_dict(a: Author) -> dict[str, Any]:
    return {
        "id": a.id,
        "display_name": a.display_name,
        "slug": a.slug,
        "bio": a.bio,
        "status": a.status,
        "profile_image_id": a.profile_image_id,
        "profile_image": media_dict(a.profile_image),
        "article_count": author_usage(a.id),
        "updated_at": iso(a.updated_at),
    }


def tag_dict(t: Tag) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
        "article_count": tag_usage(t.id),
        "updated_at": iso(t.updated_at),
    }


# ---- generic helpers ----------------------------------------------------------


def _check_image(image_id: int | None, field: str) -> None:
    if image_id is None:
        return
    asset = db.session.get(MediaAsset, image_id)
    if asset is None or asset.visibility != "public" or not asset.mime_type.startswith("image/"):
        raise ValidationError(details={field: ["Choose a public image."]})


def _write(model, obj, data: dict[str, Any], fields: tuple[str, ...], label_field: str):
    if "slug" in data or obj.id is None:
        obj.slug = resolve_slug(
            model,
            data.get("slug"),
            data.get(label_field) or getattr(obj, label_field) or "",
            exclude_id=obj.id,
        )
    for field in fields:
        if field in data:
            setattr(obj, field, data[field])


def _snapshot(obj, fields) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in ("slug", *fields)}


def _save(kind: str, model, obj, data, fields, label_field, actor: User, *, public: bool):
    creating = obj.id is None
    before = {} if creating else _snapshot(obj, fields)
    _write(model, obj, data, fields, label_field)
    if creating:
        db.session.add(obj)
    db.session.flush()
    changes = audit_service.changed_fields(before, _snapshot(obj, fields))
    if changes:
        audit_service.record(
            f"{kind}.{'created' if creating else 'updated'}",
            kind,
            obj.id,
            actor=actor,
            details=changes,
        )
        if public:
            record_public_change(kind, obj.id, f"{kind}_changed", actor)
    return obj


# ---- topics -------------------------------------------------------------------

TOPIC_FIELDS = (
    "name",
    "description",
    "intro",
    "icon",
    "featured",
    "display_order",
    "status",
    "featured_image_id",
    "seo_title",
    "seo_description",
)


def list_topics() -> list[dict[str, Any]]:
    stmt = select(Topic).order_by(Topic.display_order, Topic.name)
    return [topic_dict(t) for t in db.session.scalars(stmt)]


def save_topic(topic: Topic | None, data: dict[str, Any], actor: User) -> Topic:
    if "icon" in data and data["icon"] not in TOPIC_ICONS:
        raise ValidationError(details={"icon": [f"Use one of: {', '.join(TOPIC_ICONS)}."]})
    _check_image(data.get("featured_image_id"), "featured_image_id")
    return _save("topic", Topic, topic or Topic(), data, TOPIC_FIELDS, "name", actor, public=True)


def delete_topic(topic: Topic, actor: User) -> None:
    used = topic_usage(topic.id)
    if used:
        raise ConflictError(
            f"This topic is used by {used} article(s). Reassign those articles or archive the "
            "topic instead.",
            details={"article_count": used},
        )
    audit_service.record(
        "topic.deleted", "topic", topic.id, actor=actor, details={"slug": topic.slug}
    )
    record_public_change("topic", topic.id, "topic_deleted", actor)
    db.session.delete(topic)


def reassign_topic(topic: Topic, target_id: int, actor: User) -> int:
    target = get_or_404(Topic, target_id, "Target topic")
    if target.id == topic.id or target.status == "archived":
        raise ValidationError(details={"target_id": ["Choose a different, non-archived topic."]})
    moved = db.session.execute(
        update(Article)
        .where(Article.primary_topic_id == topic.id)
        .values(primary_topic_id=target.id)
    ).rowcount
    # Secondary links: move to target unless the article already has it.
    rows = (
        db.session.execute(
            select(article_topics.c.article_id).where(article_topics.c.topic_id == topic.id)
        )
        .scalars()
        .all()
    )
    for article_id in rows:
        article = db.session.get(Article, article_id)
        article.secondary_topics = [t for t in article.secondary_topics if t.id != topic.id]
        if target.id != article.primary_topic_id and target not in article.secondary_topics:
            article.secondary_topics.append(target)
    audit_service.record(
        "topic.reassigned",
        "topic",
        topic.id,
        actor=actor,
        details={"target_id": target.id, "primary_moved": moved, "secondary_moved": len(rows)},
    )
    record_public_change("topic", topic.id, "topic_reassigned", actor)
    return moved + len(rows)


# ---- authors ------------------------------------------------------------------

AUTHOR_FIELDS = ("display_name", "bio", "status", "profile_image_id")


def list_authors() -> list[dict[str, Any]]:
    return [
        author_dict(a) for a in db.session.scalars(select(Author).order_by(Author.display_name))
    ]


def save_author(author: Author | None, data: dict[str, Any], actor: User) -> Author:
    _check_image(data.get("profile_image_id"), "profile_image_id")
    return _save(
        "author",
        Author,
        author or Author(),
        data,
        AUTHOR_FIELDS,
        "display_name",
        actor,
        public=True,
    )


def delete_author(author: Author, actor: User) -> None:
    used = author_usage(author.id)
    if used:
        raise ConflictError(
            f"This author is credited on {used} article(s). Reassign those articles or archive "
            "the author instead.",
            details={"article_count": used},
        )
    audit_service.record(
        "author.deleted", "author", author.id, actor=actor, details={"slug": author.slug}
    )
    db.session.delete(author)


def reassign_author(author: Author, target_id: int, actor: User) -> int:
    target = get_or_404(Author, target_id, "Target author")
    if target.id == author.id or target.status != "active":
        raise ValidationError(details={"target_id": ["Choose a different, active author."]})
    moved = db.session.execute(
        update(Article).where(Article.author_id == author.id).values(author_id=target.id)
    ).rowcount
    audit_service.record(
        "author.reassigned",
        "author",
        author.id,
        actor=actor,
        details={"target_id": target.id, "articles": moved},
    )
    record_public_change("author", author.id, "author_reassigned", actor)
    return moved


# ---- tags ---------------------------------------------------------------------

TAG_FIELDS = ("name", "description")


def list_tags() -> list[dict[str, Any]]:
    return [tag_dict(t) for t in db.session.scalars(select(Tag).order_by(Tag.name))]


def save_tag(tag: Tag | None, data: dict[str, Any], actor: User) -> Tag:
    return _save("tag", Tag, tag or Tag(), data, TAG_FIELDS, "name", actor, public=True)


def delete_tag(tag: Tag, actor: User) -> None:
    used = tag_usage(tag.id)
    if used:
        raise ConflictError(
            f"This tag is used by {used} article(s). Remove it from those articles first.",
            details={"article_count": used},
        )
    audit_service.record("tag.deleted", "tag", tag.id, actor=actor, details={"slug": tag.slug})
    db.session.delete(tag)
