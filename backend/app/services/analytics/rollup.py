"""Daily rollups and retention (``flask analytics maintain``, run hourly by a timer).

Completed days (before today, UTC) are aggregated once into ``analytics_daily_pages`` /
``analytics_daily_sources`` / ``analytics_rollup_days``. A day's raw rows are final once
it is over (events are stamped with the server's receive time), so a rollup never
changes later. Raw rows are deleted after ``ANALYTICS_RAW_RETENTION_DAYS`` (only once
their day is rolled up), rollups after ``ANALYTICS_AGGREGATE_RETENTION_DAYS``, and salts
as soon as their day has passed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from flask import current_app
from sqlalchemy import delete, func, insert, select

from ...extensions import db
from ...models import (
    AnalyticsDailyPage,
    AnalyticsDailySource,
    AnalyticsPageView,
    AnalyticsRollupDay,
    AnalyticsSalt,
)

V = AnalyticsPageView


def _today() -> date:
    return datetime.now(UTC).date()


def rollup_day(day: date) -> int:
    """(Re)build one completed day's aggregates. Idempotent. Returns the day's views."""
    db.session.execute(delete(AnalyticsDailyPage).where(AnalyticsDailyPage.day == day))
    db.session.execute(delete(AnalyticsDailySource).where(AnalyticsDailySource.day == day))
    db.session.execute(delete(AnalyticsRollupDay).where(AnalyticsRollupDay.day == day))
    visitors = func.count(func.distinct(V.visitor_hash))
    pages = db.session.execute(
        select(
            V.path,
            func.max(V.page_type),
            func.max(V.content_type),
            func.max(V.content_id),
            func.count(V.id),
            visitors,
        )
        .where(V.day == day)
        .group_by(V.path)
    ).all()
    if pages:
        db.session.execute(
            insert(AnalyticsDailyPage),
            [
                {
                    "day": day,
                    "path": path,
                    "page_type": page_type,
                    "content_type": content_type or "",
                    "content_id": content_id,
                    "views": views,
                    "visitors": unique,
                }
                for path, page_type, content_type, content_id, views, unique in pages
            ],
        )
    dims = (V.source, V.referrer_host, V.utm_source, V.utm_medium, V.utm_campaign)
    sources = db.session.execute(
        select(*dims, func.count(V.id), visitors).where(V.day == day).group_by(*dims)
    ).all()
    if sources:
        db.session.execute(
            insert(AnalyticsDailySource),
            [
                {
                    "day": day,
                    "source": src,
                    "referrer_host": host,
                    "utm_source": us,
                    "utm_medium": um,
                    "utm_campaign": uc,
                    "views": views,
                    "visitors": unique,
                }
                for src, host, us, um, uc, views, unique in sources
            ],
        )
    total, unique = db.session.execute(select(func.count(V.id), visitors).where(V.day == day)).one()
    db.session.add(AnalyticsRollupDay(day=day, views=total or 0, visitors=unique or 0))
    return total or 0


def maintain(today: date | None = None) -> dict[str, int]:
    today = today or _today()
    cfg = current_app.config
    counts = {"rolled_up": 0, "raw_deleted": 0, "aggregates_deleted": 0, "salts_deleted": 0}
    rolled = set(db.session.scalars(select(AnalyticsRollupDay.day)))
    pending = db.session.scalars(
        select(V.day).where(V.day < today).group_by(V.day).order_by(V.day)
    ).all()
    for day in pending:
        if day not in rolled:
            rollup_day(day)
            db.session.commit()
            counts["rolled_up"] += 1
    raw_cutoff = today - timedelta(days=cfg["ANALYTICS_RAW_RETENTION_DAYS"])
    rolled = set(db.session.scalars(select(AnalyticsRollupDay.day)))
    old_days = [
        d
        for d in db.session.scalars(select(V.day).where(V.day < raw_cutoff).group_by(V.day))
        if d in rolled
    ]
    for day in old_days:
        counts["raw_deleted"] += db.session.execute(delete(V).where(V.day == day)).rowcount or 0
    agg_cutoff = today - timedelta(days=cfg["ANALYTICS_AGGREGATE_RETENTION_DAYS"])
    for model in (AnalyticsDailyPage, AnalyticsDailySource, AnalyticsRollupDay):
        counts["aggregates_deleted"] += (
            db.session.execute(delete(model).where(model.day < agg_cutoff)).rowcount or 0
        )
    counts["salts_deleted"] = (
        db.session.execute(delete(AnalyticsSalt).where(AnalyticsSalt.day < today)).rowcount or 0
    )
    db.session.commit()
    return counts
