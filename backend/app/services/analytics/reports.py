"""Website analytics reports (``GET /api/v1/admin/analytics/traffic``).

Completed, rolled-up days are read from the daily aggregates; other days in range
(normally just today, or days the maintenance job hasn't reached yet) are computed from
raw page views. Everything comes from recorded rows: nothing is estimated or filled in.

Visitors are *daily* estimates (distinct salted hashes per day). Because the salt changes
every day, a person visiting on two days counts twice: multi-day figures are the sum of
daily visitors and are labelled as such. Sessions are not measured.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from ...extensions import db
from ...models import (
    AnalyticsDailyPage,
    AnalyticsDailySource,
    AnalyticsPageView,
    AnalyticsRollupDay,
    Article,
    Topic,
)
from ...utils.errors import ValidationError
from ..serializers import iso

V = AnalyticsPageView
MAX_RANGE_DAYS = 800
TOP = 20
GRANULARITIES = ("day", "week", "month")


def _today() -> date:
    return datetime.now(UTC).date()


def _parse(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValidationError(details={field: ["Use YYYY-MM-DD."]}) from None


def resolve_range(args: dict[str, Any]) -> tuple[date, date, str]:
    today = _today()
    preset = args.get("range")
    presets = {"7d": 6, "30d": 29, "90d": 89, "365d": 364}
    if preset and preset not in presets:
        raise ValidationError(details={"range": ["Use 7d, 30d, 90d or 365d."]})
    end = _parse(args.get("date_to"), "date_to") or today
    start = _parse(args.get("date_from"), "date_from") or end - timedelta(
        days=presets.get(preset or "30d", 29)
    )
    if start > end:
        raise ValidationError(details={"date_from": ["The start must be before the end."]})
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValidationError(details={"date_from": ["Choose a shorter range."]})
    granularity = args.get("granularity") or (
        "day" if (end - start).days <= 62 else "week" if (end - start).days <= 190 else "month"
    )
    if granularity not in GRANULARITIES:
        raise ValidationError(details={"granularity": ["Use day, week or month."]})
    return start, end, granularity


def _bucket(day: date, granularity: str) -> str:
    if granularity == "week":
        monday = day - timedelta(days=day.weekday())
        return monday.isoformat()
    if granularity == "month":
        return day.strftime("%Y-%m")
    return day.isoformat()


def _split_days(start: date, end: date) -> tuple[set[date], list[date]]:
    rolled = set(
        db.session.scalars(
            select(AnalyticsRollupDay.day).where(
                AnalyticsRollupDay.day >= start, AnalyticsRollupDay.day <= end
            )
        )
    )
    raw_days = [
        d
        for d in db.session.scalars(
            select(V.day).where(V.day >= start, V.day <= end).group_by(V.day)
        )
        if d not in rolled
    ]
    return rolled, raw_days


def _daily_totals(start, end, rolled, raw_days) -> dict[date, tuple[int, int]]:
    out: dict[date, tuple[int, int]] = {}
    for r in db.session.scalars(
        select(AnalyticsRollupDay).where(
            AnalyticsRollupDay.day >= start, AnalyticsRollupDay.day <= end
        )
    ):
        out[r.day] = (r.views, r.visitors)
    if raw_days:
        for day, views, visitors in db.session.execute(
            select(V.day, func.count(V.id), func.count(func.distinct(V.visitor_hash)))
            .where(V.day.in_(raw_days))
            .group_by(V.day)
        ):
            out[day] = (views, visitors)
    return out


def _page_rows(start, end, raw_days) -> dict[str, dict[str, Any]]:
    """Per path: views, summed daily visitors, page type and content id."""
    pages: dict[str, dict[str, Any]] = {}

    def add(path, page_type, content_type, content_id, views, visitors):
        row = pages.setdefault(
            path,
            {
                "path": path,
                "page_type": page_type,
                "content_type": content_type,
                "content_id": content_id,
                "views": 0,
                "visitors": 0,
            },
        )
        row["views"] += views
        row["visitors"] += visitors
        if content_id and not row["content_id"]:
            row["content_type"], row["content_id"] = content_type, content_id

    P = AnalyticsDailyPage
    for r in db.session.execute(
        select(
            P.path,
            func.max(P.page_type),
            func.max(P.content_type),
            func.max(P.content_id),
            func.sum(P.views),
            func.sum(P.visitors),
        )
        .where(P.day >= start, P.day <= end)
        .group_by(P.path)
    ):
        add(*r)
    if raw_days:
        for r in db.session.execute(
            select(
                V.path,
                func.max(V.page_type),
                func.max(V.content_type),
                func.max(V.content_id),
                func.count(V.id),
                func.count(func.distinct(V.visitor_hash)),
            )
            .where(V.day.in_(raw_days))
            .group_by(V.day, V.path)
        ):
            add(*r)
    return pages


def _source_rows(start, end, raw_days) -> list[tuple]:
    """(source, referrer_host, utm_source, utm_medium, utm_campaign, views, visitors)."""
    S = AnalyticsDailySource
    # Rolled-up days are summed in the database (visitors are already per-day counts, so
    # the sum is the same "sum of daily visitors" as adding the rows one by one).
    stored = (S.source, S.referrer_host, S.utm_source, S.utm_medium, S.utm_campaign)
    rows = list(
        db.session.execute(
            select(*stored, func.sum(S.views), func.sum(S.visitors))
            .where(S.day >= start, S.day <= end)
            .group_by(*stored)
        )
    )
    if raw_days:
        dims = (V.source, V.referrer_host, V.utm_source, V.utm_medium, V.utm_campaign)
        rows += list(
            db.session.execute(
                select(*dims, func.count(V.id), func.count(func.distinct(V.visitor_hash)))
                .where(V.day.in_(raw_days))
                .group_by(V.day, *dims)
            )
        )
    return rows


def _rank(counter: dict, key_name: str, limit: int = TOP) -> list[dict[str, Any]]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1][0], str(kv[0])))[:limit]
    return [{key_name: k, "views": v[0], "visitors": v[1]} for k, v in items]


def traffic_totals(args: dict[str, Any]) -> dict[str, int]:
    """Only the range totals of ``traffic_report`` (same definitions), for comparisons."""
    start, end, _g = resolve_range(args)
    rolled, raw_days = _split_days(start, end)
    daily = _daily_totals(start, end, rolled, raw_days)
    return {
        "views": sum(v for v, _ in daily.values()),
        "visitors_daily_sum": sum(u for _, u in daily.values()),
    }


def traffic_report(args: dict[str, Any]) -> dict[str, Any]:
    start, end, granularity = resolve_range(args)
    rolled, raw_days = _split_days(start, end)
    daily = _daily_totals(start, end, rolled, raw_days)

    series: dict[str, list[int]] = {}
    day = start
    while day <= end:  # every bucket in range, zero where nothing was recorded
        series.setdefault(_bucket(day, granularity), [0, 0])
        views, visitors = daily.get(day, (0, 0))
        series[_bucket(day, granularity)][0] += views
        series[_bucket(day, granularity)][1] += visitors
        day += timedelta(days=1)
    total_views = sum(v for v, _ in daily.values())
    total_visitors = sum(u for _, u in daily.values())

    pages = _page_rows(start, end, raw_days)
    top_pages = sorted(pages.values(), key=lambda r: (-r["views"], r["path"]))[:TOP]

    article_ids = {r["content_id"] for r in pages.values() if r["content_type"] == "article"}
    articles = {
        a.id: a
        for a in db.session.scalars(select(Article).where(Article.id.in_(article_ids or {0})))
    }
    topic_ids = {a.primary_topic_id for a in articles.values() if a.primary_topic_id}
    topic_ids |= {r["content_id"] for r in pages.values() if r["content_type"] == "topic"}
    topics = {
        t.id: t for t in db.session.scalars(select(Topic).where(Topic.id.in_(topic_ids or {0})))
    }

    per_article: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    categories: dict[int, dict[str, int]] = defaultdict(
        lambda: {"article_views": 0, "topic_page_views": 0}
    )
    for r in pages.values():
        if r["content_type"] == "article" and r["content_id"] in articles:
            per_article[r["content_id"]][0] += r["views"]
            per_article[r["content_id"]][1] += r["visitors"]
            topic_id = articles[r["content_id"]].primary_topic_id
            if topic_id:
                categories[topic_id]["article_views"] += r["views"]
        elif r["content_type"] == "topic" and r["content_id"] in topics:
            categories[r["content_id"]]["topic_page_views"] += r["views"]
    popular = [
        {
            "id": aid,
            "title": articles[aid].title,
            "slug": articles[aid].slug,
            "topic": topics[articles[aid].primary_topic_id].name
            if articles[aid].primary_topic_id in topics
            else None,
            "views": v[0],
            "visitors": v[1],
        }
        for aid, v in sorted(per_article.items(), key=lambda kv: (-kv[1][0], kv[0]))[:TOP]
    ]
    top_categories = sorted(
        (
            {
                "topic": topics[tid].name,
                "slug": topics[tid].slug,
                "views": c["article_views"] + c["topic_page_views"],
                **c,
            }
            for tid, c in categories.items()
            if tid in topics
        ),
        key=lambda c: (-c["views"], c["topic"]),
    )[:TOP]

    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_referrer: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_campaign: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for src, host, us, um, uc, views, visitors in _source_rows(start, end, raw_days):
        by_source[src][0] += views
        by_source[src][1] += visitors
        if host and src not in ("internal",):
            by_referrer[host][0] += views
            by_referrer[host][1] += visitors
        if src == "campaign":
            key = (uc or "(none)", us or "(none)", um or "(none)")
            by_campaign[key][0] += views
            by_campaign[key][1] += visitors
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in pages.values():
        by_type[r["page_type"]][0] += r["views"]
        by_type[r["page_type"]][1] += r["visitors"]

    cfg = current_app.config
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "granularity": granularity},
        "generated_at": iso(datetime.now(UTC)),
        "has_data": total_views > 0,
        "totals": {
            "views": total_views,
            "visitors_daily_sum": total_visitors,
            "days_with_data": sum(1 for v, _ in daily.values() if v),
            "average_daily_views": round(total_views / ((end - start).days + 1), 1),
        },
        "series": [{"period": k, "views": v[0], "visitors": v[1]} for k, v in series.items()],
        "pages": top_pages,
        "page_types": _rank(by_type, "page_type"),
        "articles": popular,
        "categories": top_categories,
        "sources": _rank(by_source, "source"),
        "referrers": _rank(by_referrer, "host"),
        "campaigns": [
            {
                "campaign": k[0],
                "utm_source": k[1],
                "utm_medium": k[2],
                "views": v[0],
                "visitors": v[1],
            }
            for k, v in sorted(by_campaign.items(), key=lambda kv: (-kv[1][0], kv[0]))[:TOP]
        ],
        "measurement": {
            "visitors": "Estimated per day from a salted hash that changes daily (no cookies). "
            "A person visiting on several days is counted once per day, so ranges show the "
            "sum of daily visitors, not unique people.",
            "sessions": "Not measured: without cookies, sessions can't be identified reliably.",
            "exclusions": "Bots, automated browsers, admin and account pages, Do Not Track / "
            "Global Privacy Control requests and repeat hits within 30 seconds are not counted.",
        },
        "tracking": {
            "enabled": cfg.get("ANALYTICS_TRACKING") == "enabled",
            "respects_do_not_track": bool(cfg.get("ANALYTICS_RESPECT_DNT", True)),
            "raw_retention_days": cfg.get("ANALYTICS_RAW_RETENTION_DAYS"),
            "aggregate_retention_days": cfg.get("ANALYTICS_AGGREGATE_RETENTION_DAYS"),
            "pending_rollup_days": len([d for d in raw_days if d < _today()]),
        },
    }
