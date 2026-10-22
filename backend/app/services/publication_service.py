"""Publication/rebuild contract.

The public site is prerendered at build time. Changes that affect public
pages are recorded as ContentRevision rows; the prerender step writes a
manifest with its generation time. Comparing the two tells administrators
whether a rebuild is required. API requests never run shell commands.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import func, select, update

from ..extensions import db
from ..models import Article, ContentRevision, User
from .serializers import iso


def record_public_change(resource_type: str, resource_id: Any, reason: str, actor: User | None):
    """Log a change that affects public pages and queue a (debounced) site rebuild."""
    from .publishing import request_build

    db.session.add(
        ContentRevision(
            resource_type=resource_type,
            resource_id=None if resource_id is None else str(resource_id),
            reason=reason,
            user_id=actor.id if actor else None,
        )
    )
    request_build(reason, actor)


def _manifest_path() -> Path:
    current = Path(current_app.config["PUBLISH_CURRENT_LINK"]) / "prerender-manifest.json"
    if current.is_file():
        return current
    return Path(current_app.config["FRONTEND_BUILD_MANIFEST"])


def _read_manifest() -> dict[str, Any] | None:
    try:
        return json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status() -> dict[str, Any]:
    from .publishing import summary

    latest = db.session.scalar(select(func.max(ContentRevision.changed_at)))
    manifest = _read_manifest()
    built_at = None
    if manifest and manifest.get("generatedAt"):
        try:
            built_at = datetime.fromisoformat(manifest["generatedAt"].replace("Z", "+00:00"))
        except ValueError:
            built_at = None
    now = datetime.now(UTC)
    due = db.session.scalar(
        select(func.count(Article.id)).where(
            Article.status == "scheduled", Article.published_at <= now
        )
    )
    from ..models import Page

    due += (
        db.session.scalar(
            select(func.count(Page.id)).where(
                Page.scheduled_at.is_not(None), Page.scheduled_at <= now
            )
        )
        or 0
    )
    jobs = summary()
    return {
        "last_build_at": iso(built_at),
        "build_manifest_found": manifest is not None,
        "indexing_enabled": bool(manifest.get("indexing")) if manifest else None,
        "latest_public_change_at": iso(latest),
        "rebuild_required": bool(latest and (built_at is None or latest > built_at)),
        "scheduled_due_count": due or 0,
        "rebuild_command": "./scripts/build-production.sh",
        "jobs": jobs,
    }


def publish_due_scheduled(now: datetime | None = None) -> dict[str, Any]:
    """Promote scheduled articles whose publish time has passed. Idempotent.

    Each article is promoted with a conditional UPDATE, so overlapping runs (timer
    plus worker) cannot publish the same article twice. Failures are recorded in
    the audit log and do not stop other articles.
    """
    from . import audit_service

    now = now or datetime.now(UTC)
    due = db.session.scalars(
        select(Article.id).where(Article.status == "scheduled", Article.published_at <= now)
    ).all()
    published, failed = [], []
    for article_id in due:
        try:
            with db.session.begin_nested():
                result = db.session.execute(
                    update(Article)
                    .where(Article.id == article_id, Article.status == "scheduled")
                    .values(status="published", lock_version=Article.lock_version + 1)
                )
                if result.rowcount != 1:
                    continue
                article = db.session.get(Article, article_id)
                db.session.refresh(article)
                if article.first_published_at is None:
                    article.first_published_at = article.published_at
                record_public_change("article", article.id, "scheduled_published", None)
                audit_service.record(
                    "article.published",
                    "article",
                    article.id,
                    details={"published_at": iso(article.published_at), "by": "scheduler"},
                )
                published.append(article.slug)
        except Exception as exc:  # keep going; the failure is visible in the audit log
            failed.append(article_id)
            audit_service.record(
                "scheduler.failed",
                "article",
                article_id,
                details={"error": type(exc).__name__},
            )
    pages = _publish_due_pages(now)
    rebuild = _visibility_boundaries_passed(now)
    return {
        "published": published + pages["published"],
        "failed": failed + pages["failed"],
        "boundary_rebuild": rebuild,
    }


def _publish_due_pages(now: datetime) -> dict[str, list]:
    from .admin.page_admin import publish_due

    return publish_due(now)


BOUNDARY_MARKER = "_scheduler.boundaries_checked_at"


def _visibility_boundaries_passed(now: datetime) -> bool:
    """Queue one rebuild when a section window or announcement starts or ends.

    The last check time is stored outside the settings registry (never exposed in
    the admin). The first run only records the time.
    """
    from ..models import SiteSetting
    from .admin.announcement_admin import boundaries as announcement_boundaries
    from .page_render import visibility_boundaries
    from .publishing import request_build

    marker = db.session.get(SiteSetting, BOUNDARY_MARKER)
    last = None
    if marker is not None and isinstance(marker.value, str):
        try:
            last = datetime.fromisoformat(marker.value)
        except ValueError:
            last = None
    if marker is None:
        marker = SiteSetting(key=BOUNDARY_MARKER)
        db.session.add(marker)
    marker.value = now.isoformat()
    if last is None:
        return False
    crossed = any(last < t <= now for t in visibility_boundaries() + announcement_boundaries())
    if crossed:
        request_build("scheduled_visibility", None)
    return crossed
