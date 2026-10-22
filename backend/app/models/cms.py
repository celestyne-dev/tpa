from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

PAGE_STATUSES = ("draft", "published", "archived")
LINK_TYPES = ("internal", "external", "heading")
NAV_VISIBILITY = ("all", "desktop", "mobile")
ANNOUNCEMENT_VARIANTS = ("sage", "gold", "charcoal", "ivory")
ANNOUNCEMENT_TARGETS = ("all", "home", "paths")


class SiteSetting(db.Model):
    """One validated value per registered key (see app/cms/settings_registry.py)."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NavigationMenu(TimestampMixin, db.Model):
    __tablename__ = "navigation_menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    items: Mapped[list[NavigationItem]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        order_by="NavigationItem.display_order",
        lazy="selectin",
    )


class NavigationItem(db.Model):
    __tablename__ = "navigation_items"
    __table_args__ = (
        CheckConstraint(f"link_type IN {LINK_TYPES}", name="link_type_valid"),
        Index("ix_navigation_items_menu_order", "menu_id", "display_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("navigation_menus.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("navigation_items.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    open_in_new_tab: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_visible: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Header/mobile targeting: all, desktop (desktop header only) or mobile (menu panel only).
    visibility: Mapped[str] = mapped_column(String(10), default="all", nullable=False)
    display_order: Mapped[int] = mapped_column(default=0, nullable=False)

    menu: Mapped[NavigationMenu] = relationship(back_populates="items")


class Page(TimestampMixin, db.Model):
    """A CMS page. Rows in ``page_sections`` are the working draft; the public site
    only ever renders ``published_snapshot`` (written by Publish)."""

    __tablename__ = "pages"
    __table_args__ = (
        CheckConstraint(f"status IN {PAGE_STATUSES}", name="status_valid"),
        Index("uq_pages_path", "path", unique=True),
        Index("uq_pages_published_path", "published_path", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    noindex: Mapped[bool] = mapped_column(default=False, nullable=False)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)

    # Batch 04: page builder
    template: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("pages.id", ondelete="SET NULL"), nullable=True
    )
    # Draft URL path and the path currently live on the website.
    path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    published_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    social_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    social_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    published_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Revision holding the snapshot that will be published at scheduled_at.
    scheduled_revision_id: Mapped[int | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    draft_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    sections: Mapped[list[PageSection]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="PageSection.display_order",
        lazy="selectin",
    )
    parent: Mapped[Page | None] = relationship(remote_side="Page.id", foreign_keys=[parent_id])
    social_image = relationship("MediaAsset", foreign_keys=[social_image_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    published_by = relationship("User", foreign_keys=[published_by_id])


class PageSection(TimestampMixin, db.Model):
    __tablename__ = "page_sections"
    __table_args__ = (
        UniqueConstraint("page_id", "key", name="uq_page_sections_page_key"),
        Index("ix_page_sections_page_order", "page_id", "display_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    # Stable identifier within the page (e.g. "hero"), used by renderers and seeds.
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    section_type: Mapped[str] = mapped_column(String(40), nullable=False)
    variant: Mapped[str] = mapped_column(String(40), default="default", nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_visible: Mapped[bool] = mapped_column(default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(default=0, nullable=False)
    # Batch 04: internal name, approved design presets, visibility rules, shared sections.
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    design: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    visibility: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    reusable_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("reusable_sections.id", ondelete="RESTRICT"), nullable=True
    )

    page: Mapped[Page] = relationship(back_populates="sections")
    reusable = relationship("ReusableSection")


class PageRevision(db.Model):
    """Snapshots of a page: every publish, scheduled publish and pre-restore backup."""

    __tablename__ = "page_revisions"
    __table_args__ = (UniqueConstraint("page_id", "number", name="uq_page_revisions_page_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_by = relationship("User")


class ReusableSection(TimestampMixin, db.Model):
    """A shared section edited once and shown on every page that links to it."""

    __tablename__ = "reusable_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    section_type: Mapped[str] = mapped_column(String(40), nullable=False)
    variant: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    design: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by = relationship("User")


class GlobalCta(TimestampMixin, db.Model):
    """A reusable call to action (label + link) referenced by sections."""

    __tablename__ = "global_ctas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    style: Mapped[str] = mapped_column(String(20), default="primary", nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Announcement(TimestampMixin, db.Model):
    """A slim, accessible site-wide banner (never a popup)."""

    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(f"variant IN {ANNOUNCEMENT_VARIANTS}", name="announcement_variant_valid"),
        CheckConstraint(f"target IN {ANNOUNCEMENT_TARGETS}", name="announcement_target_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(240), nullable=False)
    cta_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    variant: Mapped[str] = mapped_column(String(20), default="sage", nullable=False)
    target: Mapped[str] = mapped_column(String(20), default="all", nullable=False)
    target_paths: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_dismissible: Mapped[bool] = mapped_column(default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(default=0, nullable=False)
    # Bumped on every change so a reader who dismissed an old version sees the new one.
    revision: Mapped[int] = mapped_column(default=1, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
