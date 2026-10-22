"""Article revision history.

Every manual save, publication and restoration creates a numbered revision
with a full content snapshot. Autosaves are coalesced: consecutive autosaves by
the same editor within AUTOSAVE_WINDOW update one revision, and at most
MAX_AUTOSAVES autosave revisions are kept per article, so typing never creates
an unbounded history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import Article, ArticleRevision, User
from ...utils.errors import NotFoundError
from ..serializers import iso

AUTOSAVE_WINDOW = timedelta(minutes=10)
MAX_AUTOSAVES = 20

CONTENT_FIELDS = (
    "title",
    "subtitle",
    "excerpt",
    "body",
    "slug",
    "author_id",
    "primary_topic_id",
    "secondary_topic_ids",
    "tag_ids",
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
FIELD_LABELS = {
    "title": "title",
    "subtitle": "subtitle",
    "excerpt": "excerpt",
    "body": "content",
    "slug": "URL slug",
    "author_id": "author",
    "primary_topic_id": "primary topic",
    "secondary_topic_ids": "topics",
    "tag_ids": "tags",
    "featured": "featured flag",
    "featured_image_id": "featured image",
    "social_image_id": "social image",
    "seo_title": "SEO title",
    "meta_description": "meta description",
    "social_title": "social title",
    "social_description": "social description",
    "canonical_url": "canonical URL",
    "noindex": "indexing",
    "original_url": "original URL",
    "original_slug": "original slug",
}


def content_values(article: Article) -> dict[str, Any]:
    values = {f: getattr(article, f) for f in CONTENT_FIELDS if hasattr(Article, f)}
    values["body"] = list(article.body or [])
    values["secondary_topic_ids"] = sorted(t.id for t in article.secondary_topics)
    values["tag_ids"] = sorted(t.id for t in article.tags)
    return values


def working_values(article: Article) -> dict[str, Any]:
    """The editor's view: live values overlaid with unpublished changes."""
    return {**content_values(article), **(article.pending_changes or {})}


def snapshot(article: Article) -> dict[str, Any]:
    return {
        **working_values(article),
        "status": article.status,
        "published_at": iso(article.published_at),
    }


def summarise(before: dict[str, Any], after: dict[str, Any]) -> str:
    changed = [FIELD_LABELS[f] for f in CONTENT_FIELDS if before.get(f) != after.get(f)]
    if not changed:
        return "No content changes"
    if len(changed) > 4:
        return f"Changed {', '.join(changed[:4])} and {len(changed) - 4} more"
    return "Changed " + ", ".join(changed)


def _next_number(article_id: int) -> int:
    current = db.session.scalar(
        select(func.max(ArticleRevision.number)).where(ArticleRevision.article_id == article_id)
    )
    return (current or 0) + 1


def latest(article_id: int) -> ArticleRevision | None:
    return db.session.scalar(
        select(ArticleRevision)
        .where(ArticleRevision.article_id == article_id)
        .order_by(ArticleRevision.number.desc())
        .limit(1)
    )


def record(article: Article, actor: User | None, kind: str, summary: str = "") -> ArticleRevision:
    snap = snapshot(article)
    now = datetime.now(UTC)
    last = latest(article.id)
    if (
        kind == "autosave"
        and last is not None
        and last.kind == "autosave"
        and last.editor_id == (actor.id if actor else None)
        and now - last.updated_at <= AUTOSAVE_WINDOW
    ):
        last.snapshot = snap
        last.summary = summary or last.summary
        last.updated_at = now
        return last
    if last is not None and kind in ("manual", "autosave") and last.snapshot == snap:
        return last  # nothing changed since the previous revision
    revision = ArticleRevision(
        article_id=article.id,
        number=_next_number(article.id),
        kind=kind,
        summary=(summary or "")[:300],
        snapshot=snap,
        editor_id=actor.id if actor else None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(revision)
    db.session.flush()
    if kind == "autosave":
        _trim_autosaves(article.id)
    return revision


def _trim_autosaves(article_id: int) -> None:
    autosaves = db.session.scalars(
        select(ArticleRevision)
        .where(ArticleRevision.article_id == article_id, ArticleRevision.kind == "autosave")
        .order_by(ArticleRevision.number.desc())
        .offset(MAX_AUTOSAVES)
    ).all()
    for old in autosaves:
        db.session.delete(old)


def revision_summary(r: ArticleRevision) -> dict[str, Any]:
    return {
        "id": r.id,
        "number": r.number,
        "kind": r.kind,
        "summary": r.summary,
        "editor": {"id": r.editor.id, "display_name": r.editor.display_name} if r.editor else None,
        "created_at": iso(r.created_at),
        "updated_at": iso(r.updated_at),
        "title": (r.snapshot or {}).get("title"),
        "status": (r.snapshot or {}).get("status"),
    }


def list_for(article: Article) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(ArticleRevision)
        .where(ArticleRevision.article_id == article.id)
        .order_by(ArticleRevision.number.desc())
    ).all()
    return [revision_summary(r) for r in rows]


def get(article: Article, revision_id: int) -> ArticleRevision:
    r = db.session.get(ArticleRevision, revision_id)
    if r is None or r.article_id != article.id:
        raise NotFoundError("Revision not found.")
    return r


def _block_label(block: dict[str, Any]) -> str:
    text = block.get("text") or block.get("title") or block.get("label") or block.get("caption")
    kind = block.get("type", "block")
    return f"{kind}: {text[:80]}" if isinstance(text, str) and text else kind


def compare(a: ArticleRevision, b: ArticleRevision) -> dict[str, Any]:
    """Field-level differences from revision a (older) to revision b (newer)."""
    sa, sb = a.snapshot or {}, b.snapshot or {}
    fields = []
    for field in (*CONTENT_FIELDS, "status", "published_at"):
        if field == "body" or sa.get(field) == sb.get(field):
            continue
        fields.append(
            {
                "field": field,
                "label": FIELD_LABELS.get(field, field.replace("_", " ")),
                "from": sa.get(field),
                "to": sb.get(field),
            }
        )
    body_a, body_b = sa.get("body") or [], sb.get("body") or []
    blocks = []
    for index in range(max(len(body_a), len(body_b))):
        old = body_a[index] if index < len(body_a) else None
        new = body_b[index] if index < len(body_b) else None
        if old == new:
            continue
        change = "changed" if old and new else ("added" if new else "removed")
        blocks.append(
            {
                "index": index,
                "change": change,
                "from": _block_label(old) if old else None,
                "to": _block_label(new) if new else None,
                "from_block": old,
                "to_block": new,
            }
        )
    return {
        "from": revision_summary(a),
        "to": revision_summary(b),
        "fields": fields,
        "blocks": blocks,
    }
