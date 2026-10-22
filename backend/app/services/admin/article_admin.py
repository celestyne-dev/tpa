"""Editorial article management and publication workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms.blocks import validate_blocks
from ...extensions import db
from ...models import Article, Author, MediaAsset, Tag, Topic, User
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso, media_dict, public_article, reading_time
from .common import paginate, resolve_slug

SCHEDULE_GRACE = timedelta(minutes=1)


def _now() -> datetime:
    return datetime.now(UTC)


def is_public(article: Article) -> bool:
    return (
        article.status == "published"
        and article.published_at is not None
        and article.published_at <= _now()
    )


# ---- ownership-aware access ---------------------------------------------------------


def can_view_all(user: User) -> bool:
    return P.ARTICLES_VIEW.value in effective_permissions(user)


def scope_filter(user: User):
    """Users without articles.view only see the articles they created."""
    return None if can_view_all(user) else (Article.created_by_id == user.id)


def is_owner(article: Article, user: User) -> bool:
    return article.created_by_id is not None and article.created_by_id == user.id


def capabilities(article: Article, user: User) -> dict[str, bool]:
    """What this user may do with this article (enforced again by every action)."""
    perms = effective_permissions(user)
    owner = is_owner(article, user)
    status = article.status
    can_edit = P.ARTICLES_EDIT_ANY.value in perms or (
        P.ARTICLES_EDIT_OWN.value in perms and owner and status == "draft"
    )
    return {
        "edit": can_edit,
        "submit": P.ARTICLES_SUBMIT_REVIEW.value in perms
        and (owner or P.ARTICLES_EDIT_ANY.value in perms)
        and status == "draft"
        and article.review_status != "submitted",
        "approve": P.ARTICLES_APPROVE.value in perms
        and article.review_status == "submitted"
        and status in ("draft", "scheduled"),
        "publish": P.ARTICLES_PUBLISH.value in perms and status in ("draft", "scheduled"),
        "unpublish": P.ARTICLES_UNPUBLISH.value in perms and status in ("published", "scheduled"),
        "archive": P.ARTICLES_ARCHIVE.value in perms and status != "archived",
        "restore": P.ARTICLES_ARCHIVE.value in perms and status == "archived",
        "delete": P.ARTICLES_DELETE.value in perms
        and article.first_published_at is None
        and status in ("draft", "archived"),
    }


def require_capability(article: Article, user: User, action: str) -> None:
    if not capabilities(article, user)[action]:
        raise ForbiddenError(f"You cannot {action} this article.")


def get_article_for(article_id: int, user: User) -> Article:
    article = db.session.get(Article, article_id)
    # Out-of-scope articles are reported as missing (no existence leak).
    if article is None or (not can_view_all(user) and not is_owner(article, user)):
        raise NotFoundError("Article not found.")
    return article


def admin_summary(a: Article) -> dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "slug": a.slug,
        "status": a.status,
        "featured": a.featured,
        "is_public": is_public(a),
        "published_at": iso(a.published_at),
        "updated_at": iso(a.updated_at),
        "author": {"id": a.author.id, "display_name": a.author.display_name} if a.author else None,
        "primary_topic": {"id": a.primary_topic.id, "name": a.primary_topic.name}
        if a.primary_topic
        else None,
        "source": a.source,
        "review_status": a.review_status,
        "created_by": {"id": a.created_by.id, "display_name": a.created_by.display_name}
        if a.created_by
        else None,
    }


def admin_detail(a: Article, user: User | None = None) -> dict[str, Any]:
    return {
        **admin_summary(a),
        "can": capabilities(a, user) if user else None,
        "submitted_at": iso(a.submitted_at),
        "approved_at": iso(a.approved_at),
        "subtitle": a.subtitle,
        "excerpt": a.excerpt,
        "body": a.body or [],
        "author_id": a.author_id,
        "primary_topic_id": a.primary_topic_id,
        "secondary_topic_ids": [t.id for t in a.secondary_topics],
        "tag_ids": [t.id for t in a.tags],
        "featured_image_id": a.featured_image_id,
        "featured_image": media_dict(a.featured_image),
        "social_image_id": a.social_image_id,
        "seo_title": a.seo_title,
        "meta_description": a.meta_description,
        "canonical_url": a.canonical_url,
        "noindex": a.noindex,
        "original_url": a.original_url,
        "original_slug": a.original_slug,
        "first_published_at": iso(a.first_published_at),
        "slug_locked": a.first_published_at is not None,
        "created_at": iso(a.created_at),
        "reading_time_minutes": reading_time(a.body or []),
    }


def list_articles(args: dict[str, Any], user: User) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(Article)
    if (scope := scope_filter(user)) is not None:
        stmt = stmt.where(scope)
    if args.get("q"):
        like = f"%{args['q'].strip()}%"
        stmt = stmt.where(or_(Article.title.ilike(like), Article.slug.ilike(like)))
    if args.get("status"):
        stmt = stmt.where(Article.status == args["status"])
    if args.get("topic_id"):
        stmt = stmt.where(Article.primary_topic_id == args["topic_id"])
    if args.get("author_id"):
        stmt = stmt.where(Article.author_id == args["author_id"])
    if args.get("featured") is not None:
        stmt = stmt.where(Article.featured.is_(args["featured"]))
    if args.get("review_status"):
        stmt = stmt.where(Article.review_status == args["review_status"])
    stmt = stmt.order_by(Article.updated_at.desc(), Article.id.desc())
    items, pagination = paginate(stmt, args["page"], args["page_size"])
    return [admin_summary(a) for a in items], pagination


def _load_refs(data: dict[str, Any], article: Article | None) -> dict[str, Any]:
    """Resolve and validate related records referenced by id."""
    errors: dict[str, list[str]] = {}
    refs: dict[str, Any] = {}
    if "author_id" in data:
        author = db.session.get(Author, data["author_id"]) if data["author_id"] else None
        if data["author_id"] and author is None:
            errors["author_id"] = ["Author not found."]
        elif (
            author
            and author.status != "active"
            and (article is None or article.author_id != author.id)
        ):
            errors["author_id"] = ["Archived authors cannot be assigned."]
        refs["author"] = author
    if "primary_topic_id" in data:
        topic = (
            db.session.get(Topic, data["primary_topic_id"]) if data["primary_topic_id"] else None
        )
        if data["primary_topic_id"] and topic is None:
            errors["primary_topic_id"] = ["Topic not found."]
        elif (
            topic
            and topic.status == "archived"
            and (article is None or article.primary_topic_id != topic.id)
        ):
            errors["primary_topic_id"] = ["Archived topics cannot be assigned."]
        refs["primary_topic"] = topic
    if "secondary_topic_ids" in data:
        ids = sorted(set(data["secondary_topic_ids"]))
        topics = db.session.scalars(select(Topic).where(Topic.id.in_(ids))).all() if ids else []
        if len(topics) != len(ids):
            errors["secondary_topic_ids"] = ["One or more topics were not found."]
        refs["secondary_topics"] = topics
    if "tag_ids" in data:
        ids = sorted(set(data["tag_ids"]))
        tags = db.session.scalars(select(Tag).where(Tag.id.in_(ids))).all() if ids else []
        if len(tags) != len(ids):
            errors["tag_ids"] = ["One or more tags were not found."]
        refs["tags"] = tags
    for field in ("featured_image_id", "social_image_id"):
        if field in data and data[field]:
            asset = db.session.get(MediaAsset, data[field])
            if asset is None:
                errors[field] = ["Media asset not found."]
            elif asset.visibility != "public" or not asset.mime_type.startswith("image/"):
                errors[field] = ["Choose a public image."]
    if errors:
        raise ValidationError(details=errors)
    return refs


_SCALARS = (
    "title",
    "subtitle",
    "excerpt",
    "featured",
    "featured_image_id",
    "social_image_id",
    "seo_title",
    "meta_description",
    "canonical_url",
    "noindex",
    "original_url",
    "original_slug",
)


def _apply(article: Article, data: dict[str, Any], refs: dict[str, Any]) -> None:
    for field in _SCALARS:
        if field in data:
            setattr(article, field, data[field])
    if "body" in data:
        article.body = validate_blocks(data["body"])
    if "author" in refs:
        article.author = refs["author"]
    if "primary_topic" in refs:
        article.primary_topic = refs["primary_topic"]
    if "secondary_topics" in refs:
        primary_id = article.primary_topic.id if article.primary_topic else None
        article.secondary_topics = [t for t in refs["secondary_topics"] if t.id != primary_id]
    if "tags" in refs:
        article.tags = refs["tags"]


def _snapshot(a: Article) -> dict[str, Any]:
    d = admin_detail(a)
    d.pop("can", None)
    d["body"] = f"{len(a.body or [])} blocks"
    return {
        k: v
        for k, v in d.items()
        if k
        not in {"updated_at", "featured_image", "author", "primary_topic", "reading_time_minutes"}
    }


def create_article(data: dict[str, Any], actor: User) -> Article:
    refs = _load_refs(data, None)
    article = Article(
        title=data["title"],
        slug=resolve_slug(Article, data.get("slug"), data["title"]),
        status="draft",
        source=data.get("source", "original"),
        body=[],
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    _apply(article, data, refs)
    db.session.add(article)
    db.session.flush()
    audit_service.record(
        "article.created",
        "article",
        article.id,
        actor=actor,
        details={"title": article.title, "slug": article.slug},
    )
    return article


def update_article(article: Article, data: dict[str, Any], actor: User) -> Article:
    require_capability(article, actor, "edit")
    before = _snapshot(article)
    if "slug" in data and data["slug"] != article.slug:
        if article.first_published_at is not None:
            raise ConflictError(
                "The slug cannot change after the article has been published.",
                details={"slug": ["Locked after first publication to keep URLs stable."]},
            )
        article.slug = resolve_slug(Article, data["slug"], article.title, exclude_id=article.id)
    refs = _load_refs(data, article)
    _apply(article, data, refs)
    article.updated_by_id = actor.id
    db.session.flush()
    changes = audit_service.changed_fields(before, _snapshot(article))
    if changes:
        # Changes by someone who cannot approve invalidate a pending or granted approval.
        if (
            article.review_status != "none"
            and P.ARTICLES_APPROVE.value not in effective_permissions(actor)
        ):
            article.review_status = "none"
            article.approved_at = article.approved_by_id = article.submitted_at = None
        audit_service.record("article.updated", "article", article.id, actor=actor, details=changes)
        if is_public(article):
            record_public_change("article", article.id, "published_article_updated", actor)
    return article


def publish_readiness(article: Article) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {}
    checks = {
        "title": article.title,
        "excerpt": article.excerpt,
        "body": article.body,
        "author_id": article.author_id,
        "primary_topic_id": article.primary_topic_id,
        "featured_image_id": article.featured_image_id,
    }
    for field, value in checks.items():
        if not value:
            problems[field] = ["Required before publishing."]
    if article.author and article.author.status != "active":
        problems["author_id"] = ["The author is archived."]
    if article.primary_topic and article.primary_topic.status == "archived":
        problems["primary_topic_id"] = ["The topic is archived."]
    return problems


def publish(article: Article, when: datetime | None, actor: User) -> Article:
    if article.status == "archived":
        raise ConflictError("Restore the article to a draft before publishing.")
    problems = publish_readiness(article)
    if problems:
        raise ValidationError("The article is not ready to publish.", details=problems)
    now = _now()
    if when is not None and when.tzinfo is None:
        raise ValidationError(details={"published_at": ["Include a timezone (UTC)."]})
    if when is not None and when > now + SCHEDULE_GRACE:
        article.status = "scheduled"
        article.published_at = when
        action = "article.scheduled"
    else:
        article.status = "published"
        article.published_at = when or now
        article.first_published_at = article.first_published_at or now
        action = "article.published"
        record_public_change("article", article.id, "article_published", actor)
    article.updated_by_id = actor.id
    audit_service.record(
        action,
        "article",
        article.id,
        actor=actor,
        details={"published_at": iso(article.published_at)},
    )
    return article


def unpublish(article: Article, actor: User) -> Article:
    if article.status not in ("published", "scheduled"):
        raise ConflictError("Only published or scheduled articles can be unpublished.")
    was_public = is_public(article)
    if article.status == "scheduled":
        article.published_at = None
    article.status = "draft"
    article.updated_by_id = actor.id
    audit_service.record("article.unpublished", "article", article.id, actor=actor)
    if was_public:
        record_public_change("article", article.id, "article_unpublished", actor)
    return article


def archive(article: Article, actor: User) -> Article:
    if article.status == "archived":
        raise ConflictError("The article is already archived.")
    was_public = is_public(article)
    if article.status == "scheduled":
        article.published_at = None
    article.status = "archived"
    article.updated_by_id = actor.id
    audit_service.record("article.archived", "article", article.id, actor=actor)
    if was_public:
        record_public_change("article", article.id, "article_archived", actor)
    return article


def restore(article: Article, actor: User) -> Article:
    if article.status != "archived":
        raise ConflictError("Only archived articles can be restored.")
    article.status = "draft"
    article.updated_by_id = actor.id
    audit_service.record("article.restored", "article", article.id, actor=actor)
    return article


def submit_for_review(article: Article, actor: User) -> Article:
    require_capability(article, actor, "submit")
    article.review_status = "submitted"
    article.submitted_at = _now()
    article.approved_at = article.approved_by_id = None
    audit_service.record("article.submitted", "article", article.id, actor=actor)
    return article


def approve(article: Article, actor: User) -> Article:
    require_capability(article, actor, "approve")
    article.review_status = "approved"
    article.approved_at = _now()
    article.approved_by_id = actor.id
    audit_service.record("article.approved", "article", article.id, actor=actor)
    return article


def delete_article(article: Article, actor: User) -> None:
    """Permanent deletion is limited to drafts that were never published (URLs stay stable)."""
    if not capabilities(article, actor)["delete"]:
        if P.ARTICLES_DELETE.value in effective_permissions(actor):
            raise ConflictError(
                "Only drafts that were never published can be deleted. Archive it instead."
            )
        raise ForbiddenError("You cannot delete this article.")
    audit_service.record(
        "article.deleted",
        "article",
        article.id,
        actor=actor,
        details={"title": article.title, "slug": article.slug},
    )
    db.session.delete(article)


def preview(article: Article) -> dict[str, Any]:
    data = public_article(article)
    if not article.featured_image_id:
        data["image"] = None
    return {"article": data, "related": [], "status": article.status}


def status_counts(user: User | None = None) -> dict[str, int]:
    stmt = select(Article.status, func.count(Article.id)).group_by(Article.status)
    if user is not None and (scope := scope_filter(user)) is not None:
        stmt = stmt.where(scope)
    rows = db.session.execute(stmt)
    counts = {s: 0 for s in ("draft", "scheduled", "published", "archived")}
    counts.update({status: n for status, n in rows})
    return counts
