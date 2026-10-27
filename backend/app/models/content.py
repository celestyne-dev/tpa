from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
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
MEDIA_STATUSES = ("active", "archived")
REVISION_KINDS = ("manual", "autosave", "restore", "publish", "system")


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
        CheckConstraint(f"status IN {MEDIA_STATUSES}", name="status_valid"),
        Index("uq_media_assets_public_id", "public_id", unique=True),
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

    # ---- Batch 03: uploaded, optimised images -------------------------------------
    # Stable, random identifier used in storage keys (never the uploaded file name).
    # Legacy records (static /images/... files) have no public_id and no variants.
    public_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    caption: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    credit: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False
    )
    checksum: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Retained source file in private storage (never served publicly).
    original_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    focal_x: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5", nullable=False)
    focal_y: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    has_alpha: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    dominant_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Batch 08: library category for filtering (see media_admin.MEDIA_CATEGORIES).
    category: Mapped[str] = mapped_column(String(40), default="general", nullable=False)

    variants: Mapped[list[MediaVariant]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MediaVariant.width",
    )

    @property
    def is_managed(self) -> bool:
        return self.public_id is not None

    def current_variants(self, preset: str | None = None) -> list[MediaVariant]:
        return [
            v
            for v in self.variants
            if v.superseded_at is None and (preset is None or v.preset == preset)
        ]

    @property
    def public_url(self) -> str | None:
        if self.visibility != "public":
            return None
        if self.is_managed:
            from ..storage import public_url  # local import: avoids a models -> app cycle

            return public_url(self.storage_key)
        return self.storage_key if self.storage_key.startswith("/") else None

    def as_image(self, preset: str = "responsive") -> dict[str, Any] | None:
        """Public image shape: fallback src plus responsive sources when available."""
        url = self.public_url
        if not url:
            return None
        image: dict[str, Any] = {
            "src": url,
            "alt": self.alt_text,
            "width": self.width or 1600,
            "height": self.height or 1000,
        }
        if self.is_managed:
            from ..storage import public_url

            variants = self.current_variants(preset) or self.current_variants("responsive")
            sources: dict[str, list[str]] = {}
            for v in variants:
                sources.setdefault(v.format, []).append(f"{public_url(v.storage_key)} {v.width}w")
            fallback = [v for v in variants if v.format in ("jpeg", "png")]
            if fallback:
                largest = max(fallback, key=lambda v: v.width if v.width <= 1280 else 0)
                image["src"] = public_url(largest.storage_key)
            image["srcset"] = ", ".join(sources.get("jpeg") or sources.get("png") or [])
            image["sources"] = {
                f"image/{fmt}": ", ".join(entries)
                for fmt, entries in sources.items()
                if fmt in ("avif", "webp")
            }
            if preset != "responsive" and variants:
                image["width"], image["height"] = variants[-1].width, variants[-1].height
            if self.caption:
                image["caption"] = self.caption
            if self.credit:
                image["credit"] = self.credit
            if self.dominant_color:
                image["placeholder"] = self.dominant_color
            image["focal"] = [round(self.focal_x, 3), round(self.focal_y, 3)]
        return image


class MediaVariant(db.Model):
    """One optimised derivative (format x size) of a media asset."""

    __tablename__ = "media_variants"
    __table_args__ = (Index("ix_media_variants_asset_current", "asset_id", "superseded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    preset: Mapped[str] = mapped_column(String(40), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    # Set when a replacement or focal-point change supersedes this file. The file is
    # kept until `flask media prune` so already-built pages keep working.
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    asset: Mapped[MediaAsset] = relationship(back_populates="variants")


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
    # Only authors marked as real people produce schema.org Person data; editorial
    # bylines ("TPA Editorial") stay attributed to the organisation.
    is_person: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

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
    social_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    social_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Optimistic locking: every write increments it; clients send the version they edited.
    lock_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    # Unpublished edits to a published article (autosave, or saves by people who
    # cannot publish). The live article stays untouched until they are published.
    pending_changes: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    pending_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    pending_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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


class ArticleRevision(db.Model):
    """Versioned snapshot of an article's editable content."""

    __tablename__ = "article_revisions"
    __table_args__ = (
        UniqueConstraint("article_id", "number", name="uq_article_revisions_article_number"),
        CheckConstraint(f"kind IN {REVISION_KINDS}", name="kind_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    editor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    editor = relationship("User", lazy="joined")


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
