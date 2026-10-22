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
from sqlalchemy import func, select

from ..extensions import db
from ..models import Article, ContentRevision, User
from .serializers import iso


def record_public_change(resource_type: str, resource_id: Any, reason: str, actor: User | None):
    db.session.add(
        ContentRevision(
            resource_type=resource_type,
            resource_id=None if resource_id is None else str(resource_id),
            reason=reason,
            user_id=actor.id if actor else None,
        )
    )


def _read_manifest() -> dict[str, Any] | None:
    path = Path(current_app.config["FRONTEND_BUILD_MANIFEST"])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status() -> dict[str, Any]:
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
    return {
        "last_build_at": iso(built_at),
        "build_manifest_found": manifest is not None,
        "latest_public_change_at": iso(latest),
        "rebuild_required": bool(latest and (built_at is None or latest > built_at)),
        "scheduled_due_count": due or 0,
        "rebuild_command": "./scripts/build-production.sh",
    }


def publish_due_scheduled(now: datetime | None = None) -> list[str]:
    """Promote scheduled articles whose publish time has passed (run via CLI/timer)."""
    now = now or datetime.now(UTC)
    due = db.session.scalars(
        select(Article).where(Article.status == "scheduled", Article.published_at <= now)
    ).all()
    for article in due:
        article.status = "published"
        record_public_change("article", article.id, "scheduled_published", None)
    return [a.slug for a in due]
