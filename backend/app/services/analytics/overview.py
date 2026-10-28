"""Unified analytics overview (Batch 11.5).

A permission-aware summary built only from the existing module reports (website 11.1,
commerce 11.2, learning 11.3, membership and audience 11.4). No figure is recomputed
here, so each keeps its module's definition. A module is included only when the
requesting user holds that module's permission (the same one its own tab requires):

- website: ``analytics.view``; commerce: ``finance.view``; learning:
  ``courses.view_reports``; membership: ``memberships.view_reports``; audience:
  ``newsletters.reports``; analytics health: ``analytics.view``.

Comparisons: period figures (counts or money in the range) are compared with the
previous range of the same length; point-in-time figures (current members, subscribed
contacts, current enrollments) and estimates (MRR) are never compared, and money is only
compared within the same currency and mode.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...extensions import db
from ...models import AnalyticsPageView, AnalyticsRollupDay, User
from ..serializers import iso
from . import reports as traffic

MODULE_PERMISSIONS = {
    "website": P.ANALYTICS_VIEW,
    "commerce": P.FINANCE_VIEW,
    "learning": P.COURSES_VIEW_REPORTS,
    "membership": P.MEMBERSHIPS_VIEW_REPORTS,
    "audience": P.NEWSLETTERS_REPORTS,
}


def allowed_modules(actor: User) -> list[str]:
    granted = effective_permissions(actor)
    return [m for m, perm in MODULE_PERMISSIONS.items() if perm.value in granted]


def ranges(args: dict[str, Any]) -> tuple[date, date, date, date]:
    start, end, _g = traffic.resolve_range(args)
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return start, end, prev_end - timedelta(days=days - 1), prev_end


def compare(value: int | float | None, previous: int | float | None) -> dict[str, Any]:
    """A period metric with its previous-period value. The percentage is omitted when
    the previous value is zero or unknown (it would be infinite or meaningless)."""
    out: dict[str, Any] = {"kind": "period", "value": value, "previous": previous}
    if value is None or previous is None:
        out["change"] = out["change_pct"] = None
        return out
    out["change"] = round(value - previous, 2)
    out["change_pct"] = round(100 * (value - previous) / previous, 1) if previous else None
    return out


def point(value: Any) -> dict[str, Any]:
    return {"kind": "point_in_time", "value": value}


def _money_compare(
    current: list[dict], previous: list[dict], key: str, label_key="amount"
) -> list[dict]:
    """Per (mode, currency) money comparison: amounts are never added across them."""

    def index(rows):
        return {(r.get("mode", "live"), r[label_key]["currency"]): r[label_key] for r in rows}

    cur, prev = index(current), index(previous)
    out = []
    for mode, currency in sorted(set(cur) | set(prev)):
        now = cur.get((mode, currency))
        before = prev.get((mode, currency))
        row = compare(now["amount_minor"] if now else 0, before["amount_minor"] if before else 0)
        row |= {
            "metric": key,
            "mode": mode,
            "currency": currency,
            "formatted": now["formatted"] if now else None,
            "previous_formatted": before["formatted"] if before else None,
        }
        out.append(row)
    return out


def _website(cur_args, prev_args) -> dict[str, Any]:
    now = traffic.traffic_report(cur_args)
    before = traffic.traffic_report(prev_args)
    return {
        "page_views": compare(now["totals"]["views"], before["totals"]["views"]),
        "visitors_daily_sum": compare(
            now["totals"]["visitors_daily_sum"], before["totals"]["visitors_daily_sum"]
        )
        | {"estimate": True},
        "top_articles": [
            {"title": a["title"], "topic": a["topic"], "views": a["views"]}
            for a in now["articles"][:5]
        ],
        "series": now["series"],
        "notes": [now["measurement"]["visitors"], now["measurement"]["sessions"]],
    }


def _commerce(cur_args, prev_args, mode) -> dict[str, Any]:
    from .commerce import commerce_report

    now = commerce_report(cur_args | {"mode": mode})
    before = commerce_report(prev_args | {"mode": mode})

    def rows(report, key):
        return [{"mode": mode, key: c[key]} for c in report["currencies"]]

    by_cur = {c["currency"]: c for c in now["currencies"]}
    prev_cur = {c["currency"]: c for c in before["currencies"]}
    return {
        "mode": mode,
        "gross": _money_compare(rows(now, "gross"), rows(before, "gross"), "gross", "gross"),
        "refunds": _money_compare(
            rows(now, "refunds"), rows(before, "refunds"), "refunds", "refunds"
        ),
        "net": _money_compare(rows(now, "net"), rows(before, "net"), "net", "net"),
        "paid_orders": [
            compare(by_cur.get(c, {}).get("orders", 0), prev_cur.get(c, {}).get("orders", 0))
            | {"currency": c}
            for c in sorted(set(by_cur) | set(prev_cur))
        ],
        "top_products": [
            {
                "title": p["title"],
                "currency": p["currency"],
                "units": p["units"],
                "revenue": p["revenue"],
            }
            for p in now["products"][:5]
        ],
        "other_mode_payments": sum(m["verified_sales"] for m in now["modes"] if m["mode"] != mode),
    }


def _learning(cur_args, prev_args, actor) -> dict[str, Any]:
    from .learning import learning_report

    now = learning_report(cur_args, actor)
    before = learning_report(prev_args, actor)
    p, q = now["period"], before["period"]
    return {
        "new_enrollments": compare(p["new_enrollments"], q["new_enrollments"]),
        "completions": compare(p["completions"], q["completions"]),
        "starts": compare(p["starts"], q["starts"]),
        "active_learners": compare(p["active_learners"], q["active_learners"]) | {"minimum": True},
        "current_enrollments": point(now["current"]["enrollments"]),
        "completion_rate": point(now["current"]["completion_rate"]),
    }


def _membership(cur_args, prev_args, actor) -> dict[str, Any]:
    from .membership import membership_analytics

    now = membership_analytics(cur_args, actor)
    before = membership_analytics(prev_args, actor)
    return {
        "paid_members": point(now["current"]["paid_subscribers"]),
        "complimentary": point(now["current"]["complimentary"]),
        "new_subscriptions": compare(
            now["period"]["new_subscriptions"], before["period"]["new_subscriptions"]
        ),
        "renewals": compare(now["period"]["renewals"], before["period"]["renewals"]),
        "revenue": _money_compare(now["revenue"], before["revenue"], "revenue"),
        "net_revenue": _money_compare(now["net_revenue"], before["net_revenue"], "net_revenue"),
        "mrr_estimate": [
            {"kind": "estimate", "mode": r["mode"], "value": r["mrr"]}
            for r in now["recurring_estimate"]
        ],
    }


def _audience(cur_args, prev_args) -> dict[str, Any]:
    from .audience import audience_report

    now = audience_report(cur_args)
    before = audience_report(prev_args)
    p, q = now["period"], before["period"]
    return {
        "subscribed": point(now["current"]["subscribed"]),
        "signups": compare(p["signups"], q["signups"]),
        "new_subscriptions": compare(p["new_subscriptions"], q["new_subscriptions"]),
        "unsubscriptions": compare(p["unsubscriptions"], q["unsubscriptions"]),
        "campaigns_sent": compare(p["campaigns_sent"], q["campaigns_sent"]),
    }


def health() -> dict[str, Any]:
    """What the stored records can tell about analytics freshness. The maintenance job's
    own runs aren't recorded; ``rolled_at`` of the newest rollup is the best evidence."""
    cfg = current_app.config
    today = datetime.now(UTC).date()
    latest = db.session.scalar(
        select(AnalyticsRollupDay).order_by(AnalyticsRollupDay.day.desc()).limit(1)
    )
    rolled = set(
        db.session.scalars(
            select(AnalyticsRollupDay.day).where(
                AnalyticsRollupDay.day >= today - timedelta(days=30)
            )
        )
    )
    pending = [
        d
        for d in db.session.scalars(
            select(AnalyticsPageView.day)
            .where(AnalyticsPageView.day < today)
            .group_by(AnalyticsPageView.day)
        )
        if d not in rolled
    ]
    warnings = []
    if cfg.get("ANALYTICS_TRACKING") != "enabled":
        warnings.append("Traffic tracking is disabled: no new page views are recorded.")
    if pending:
        warnings.append(
            f"{len(pending)} completed day(s) are not rolled up yet; check the "
            "tpa-analytics-maintain timer. Reports still include them from raw records."
        )
    warnings.append(
        "Sessions, email opens/clicks and visitor-level purchase conversion are not measured."
    )
    return {
        "tracking_enabled": cfg.get("ANALYTICS_TRACKING") == "enabled",
        "respects_do_not_track": bool(cfg.get("ANALYTICS_RESPECT_DNT", True)),
        "raw_retention_days": cfg.get("ANALYTICS_RAW_RETENTION_DAYS"),
        "aggregate_retention_days": cfg.get("ANALYTICS_AGGREGATE_RETENTION_DAYS"),
        "latest_rollup_day": latest.day.isoformat() if latest else None,
        "latest_rollup_at": iso(latest.rolled_at) if latest else None,
        "pending_rollup_days": len(pending),
        "oldest_raw_day": (lambda d: d.isoformat() if d else None)(
            db.session.scalar(select(func.min(AnalyticsPageView.day)))
        ),
        "page_views_today": db.session.scalar(
            select(func.count(AnalyticsPageView.id)).where(AnalyticsPageView.day == today)
        )
        or 0,
        "job_runs_recorded": False,
        "warnings": warnings,
    }


