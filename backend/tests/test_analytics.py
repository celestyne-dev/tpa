"""Batch 11.1: first-party website analytics (ingestion, privacy, rollups, reports)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AnalyticsDailyPage,
    AnalyticsPageView,
    AnalyticsRollupDay,
    AnalyticsSalt,
    Article,
    Topic,
)

COLLECT = "/api/v1/analytics/collect"
REPORT = "/api/v1/admin/analytics/traffic"
BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


def _send(client, body, *, ua=BROWSER, ip="203.0.113.7", **headers):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return client.post(
        COLLECT,
        data=raw,
        headers={"User-Agent": ua, "Content-Type": "text/plain", **headers},
        environ_base={"REMOTE_ADDR": ip},
    )


def _rows(app):
    with app.app_context():
        rows = db.session.scalars(select(AnalyticsPageView).order_by(AnalyticsPageView.id)).all()
        for r in rows:
            db.session.expunge(r)
        return rows


@pytest.fixture()
def article(seeded):
    with seeded.app_context():
        a = db.session.scalar(
            select(Article).where(
                Article.status == "published", Article.primary_topic_id.is_not(None)
            )
        )
        topic = db.session.get(Topic, a.primary_topic_id)
        return {
            "id": a.id,
            "slug": a.slug,
            "title": a.title,
            "topic": topic.name,
            "topic_slug": topic.slug,
        }


def test_records_page_views_with_content_source_and_campaign(seeded, client, article):
    res = _send(
        client,
        {
            "path": f"/articles/{article['slug']}/",
            "search": "?utm_source=Newsletter&utm_medium=email&utm_campaign=Spring%2026"
            "&email=me@example.com&token=abc&utm_term=reader@example.com",
            "referrer": "https://www.google.com/search?q=calm",
        },
    )
    assert res.status_code == 204 and res.data == b""
    [row] = _rows(seeded)
    assert row.path == f"/articles/{article['slug']}"
    assert (row.page_type, row.content_type, row.content_id) == (
        "article",
        "article",
        article["id"],
    )
    assert row.source == "campaign"  # UTM wins over the search referrer
    assert (row.utm_source, row.utm_medium, row.utm_campaign) == (
        "newsletter",
        "email",
        "spring 26",
    )
    assert row.utm_term == ""  # looked like an email address
    assert row.referrer_host == "google.com"
    _send(
        client,
        {"path": "/topics/" + article["topic_slug"], "referrer": "https://t.co/x"},
        ip="198.51.100.1",
    )
    _send(
        client,
        {"path": "/about", "spa": True, "referrer": "https://evil.example"},
        ip="198.51.100.2",
    )
    _send(client, {"path": "/", "referrer": "https://blog.example.org/post"}, ip="198.51.100.3")
    _send(client, {"path": "/shop"}, ip="198.51.100.4")
    rows = _rows(seeded)
    assert [(r.page_type, r.source) for r in rows[1:]] == [
        ("topic", "social"),
        ("page", "internal"),
        ("home", "referral"),
        ("shop", "direct"),
    ]
    assert rows[2].referrer_host == ""  # SPA navigations never keep a referrer


def test_privacy_no_ip_ua_query_or_tokens_are_stored(seeded, client):
    _send(client, {"path": "/articles?page=2&session=xyz", "referrer": "https://x.com/a?b=c"})
    [row] = _rows(seeded)
    stored = json.dumps({c.name: str(getattr(row, c.name)) for c in row.__table__.columns})
    for secret in ("203.0.113", "Mozilla", "session", "xyz", "page=2", "b=c"):
        assert secret not in stored
    assert len(row.visitor_hash) == 16
    ignored = [
        "/account/orders/123",
        "/checkout",
        "/admin/articles",
        "/api/v1/site",
        "/reset-password",
        "/newsletter/confirm",
        "/learn/calm/lesson-1",
        f"/articles/{'a' * 40}",  # token-like segment
        "/share/AbC123defGHI456jklMNO789",  # opaque mixed-case token
        "/user@example.com",
        "not-a-path",
    ]
    for i, path in enumerate(ignored):
        assert _send(client, {"path": path}, ip=f"192.0.2.{i + 1}").status_code == 204
    assert len(_rows(seeded)) == 1


def test_bots_dnt_cross_site_duplicates_and_oversized_bodies_are_ignored(seeded, client):
    for ua in ("Googlebot/2.1", "Mozilla/5.0 HeadlessChrome/130", "curl/8.0", ""):
        _send(client, {"path": "/"}, ua=ua)
    _send(client, {"path": "/"}, DNT="1")
    _send(client, {"path": "/"}, **{"Sec-GPC": "1"})
    _send(client, {"path": "/"}, Origin="https://attacker.example")
    _send(client, {"path": "/"}, **{"Sec-Fetch-Site": "cross-site"})
    _send(client, json.dumps({"path": "/", "pad": "x" * 3000}).encode())
    _send(client, b"{not json")
    assert _rows(seeded) == []
    _send(client, {"path": "/"})
    _send(client, {"path": "/"})  # reload within 30 seconds
    _send(client, {"path": "/"}, ip="203.0.113.99")  # same /24 and browser: same visitor
    _send(client, {"path": "/"}, ip="198.51.100.9")  # someone else
    rows = _rows(seeded)
    assert len(rows) == 2 and rows[0].visitor_hash != rows[1].visitor_hash
    seeded.config["ANALYTICS_TRACKING"] = "disabled"
    _send(client, {"path": "/about"}, ip="192.0.2.200")
    assert len(_rows(seeded)) == 2


def test_daily_salt_rotates_and_is_deleted(seeded, client, monkeypatch):
    import app.services.analytics.tracking as tracking

    _send(client, {"path": "/"})
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    monkeypatch.setattr(tracking, "_now", lambda: tomorrow)
    _send(client, {"path": "/"})
    first, second = _rows(seeded)
    assert first.visitor_hash != second.visitor_hash  # unlinkable across days
    from app.services.analytics.rollup import maintain

    with seeded.app_context():
        maintain(today=tomorrow.date() + timedelta(days=1))
        assert db.session.scalars(select(AnalyticsSalt)).all() == []


def _seed_views(app, rows):
    """rows: (day, path, page_type, content_type, content_id, source, extra)."""
    with app.app_context():
        for i, (day, path, ptype, ctype, cid, source, extra) in enumerate(rows):
            db.session.add(
                AnalyticsPageView(
                    occurred_at=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
                    day=day,
                    path=path,
                    page_type=ptype,
                    content_type=ctype,
                    content_id=cid,
                    source=source,
                    visitor_hash=extra.pop("visitor", f"v{i:015d}"),
                    **extra,
                )
            )
        db.session.commit()


def test_rollups_reports_rankings_and_filters(seeded, as_role, article):
    today = datetime.now(UTC).date()
    d1, d2 = today - timedelta(days=3), today - timedelta(days=2)
    art = (f"/articles/{article['slug']}", "article", "article", article["id"])
    with seeded.app_context():
        topic_id = db.session.scalar(select(Topic.id).where(Topic.slug == article["topic_slug"]))
    topic = (f"/topics/{article['topic_slug']}", "topic", "topic", topic_id)
    camp = {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "spring"}
    _seed_views(
        seeded,
        [
            (d1, *art, "search", {"referrer_host": "google.com", "visitor": "a" * 16}),
            (d1, *art, "search", {"referrer_host": "google.com", "visitor": "a" * 16}),
            (d1, *art, "campaign", dict(camp)),
            (d2, *topic, "social", {"referrer_host": "t.co"}),
            (d2, "/about", "page", "", None, "direct", {}),
            (today, *art, "direct", {}),
        ],
    )
    from app.services.analytics.rollup import maintain

    with seeded.app_context():
        counts = maintain()
        assert counts["rolled_up"] == 2
        assert db.session.get(AnalyticsRollupDay, d1).views == 3
        assert db.session.get(AnalyticsRollupDay, d1).visitors == 2  # same hash twice
        assert (
            db.session.scalar(select(AnalyticsDailyPage.views).where(AnalyticsDailyPage.day == d1))
            == 3
        )
        assert maintain()["rolled_up"] == 0  # idempotent

    analyst = as_role("analyst")
    data = analyst.get(REPORT, query_string={"range": "7d"}).get_json()["data"]
    assert data["has_data"] and data["totals"]["views"] == 6  # rollups + today's raw rows
    assert data["totals"]["visitors_daily_sum"] == 5
    assert len(data["series"]) == 7
    assert {s["period"]: s["views"] for s in data["series"]}[d1.isoformat()] == 3
    [top] = data["articles"]
    assert (top["id"], top["views"], top["topic"]) == (article["id"], 4, article["topic"])
    [cat] = data["categories"]
    assert (cat["topic"], cat["article_views"], cat["topic_page_views"]) == (article["topic"], 4, 1)
    sources = {s["source"]: s["views"] for s in data["sources"]}
    assert sources == {"search": 2, "campaign": 1, "social": 1, "direct": 2}
    assert data["referrers"][0] == {"host": "google.com", "views": 2, "visitors": 1}
    assert data["campaigns"] == [
        {
            "campaign": "spring",
            "utm_source": "newsletter",
            "utm_medium": "email",
            "views": 1,
            "visitors": 1,
        }
    ]
    assert "Not measured" in data["measurement"]["sessions"]

    only_d2 = analyst.get(
        REPORT, query_string={"date_from": d2.isoformat(), "date_to": d2.isoformat()}
    ).get_json()["data"]
    assert only_d2["totals"]["views"] == 2 and only_d2["articles"] == []
    monthly = analyst.get(REPORT, query_string={"range": "365d"}).get_json()["data"]
    assert monthly["range"]["granularity"] == "month" and monthly["totals"]["views"] == 6
    weekly = analyst.get(REPORT, query_string={"range": "30d", "granularity": "week"}).get_json()
    assert sum(s["views"] for s in weekly["data"]["series"]) == 6
    empty = analyst.get(
        REPORT, query_string={"date_from": "2020-01-01", "date_to": "2020-01-31"}
    ).get_json()["data"]
    assert empty["has_data"] is False and empty["articles"] == []
    for bad in (
        {"date_from": "x"},
        {"range": "2y"},
        {"granularity": "hour"},
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
    ):
        assert analyst.get(REPORT, query_string=bad).status_code == 400


def test_retention_deletes_old_raw_rows_only_after_rollup(seeded):
    old = datetime.now(UTC).date() - timedelta(days=120)
    _seed_views(seeded, [(old, "/", "home", "", None, "direct", {})])
    from app.services.analytics.rollup import maintain

    with seeded.app_context():
        counts = maintain()
        assert counts["rolled_up"] == 1 and counts["raw_deleted"] == 1
        assert db.session.get(AnalyticsRollupDay, old).views == 1  # the aggregate remains
        seeded.config["ANALYTICS_AGGREGATE_RETENTION_DAYS"] = 30
        assert maintain()["aggregates_deleted"] >= 1


def test_reports_require_analytics_permission(seeded, client, as_role):
    assert client.get(REPORT).status_code == 401
    assert as_role("customer_support").get(REPORT).status_code == 403
    assert as_role("super_admin").get(REPORT).status_code == 200
    # The public beacon never returns data.
    assert client.get(COLLECT).status_code == 405
