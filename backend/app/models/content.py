from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

ARTICLE_STATUSES = ("draft", "scheduled", "published", "archived")
ARTICLE_SOURCES = ("sample", "original", "migrated")
REVIEW_STATUSES = ("none", "submitted", "approved")
AUTHOR_STATUSES = ("active", "archived")
TOPIC_STATUSES = ("active", "hidden", "archived")
MEDIA_VISIBILITY = ("public", "private")


article_topics = Table(
    "article_topics",
    db.metadata,
    Column("article_id", Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", Integer, ForeignKey("topics.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_article_topics_topic_id", "topic_id"),
)

article_tags = Table(
    "article_tags",
    db.metadata,
    Column("article_id", Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_article_tags_tag_id", "tag_id"),
)


class MediaAsset(db.Model):
    """Metadata for media files. Private assets never receive a public URL."""

    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(f"visibility IN {MEDIA_VISIBILITY}", name="visibility_valid"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Public static path ("/images/...") or an object-storage key for future uploads.
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    alt_text: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    @property
    def public_url(self) -> str | None:
        if self.visibility != "public":
            return None
        return self.storage_key if self.storage_key.startswith("/") else None

    def as_image(self) -> dict[str, Any] | None:
        url = self.public_url
        if not url:
            return None
        return {
            "src": url,
            "alt": self.alt_text,
            "width": self.width or 1600,
            "height": self.height or 1000,
        }


class Author(TimestampMixin, db.Model):
    __tablename__ = "authors"
    __table_args__ = (CheckConstraint(f"status IN {AUTHOR_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    profile_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    profile_image: Mapped[MediaAsset | None] = relationship()


class Topic(TimestampMixin, db.Model):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint(f"status IN {TOPIC_STATUSES}", name="status_valid"),
        Index("ix_topics_status_order", "status", "display_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    intro: Mapped[str] = mapped_column(Text, default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(40), default="sun", nullable=False)
    featured: Mapped[bool] = mapped_column(default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    featured_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(320), nullable=True)

    featured_image: Mapped[MediaAsset | None] = relationship()


class Tag(TimestampMixin, db.Model):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)


class Article(TimestampMixin, db.Model):
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(f"status IN {ARTICLE_STATUSES}", name="status_valid"),
        CheckConstraint(f"source IN {ARTICLE_SOURCES}", name="source_valid"),
        CheckConstraint(f"review_status IN {REVIEW_STATUSES}", name="review_status_valid"),
        CheckConstraint(
            "status NOT IN ('published', 'scheduled') OR published_at IS NOT NULL",
            name="published_at_required",
        ),
        Index("ix_articles_status_published_at", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    excerpt: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    body: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    featured_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("authors.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    primary_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    featured: Mapped[bool] = mapped_column(default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Editorial review workflow: none -> submitted -> approved (reset when content changes).
    review_status: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none", nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set the first time the article goes live; once set, the slug is locked.
    first_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # SEO
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    noindex: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Provenance / migration
    source: Mapped[str] = mapped_column(String(20), default="original", nullable=False)
    original_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    author: Mapped[Author | None] = relationship(lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    primary_topic: Mapped[Topic | None] = relationship(lazy="joined")
    featured_image: Mapped[MediaAsset | None] = relationship(foreign_keys=[featured_image_id])
    social_image: Mapped[MediaAsset | None] = relationship(foreign_keys=[social_image_id])
    secondary_topics: Mapped[list[Topic]] = relationship(secondary=article_topics, lazy="selectin")
    tags: Mapped[list[Tag]] = relationship(secondary=article_tags, lazy="selectin")


class ContentRevision(db.Model):
    """Append-only log of changes that affect the public site (drives rebuild status)."""

    __tablename__ = "content_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    changed_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
