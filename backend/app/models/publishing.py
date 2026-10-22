"""Redirects and static-site publishing jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .types import JSONType, UTCDateTime, utcnow

REDIRECT_CODES = (301, 302, 307, 308)
REDIRECT_ORIGINS = ("manual", "slug_change", "import")
JOB_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")


class Redirect(db.Model):
    """CMS-managed HTTP redirect (served by Nginx from the generated map file)."""

    __tablename__ = "redirects"
    __table_args__ = (
        CheckConstraint(f"status_code IN {REDIRECT_CODES}", name="status_code_valid"),
        CheckConstraint(f"origin IN {REDIRECT_ORIGINS}", name="origin_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    destination: Mapped[str] = mapped_column(String(1000), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=301, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class PublishJob(db.Model):
    """A durable request to rebuild and release the static public site."""

    __tablename__ = "publish_jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="status_valid"),
        Index("ix_publish_jobs_status_not_before", "status", "not_before"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Short machine reasons collected while the job waited (deduplicated bursts).
    reasons: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="content", nullable=False)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    # Debounce: the job is not started before this time; new edits push it back (capped).
    not_before: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    worker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Sanitised diagnostics only (no secrets, no absolute paths).
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    log_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    requested_by = relationship("User", lazy="joined")
