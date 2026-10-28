"""First-party website analytics (Batch 11.1).

- ``analytics_page_views``: one row per counted page view, kept for
  ``ANALYTICS_RAW_RETENTION_DAYS``. No IP address, user agent, cookie, account id or
  query string is stored: only the normalised path, page type, content id, traffic
  source (referrer *host* only), allow-listed UTM values and a visitor hash that is
  salted with a random per-day salt (deleted after the day), so it cannot be linked
  across days or reversed.
- ``analytics_daily_pages`` / ``analytics_daily_sources``: per-day rollups kept for
  ``ANALYTICS_AGGREGATE_RETENTION_DAYS``; reports read these for completed days.
- ``analytics_rollup_days``: which days are rolled up, with daily totals.
- ``analytics_salts``: the current day's random salt only.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db
from .types import UTCDateTime, utcnow

PAGE_TYPES = (
    "home",
    "article",
    "article_index",
    "topic",
    "shop",
    "product",
    "course",
    "membership",
    "resource",
    "page",
)
SOURCES = ("direct", "search", "social", "email", "referral", "campaign", "internal")


class AnalyticsPageView(db.Model):
    __tablename__ = "analytics_page_views"
    __table_args__ = (
        Index("ix_analytics_page_views_day", "day", "page_type"),
        Index("ix_analytics_page_views_visitor", "visitor_hash", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    page_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    referrer_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    utm_source: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_medium: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_campaign: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_content: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_term: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    visitor_hash: Mapped[str] = mapped_column(String(16), default="", nullable=False)


class AnalyticsDailyPage(db.Model):
    __tablename__ = "analytics_daily_pages"
    __table_args__ = (UniqueConstraint("day", "path", name="uq_analytics_daily_pages_day_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    page_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AnalyticsDailySource(db.Model):
    __tablename__ = "analytics_daily_sources"
    __table_args__ = (
        UniqueConstraint(
            "day",
            "source",
            "referrer_host",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            name="uq_analytics_daily_sources_dims",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    referrer_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    utm_source: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_medium: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    utm_campaign: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AnalyticsRollupDay(db.Model):
    __tablename__ = "analytics_rollup_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visitors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rolled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AnalyticsSalt(db.Model):
    __tablename__ = "analytics_salts"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
