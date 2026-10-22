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
    display_order: Mapped[int] = mapped_column(default=0, nullable=False)

    menu: Mapped[NavigationMenu] = relationship(back_populates="items")


class Page(TimestampMixin, db.Model):
    __tablename__ = "pages"
    __table_args__ = (CheckConstraint(f"status IN {PAGE_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    noindex: Mapped[bool] = mapped_column(default=False, nullable=False)
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)

    sections: Mapped[list[PageSection]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="PageSection.display_order",
        lazy="selectin",
    )


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

    page: Mapped[Page] = relationship(back_populates="sections")
