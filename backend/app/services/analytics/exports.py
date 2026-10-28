"""Analytics CSV exports (Batch 11.5): aggregates from the module reports only.

- Each report needs its tab's permission. Membership exports also need
  ``finance.export`` (they contain revenue); commerce keeps its existing
  ``finance.export`` endpoint. Every export is audited by the API layer.
- No emails, names, ids of customers or learners, answers or private records: the
  reports themselves are aggregate-only.
- Money is written per currency and payment mode, never combined.
- Formula injection: any cell starting with ``=``, ``+``, ``-``, ``@``, tab or carriage
  return is prefixed with an apostrophe so spreadsheets treat it as text.
"""

from __future__ import annotations

from typing import Any

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...models import User
from ...utils.csv_safe import SafeWriter, safe_cell  # noqa: F401  (re-exported)
from ...utils.errors import ForbiddenError, ValidationError

REPORTS = ("website", "learning", "membership", "audience", "overview")


def _money(m: dict | None) -> str:
    return m["amount"] if m else ""


def _require(actor: User, *perms: P) -> None:
    granted = effective_permissions(actor)
    if not all(p.value in granted for p in perms):
        raise ForbiddenError()


def _website(w: SafeWriter, args: dict[str, Any]) -> None:
    from .reports import traffic_report

    r = traffic_report(args)
    w.row("report", "website", "from", r["range"]["from"], "to", r["range"]["to"])
    w.row(
        "page_views",
        r["totals"]["views"],
        "daily_visitors_sum_estimate",
        r["totals"]["visitors_daily_sum"],
    )
    w.row()
    w.row("period", "page_views", "daily_visitors_sum")
    for s in r["series"]:
        w.row(s["period"], s["views"], s["visitors"])
    w.row()
    w.row("article", "topic", "views")
    for a in r["articles"]:
        w.row(a["title"], a["topic"] or "", a["views"])
    w.row()
    w.row("source", "views")
    for s in r["sources"]:
        w.row(s["source"], s["views"])
    w.row()
    w.row("campaign", "utm_source", "utm_medium", "views")
    for c in r["campaigns"]:
        w.row(c["campaign"], c["utm_source"], c["utm_medium"], c["views"])


def _learning(w: SafeWriter, args: dict[str, Any], actor: User) -> None:
    from .learning import learning_report

    r = learning_report(args, actor)
    w.row("report", "learning", "from", r["range"]["from"], "to", r["range"]["to"])
    w.row(
        "new_enrollments",
        r["period"]["new_enrollments"],
        "starts",
        r["period"]["starts"],
        "completions",
        r["period"]["completions"],
        "active_learners_minimum",
        r["period"]["active_learners"],
    )
    w.row()
    w.row(
        "course",
        "enrollments",
        "started",
        "completed",
        "completion_rate",
        "average_progress",
        "assignment_submissions",
        "assessment_participants",
        "average_best_score",
    )
    for c in r["courses"]:
        w.row(
            c["title"],
            c["enrollments"],
            c["started"],
            c["completed"],
            c["completion_rate"],
            c["average_progress"],
            c["assignment_submissions"],
            c["assessment_participants"],
            c["average_best_score"],
        )
    w.row()
    w.row("assessment_type", "attempts", "participants", "passed", "failed", "average_percent")
    for kind, a in r["assessments"]["by_type"].items():
        w.row(
            kind, a["attempts"], a["participants"], a["passed"], a["failed"], a["average_percent"]
        )