def overview_report(args: dict[str, Any], actor: User) -> dict[str, Any]:
    start, end, prev_start, prev_end = ranges(args)
    mode = args.get("mode") or "live"
    cur = {"date_from": start.isoformat(), "date_to": end.isoformat()}
    prev = {"date_from": prev_start.isoformat(), "date_to": prev_end.isoformat()}
    modules = allowed_modules(actor)
    sections: dict[str, Any] = {}
    if "website" in modules:
        sections["website"] = _website(cur, prev)
    if "commerce" in modules:
        sections["commerce"] = _commerce(cur, prev, mode)
    if "learning" in modules:
        sections["learning"] = _learning(cur, prev, actor)
    if "membership" in modules:
        sections["membership"] = _membership(cur, prev, actor)
    if "audience" in modules:
        sections["audience"] = _audience(cur, prev)
    return {
        "range": cur | {"from": start.isoformat(), "to": end.isoformat()},
        "previous_range": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "modules": modules,
        "sections": sections,
        "health": health() if "website" in modules else None,
        "notes": [
            "Each figure keeps its module's definition (see the module tabs).",
            "Period figures are compared with the previous period of the same length; "
            "point-in-time figures and estimates are not compared.",
            "Money is shown per currency and payment mode and never combined; commerce and "
            "membership revenue are separate measures.",
        ],
    }
