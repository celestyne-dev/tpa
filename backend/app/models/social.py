"""Social publishing: connected Pinterest / Instagram accounts, outgoing posts and images
imported from Instagram into the Media Library.

Tokens are stored encrypted (``services.social.crypto``); nothing here holds a usable
credential in plain text. A post is published only by an explicit administrator action
(publish now or a schedule they set); publishing on TPA never posts anything by itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .types import JSONType, UTCDateTime, utcnow

SOCIAL_PLATFORMS = ("pinterest", "instagram")
ACCOUNT_STATUSES = ("connected", "expired", "error")
# scheduled → publishing → published | failed (retried by an administrator) | cancelled.
# "checking": an attempt whose outcome is unknown (e.g. a timeout); it is resolved by looking
# for the post on the platform before anything is sent again (never a duplicate).
POST_STATUSES = ("scheduled", "publishing", "checking", "published", "failed", "cancelled")


class SocialAccount(db.Model):
    """One connected account per platform."""

    __tablename__ = "social_accounts"
    __table_args__ = (
        CheckConstraint(f"platform IN {SOCIAL_PLATFORMS}", name="platform_valid"),
        CheckConstraint(f"status IN {ACCOUNT_STATUSES}", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="connected", nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    connected_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SocialPost(db.Model):
    """A Pin or an Instagram feed post made from a Media Library image."""

    __tablename__ = "social_posts"
    __table_args__ = (
        CheckConstraint(f"platform IN {SOCIAL_PLATFORMS}", name="platform_valid"),
        CheckConstraint(f"status IN {POST_STATUSES}", name="status_valid"),
        Index("ix_social_posts_status_scheduled_at", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The article or quote collection the image belongs to (its canonical URL is the Pin link).
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)  # description / caption
    alt_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    destination_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    board_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    board_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Platform state between steps (e.g. the Instagram container id).
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    media_asset = relationship("MediaAsset")
    article = relationship("Article")


class SocialImport(db.Model):
    """An image imported from the connected Instagram account (one per external media id)."""

    __tablename__ = "social_imports"
    __table_args__ = (
        CheckConstraint(f"platform IN {SOCIAL_PLATFORMS}", name="platform_valid"),
        db.UniqueConstraint("platform", "external_id", name="uq_social_imports_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    media_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    permalink: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # The administrator confirmed the image is the account's own and suitable for TPA.
    ownership_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imported_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