def _membership(w: SafeWriter, args: dict[str, Any], actor: User) -> None:
    from .membership import membership_analytics

    r = membership_analytics(args, actor)
    w.row("report", "membership", "from", r["range"]["from"], "to", r["range"]["to"])
    w.row(
        "paid_members_now",
        r["current"]["paid_subscribers"],
        "complimentary_now",
        r["current"]["complimentary"],
    )
    w.row(
        "new_subscriptions", r["period"]["new_subscriptions"], "renewals", r["period"]["renewals"]
    )
    w.row()
    w.row("realised", "mode", "currency", "gross", "refunds", "net")
    refunds = {(x["mode"], x["amount"]["currency"]): x["amount"] for x in r["refunds"]}
    nets = {(x["mode"], x["amount"]["currency"]): x["amount"] for x in r["net_revenue"]}
    for x in r["revenue"]:
        key = (x["mode"], x["amount"]["currency"])
        w.row(
            "revenue",
            x["mode"],
            key[1],
            _money(x["amount"]),
            _money(refunds.get(key)),
            _money(nets.get(key)),
        )
    w.row()
    w.row("estimate", "mode", "currency", "subscriptions", "mrr", "arr")
    for x in r["recurring_estimate"]:
        w.row(
            "recurring",
            x["mode"],
            x["mrr"]["currency"],
            x["subscriptions"],
            _money(x["mrr"]),
            _money(x["arr"]),
        )
    w.row()
    w.row("plan", "interval", "mode", "paid_members")
    for x in r["by_plan"]:
        w.row(x["plan"], x["interval"], x["mode"], x["paid_members"])


def _audience(w: SafeWriter, args: dict[str, Any]) -> None:
    from .audience import audience_report

    r = audience_report(args)
    w.row("report", "audience", "from", r["range"]["from"], "to", r["range"]["to"])
    w.row(
        "subscribed_now",
        r["current"]["subscribed"],
        "signups",
        r["period"]["signups"],
        "new_subscriptions",
        r["period"]["new_subscriptions"],
        "unsubscriptions",
        r["period"]["unsubscriptions"],
    )
    w.row()
    w.row("period", "signups", "new_subscriptions", "unsubscriptions", "net_growth")
    for t in r["trend"]:
        w.row(
            t["period"], t["signups"], t["new_subscriptions"], t["unsubscriptions"], t["net_growth"]
        )
    w.row()
    w.row("campaign", "eligible", "accepted", "delivered_confirmed", "bounced", "complained")
    for c in r["campaigns"]:
        w.row(
            c["name"],
            c["eligible"],
            c["accepted"],
            c["delivered_confirmed"],
            c["bounced"],
            c["complained"],
        )
    w.row("opens_and_clicks", "not tracked")


def _overview(w: SafeWriter, args: dict[str, Any], actor: User) -> None:
    from .overview import overview_report

    r = overview_report(args, actor)
    financial = P.FINANCE_EXPORT.value in effective_permissions(actor)
    w.row(
        "report",
        "overview",
        "from",
        r["range"]["from"],
        "to",
        r["range"]["to"],
        "previous_from",
        r["previous_range"]["from"],
        "previous_to",
        r["previous_range"]["to"],
    )
    w.row("section", "metric", "kind", "mode", "currency", "value", "previous", "change_pct")
    for name, section in r["sections"].items():
        if name in ("commerce", "membership") and not financial:
            continue  # financial figures need finance.export
        for metric, value in section.items():
            items = value if isinstance(value, list) else [value]
            for item in items:
                if not isinstance(item, dict) or "kind" not in item:
                    continue
                v = item.get("value")
                if isinstance(v, dict):  # money object (estimates)
                    w.row(
                        name,
                        metric,
                        item["kind"],
                        item.get("mode", ""),
                        v["currency"],
                        v["amount"],
                        "",
                        "",
                    )
                    continue
                currency = item.get("currency", "")
                w.row(
                    name,
                    metric,
                    item["kind"],
                    item.get("mode", ""),
                    currency,
                    v,
                    item.get("previous", ""),
                    item.get("change_pct", ""),
                )


def export(report: str, args: dict[str, Any], actor: User) -> str:
    if report not in REPORTS:
        raise ValidationError(details={"report": [f"Use one of: {', '.join(REPORTS)}."]})
    w = SafeWriter()
    if report == "website":
        _require(actor, P.ANALYTICS_VIEW)
        _website(w, args)
    elif report == "learning":
        _require(actor, P.COURSES_VIEW_REPORTS)
        _learning(w, args, actor)
    elif report == "membership":
        _require(actor, P.MEMBERSHIPS_VIEW_REPORTS, P.FINANCE_EXPORT)
        _membership(w, args, actor)
    elif report == "audience":
        _require(actor, P.NEWSLETTERS_REPORTS)
        _audience(w, args)
    else:
        from .overview import allowed_modules

        if not allowed_modules(actor):
            raise ForbiddenError()
        _overview(w, args, actor)
    return w.value()
