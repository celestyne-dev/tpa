"""Batch 11.5: unified analytics overview, health and safe CSV exports."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, Customer, OrderItem, Product

from .test_commerce_analytics import _order, _report, shop  # noqa: F401

OVERVIEW = "/api/v1/admin/analytics/overview"
EXPORT = "/api/v1/admin/analytics/export"
NOW = datetime.now(UTC)


def _overview(api, **params):
    res = api.get(OVERVIEW, query_string={"range": "7d", **params})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def test_compare_helper_and_previous_range():
    from app.services.analytics.overview import compare, ranges

    assert compare(10, 5) == {
        "kind": "period",
        "value": 10,
        "previous": 5,
        "change": 5,
        "change_pct": 100.0,
    }
    assert compare(3, 0)["change_pct"] is None and compare(3, 0)["change"] == 3
    assert compare(None, 2)["change"] is None
    start, end, prev_start, prev_end = ranges({"date_from": "2026-10-10", "date_to": "2026-10-16"})
    assert (prev_start.isoformat(), prev_end.isoformat()) == ("2026-10-03", "2026-10-09")


def test_permission_isolation(seeded, as_role, client):
    assert client.get(OVERVIEW).status_code == 401
    assert as_role("customer_support").get(OVERVIEW).status_code == 403
    seo = _overview(as_role("seo_manager"))
    assert set(seo["sections"]) == {"website"} and seo["health"] is not None
    finance = _overview(as_role("finance_manager"))
    assert set(finance["sections"]) == {"commerce", "membership"} and finance["health"] is None
    marketing = _overview(as_role("marketing_manager"))
    assert set(marketing["sections"]) == {"website", "learning", "audience"}
    everything = _overview(as_role("super_admin"))
    assert set(everything["sections"]) == {
        "website",
        "commerce",
        "learning",
        "membership",
        "audience",
    }


def test_commerce_comparison_currency_and_mode_separation(shop, as_role):  # noqa: F811
    app, ids = shop
    with app.app_context():
        c = db.session.scalar(select(Customer))
        guide = db.session.get(Product, ids["guide"])
        _order(c, [(guide, 1, 1000)], paid_at=NOW - timedelta(days=10))  # previous 7 days
        db.session.commit()
    finance = as_role("finance_manager")
    data = _overview(finance)["sections"]["commerce"]
    gross = {(g["mode"], g["currency"]): g for g in data["gross"]}
    assert set(gross) == {("live", "USD"), ("live", "KES")}  # never combined
    usd = gross[("live", "USD")]
    assert (usd["value"], usd["previous"], usd["change"]) == (9100, 1000, 8100)
    assert usd["change_pct"] == 810.0
    assert gross[("live", "KES")]["previous"] == 0 and gross[("live", "KES")]["change_pct"] is None
    assert data["other_mode_payments"] == 1  # the test-mode payment, reported separately
    test = _overview(finance, mode="test")["sections"]["commerce"]
    assert [(g["mode"], g["currency"], g["value"]) for g in test["gross"]] == [
        ("test", "USD", 1500)
    ]
    # Matches the commerce tab exactly (same definitions, no recalculation).
    tab = _report(
        finance,
        date_from=(NOW - timedelta(days=6)).date().isoformat(),
        date_to=NOW.date().isoformat(),
    )
    assert {c["currency"]: c["gross"]["amount_minor"] for c in tab["currencies"]} == {
        "USD": 9100,
        "KES": 2000,
    }


def test_point_in_time_vs_period_and_missing_data(seeded, as_role):
    data = _overview(as_role("super_admin"))
    s = data["sections"]
    assert s["membership"]["paid_members"] == {"kind": "point_in_time", "value": 0}
    assert "previous" not in s["membership"]["paid_members"]
    assert s["audience"]["subscribed"]["kind"] == "point_in_time"
    assert s["learning"]["new_enrollments"]["kind"] == "period"
    assert s["learning"]["active_learners"]["minimum"] is True
    assert s["website"]["visitors_daily_sum"]["estimate"] is True
    assert (
        s["website"]["page_views"]["value"] == 0
        and s["website"]["page_views"]["change_pct"] is None
    )
    assert s["commerce"]["gross"] == [] and s["membership"]["mrr_estimate"] == []
    h = data["health"]
    assert h["latest_rollup_day"] is None and h["job_runs_recorded"] is False
    assert h["pending_rollup_days"] == 0 and any("not measured" in w for w in h["warnings"])
    seeded.config["ANALYTICS_TRACKING"] = "disabled"
    h = as_role("seo_manager").get("/api/v1/admin/analytics/health").get_json()["data"]
    assert h["tracking_enabled"] is False and any("disabled" in w for w in h["warnings"])


def _csv(res):
    return list(csv.reader(io.StringIO(res.get_data(as_text=True))))


def test_exports_are_authorised_safe_and_audited(shop, as_role):  # noqa: F811
    app, ids = shop
    with app.app_context():
        # Exports use the historical order-line title (not the current product title).
        for item in db.session.scalars(
            select(OrderItem).where(OrderItem.product_id == ids["guide"])
        ):
            item.title = "=HYPERLINK(evil)"
        db.session.commit()
    seo, analyst, finance = as_role("seo_manager"), as_role("analyst"), as_role("finance_manager")
    res = seo.get(EXPORT, query_string={"report": "website", "range": "7d"})
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert seo.get(EXPORT, query_string={"report": "learning"}).status_code == 403
    assert seo.get(EXPORT, query_string={"report": "nope"}).status_code == 400
    assert (
        analyst.get(EXPORT, query_string={"report": "membership"}).status_code == 403
    )  # no finance.export
    assert finance.get(EXPORT, query_string={"report": "membership"}).status_code == 200
    # Overview CSV for an analytics-only user carries no financial rows.
    rows = _csv(seo.get(EXPORT, query_string={"report": "overview", "range": "7d"}))
    assert not any(r and r[0] in ("commerce", "membership") for r in rows)
    fin_rows = _csv(finance.get(EXPORT, query_string={"report": "overview", "range": "7d"}))
    usd = [r for r in fin_rows if r[:2] == ["commerce", "gross"] and r[4] == "USD"]
    assert usd and usd[0][3] == "live"
    # Formula injection is neutralised in the commerce export (product titles).
    text = finance.get(
        "/api/v1/admin/analytics/commerce/export", query_string={"range": "30d"}
    ).get_data(as_text=True)
    assert "'=HYPERLINK(evil)" in text and "\n=HYPERLINK" not in text and ",=HYPERLINK" not in text
    assert "buyer@example.com" not in text
    with app.app_context():
        actions = [
            a.details.get("report")
            for a in db.session.scalars(
                select(AuditLog).where(AuditLog.action == "analytics.report_exported")
            )
        ]
        assert {"website", "membership", "overview"} <= set(actions)


def test_safe_cell():
    from app.services.analytics.exports import safe_cell

    for bad in ("=1+1", "+1+A1", "-2+A1", "@SUM(A1)", "\tx", "\rx"):
        assert safe_cell(bad).startswith("'")
    assert safe_cell("Calm Guide") == "Calm Guide" and safe_cell(5) == 5
