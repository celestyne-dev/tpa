"""Editorial article management and publication workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms.blocks import blocks_word_count, media_ids, related_ids, validate_blocks
from ...extensions import db
from ...models import Article, Author, MediaAsset, Tag, Topic, User
from ...utils.errors import APIError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from .. import audit_service, redirect_service
from ..publication_service import record_public_change
from ..serializers import iso, media_dict, public_article, reading_time
from . import revisions
from .common import paginate, resolve_slug
from .media_admin import validate_media_refs


class EditConflict(APIError):
    status_code = 409
    code = "edit_conflict"
    message = "This article was changed by someone else since you opened it."


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
        "publish_changes": P.ARTICLES_PUBLISH.value in perms
        and status == "published"
        and bool(article.pending_changes),
        "discard_changes": can_edit and bool(article.pending_changes),
        "view_revisions": P.ARTICLES_VIEW_REVISIONS.value in perms,
        "restore_revision": can_edit and P.ARTICLES_RESTORE_REVISIONS.value in perms,
        "preview": P.ARTICLES_PREVIEW.value in perms,
        # Published URLs only change with a redirect, by someone responsible for SEO.
        "edit_slug": can_edit
        and (article.first_published_at is None or P.SEO_MANAGE.value in perms),
        "edit_indexing": can_edit and P.SEO_MANAGE.value in perms,
        # Saves to a live article go straight out only for publishers.
        "save_live": P.ARTICLES_PUBLISH.value in perms,
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
        "has_pending_changes": bool(a.pending_changes),
    }


def admin_detail(a: Article, user: User | None = None) -> dict[str, Any]:
    """Editor payload. Content fields are the working copy (live + unpublished changes)."""
    w = revisions.working_values(a)
    featured = (
        db.session.get(MediaAsset, w["featured_image_id"]) if w["featured_image_id"] else None
    )
    social = db.session.get(MediaAsset, w["social_image_id"]) if w["social_image_id"] else None
    can = capabilities(a, user) if user else None
    pending_by = db.session.get(User, a.pending_by_id) if a.pending_by_id else None
    return {
        **admin_summary(a),
        **{k: w[k] for k in revisions.CONTENT_FIELDS if k not in ("slug",)},
        "slug": w["slug"],
        "can": can,
        "submitted_at": iso(a.submitted_at),
        "approved_at": iso(a.approved_at),
        "featured_image": media_dict(featured),
        "social_image": media_dict(social),
        "first_published_at": iso(a.first_published_at),
        "slug_locked": a.first_published_at is not None and not (can or {}).get("edit_slug"),
        "created_at": iso(a.created_at),
        "lock_version": a.lock_version,
        "pending_updated_at": iso(a.pending_updated_at),
        "pending_by": {"id": pending_by.id, "display_name": pending_by.display_name}
        if pending_by
        else None,
        "pending_fields": sorted(a.pending_changes or {}),
        "word_count": blocks_word_count(w["body"] or []),
        "reading_time_minutes": reading_time(w["body"] or []),
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
    if args.get("has_pending"):
        stmt = stmt.where(Article.pending_changes.is_not(None))
    if args.get("mine"):
        stmt = stmt.where(Article.created_by_id == user.id)
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
    already = set()
    if article is not None:
        live = revisions.working_values(article)
        already = {live.get("featured_image_id"), live.get("social_image_id")} | media_ids(
            live.get("body") or []
        )
    for field in ("featured_image_id", "social_image_id"):
        if field in data and data[field]:
            asset = db.session.get(MediaAsset, data[field])
            if asset is None:
                errors[field] = ["Media asset not found."]
            elif asset.visibility != "public" or not asset.mime_type.startswith("image/"):
                errors[field] = ["Choose a public image."]
            elif asset.status == "archived" and asset.id not in already:
                errors[field] = ["This image is archived. Restore it in the media library first."]
    if errors:
        raise ValidationError(details=errors)
    if "body" in data:
        # Images already used by this article may stay even if archived since.
        validate_media_refs(media_ids(data["body"]), allow_archived=already)
        missing = related_ids(data["body"]) - set(
            db.session.scalars(select(Article.id).where(Article.id.in_(related_ids(data["body"]))))
        )
        if missing:
            raise ValidationError(details={"body": ["A related article no longer exists."]})
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
    "social_title",
    "social_description",
    "canonical_url",
    "noindex",
    "original_url",
    "original_slug",
)
INDEXING_FIELDS = ("canonical_url", "noindex")


def _apply(article: Article, data: dict[str, Any], refs: dict[str, Any]) -> None:
    for field in _SCALARS:
        if field in data:
            setattr(article, field, data[field])
    if "body" in data:
        article.body = data["body"]
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
    d = revisions.content_values(a)
    d["body"] = f"{len(a.body or [])} blocks"
    return d


def _clean(article: Article | None, data: dict[str, Any], actor: User) -> dict[str, Any]:
    """Validate a write payload and normalise it to content values (ids, cleaned body)."""
    data = dict(data)
    if "body" in data:
        data["body"] = validate_blocks(data["body"])
    if article is not None:
        can = capabilities(article, actor)
        current = revisions.working_values(article)
        for field in INDEXING_FIELDS:
            if field in data and data[field] != current.get(field) and not can["edit_indexing"]:
                raise ForbiddenError(
                    "Changing the canonical URL or indexing needs the SEO permission.",
                    details={field: ["Requires seo.manage."]},
                )
    return data


def _check_lock(article: Article, lock_version: int | None) -> None:
    if lock_version is not None and lock_version != article.lock_version:
        editor = db.session.get(User, article.updated_by_id) if article.updated_by_id else None
        raise EditConflict(
            details={
                "lock_version": article.lock_version,
                "updated_at": iso(article.updated_at),
                "updated_by": editor.display_name if editor else None,
            }
        )


def _reset_review_if_needed(article: Article, actor: User) -> None:
    # Changes by someone who cannot approve invalidate a pending or granted approval.
    if article.review_status != "none" and P.ARTICLES_APPROVE.value not in effective_permissions(
        actor
    ):
        article.review_status = "none"
        article.approved_at = article.approved_by_id = article.submitted_at = None


def _change_slug(article: Article, requested: str | None, actor: User) -> None:
    new_slug = resolve_slug(Article, requested, article.title, exclude_id=article.id)
    if new_slug == article.slug:
        return
    old_slug = article.slug
    article.slug = new_slug
    if article.first_published_at is not None:
        redirect_service.create_slug_redirect(
            f"/articles/{old_slug}", f"/articles/{new_slug}", actor
        )


def create_article(data: dict[str, Any], actor: User) -> Article:
    data = _clean(None, data, actor)
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
    revisions.record(article, actor, "manual", "Created")
    audit_service.record(
        "article.created",
        "article",
        article.id,
        actor=actor,
        details={"title": article.title, "slug": article.slug},
    )
    return article


def update_article(
    article: Article,
    data: dict[str, Any],
    actor: User,
    *,
    mode: str = "save",
    lock_version: int | None = None,
    summary: str | None = None,
) -> str:
    """Save edits. Returns "saved" (applied) or "pending" (kept for a publisher).

    Published articles are never changed by autosave, and edits by people who
    cannot publish are kept as pending changes, so the live page only changes
    when a publisher publishes them.
    """
    require_capability(article, actor, "edit")
    _check_lock(article, lock_version)
    data = _clean(article, data, actor)
    can = capabilities(article, actor)
    if (
        "slug" in data
        and data["slug"]
        and data["slug"] != revisions.working_values(article)["slug"]
    ) and not can["edit_slug"]:
        raise ConflictError(
            "The slug cannot change after the article has been published.",
            details={"slug": ["Locked after first publication to keep URLs stable."]},
        )
    refs = _load_refs(data, article)
    before_working = revisions.working_values(article)

    if article.status == "published" and (mode == "autosave" or not can["save_live"]):
        return _save_pending(article, data, actor, mode, summary, before_working)

    before = _snapshot(article)
    pending = article.pending_changes or {}
    if pending:
        # Applying a save to a live article also applies the earlier unpublished changes.
        merged = {**pending, **data}
        refs = {**_load_refs({k: v for k, v in pending.items() if k not in data}, article), **refs}
        data = merged
        article.pending_changes = None
        article.pending_updated_at = article.pending_by_id = None
    if "slug" in data and data["slug"]:
        _change_slug(article, data["slug"], actor)
    _apply(article, data, refs)
    article.updated_by_id = actor.id
    article.lock_version += 1
    db.session.flush()
    changes = audit_service.changed_fields(before, _snapshot(article))
    if changes:
        _reset_review_if_needed(article, actor)
        text = summary or revisions.summarise(before_working, revisions.working_values(article))
        if mode == "autosave":
            revisions.record(article, actor, "autosave", text)
        else:
            revisions.record(article, actor, "publish" if is_public(article) else "manual", text)
            audit_service.record(
                "article.updated", "article", article.id, actor=actor, details=changes
            )
        if is_public(article):
            record_public_change("article", article.id, "published_article_updated", actor)
    return "saved"


def _save_pending(article, data, actor, mode, summary, before_working) -> str:
    live = revisions.content_values(article)
    merged = {**(article.pending_changes or {})}
    for key, value in data.items():
        if key not in revisions.CONTENT_FIELDS:
            continue
        merged[key] = value
    # Keep only real differences from the live article.
    merged = {k: v for k, v in merged.items() if live.get(k) != v}
    if merged == (article.pending_changes or {}):
        return "pending" if merged else "saved"
    article.pending_changes = merged or None
    article.pending_updated_at = datetime.now(UTC) if merged else None
    article.pending_by_id = actor.id if merged else None
    article.lock_version += 1
    db.session.flush()
    text = summary or revisions.summarise(before_working, revisions.working_values(article))
    revisions.record(article, actor, "autosave" if mode == "autosave" else "manual", text)
    if mode != "autosave":
        _reset_review_if_needed(article, actor)
        audit_service.record(
            "article.changes_saved",
            "article",
            article.id,
            actor=actor,
            details={"fields": sorted(merged)},
        )
    return "pending" if merged else "saved"


def publish_changes(article: Article, actor: User, lock_version: int | None = None) -> Article:
    require_capability(article, actor, "publish_changes")
    _check_lock(article, lock_version)
    pending = dict(article.pending_changes or {})
    before_working = revisions.content_values(article)
    article.pending_changes = None
    article.pending_updated_at = article.pending_by_id = None
    refs = _load_refs(pending, article)
    if pending.get("slug"):
        _change_slug(article, pending["slug"], actor)
    problems = None
    _apply(article, pending, refs)
    problems = publish_readiness(article)
    if problems:
        raise ValidationError("The changes leave the article incomplete.", details=problems)
    article.updated_by_id = actor.id
    article.lock_version += 1
    db.session.flush()
    revisions.record(
        article,
        actor,
        "publish",
        "Published changes: "
        + revisions.summarise(before_working, revisions.content_values(article)).removeprefix(
            "Changed "
        ),
    )
    audit_service.record(
        "article.changes_published",
        "article",
        article.id,
        actor=actor,
        details={"fields": sorted(pending)},
    )
    record_public_change("article", article.id, "published_article_updated", actor)
    return article


def discard_changes(article: Article, actor: User) -> Article:
    require_capability(article, actor, "discard_changes")
    fields = sorted(article.pending_changes or {})
    article.pending_changes = None
    article.pending_updated_at = article.pending_by_id = None
    article.lock_version += 1
    audit_service.record(
        "article.changes_discarded", "article", article.id, actor=actor, details={"fields": fields}
    )
    return article


def restore_revision(
    article: Article, revision_id: int, actor: User, lock_version: int | None = None
) -> str:
    """Bring back an older revision's content as the working copy.

    For a live article the restored content becomes pending changes (it goes
    live only when published), otherwise it is saved directly.
    """
    require_capability(article, actor, "restore_revision")
    revision = revisions.get(article, revision_id)
    snap = revision.snapshot or {}
    can = capabilities(article, actor)
    data = {k: snap[k] for k in revisions.CONTENT_FIELDS if k in snap}
    if not can["edit_indexing"]:
        for field in INDEXING_FIELDS:
            data.pop(field, None)
    if not can["edit_slug"]:
        data.pop("slug", None)
    summary = f"Restored revision #{revision.number}"
    if article.status == "published":
        _check_lock(article, lock_version)
        data["body"] = validate_blocks(data.get("body") or [])
        _load_refs(data, article)
        result = _save_pending(
            article, data, actor, "save", summary, revisions.working_values(article)
        )
    else:
        result = update_article(
            article, data, actor, mode="save", lock_version=lock_version, summary=summary
        )
    revisions.record(article, actor, "restore", summary)
    audit_service.record(
        "article.revision_restored",
        "article",
        article.id,
        actor=actor,
        details={"revision": revision.number, "result": result},
    )
    return result


def preview_article(article: Article) -> dict[str, Any]:
    """Public rendering of the working copy, built on a detached object (never saved)."""
    w = revisions.working_values(article)
    draft = Article(
        id=article.id,
        title=w["title"],
        slug=w["slug"],
        subtitle=w["subtitle"],
        excerpt=w["excerpt"] or "",
        body=w["body"] or [],
        status=article.status,
        featured=w["featured"],
        published_at=article.published_at,
        first_published_at=article.first_published_at,
        source=article.source,
        seo_title=w["seo_title"],
        meta_description=w["meta_description"],
        canonical_url=w["canonical_url"],
        noindex=w["noindex"],
        social_title=w["social_title"],
        social_description=w["social_description"],
    )
    draft.updated_at = article.updated_at
    draft.featured_image = (
        db.session.get(MediaAsset, w["featured_image_id"]) if w["featured_image_id"] else None
    )
    draft.social_image = (
        db.session.get(MediaAsset, w["social_image_id"]) if w["social_image_id"] else None
    )
    draft.author = db.session.get(Author, w["author_id"]) if w["author_id"] else None
    draft.primary_topic = (
        db.session.get(Topic, w["primary_topic_id"]) if w["primary_topic_id"] else None
    )
    ids = w["secondary_topic_ids"] or []
    draft.secondary_topics = (
        db.session.scalars(select(Topic).where(Topic.id.in_(ids))).all() if ids else []
    )
    tag_ids = w["tag_ids"] or []
    draft.tags = db.session.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all() if tag_ids else []
    if draft in db.session:
        db.session.expunge(draft)
    data = public_article(draft)
    if not draft.featured_image:
        data["image"] = None
    return {
        "article": data,
        "related": [],
        "status": article.status,
        "has_pending_changes": bool(article.pending_changes),
    }


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


def status_counts(user: User | None = None) -> dict[str, int]:
    stmt = select(Article.status, func.count(Article.id)).group_by(Article.status)
    if user is not None and (scope := scope_filter(user)) is not None:
        stmt = stmt.where(scope)
    rows = db.session.execute(stmt)
    counts = {s: 0 for s in ("draft", "scheduled", "published", "archived")}
    counts.update({status: n for status, n in rows})
    return counts
