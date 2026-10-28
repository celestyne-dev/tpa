"""Batch 12.2: the overview's lighter summaries match the full module reports exactly,
and the overview issues far fewer queries than computing every full report twice."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select

from app.extensions import db
from app.models import Campaign, Customer, Product, Subscriber, User

from .test_analytics import _seed_views
from .test_commerce_analytics import _order, shop  # noqa: F401
from .test_commerce_checkout import _send_webhook
from .test_learning_analytics import lms  # noqa: F401
from .test_membership_checkout import club  # noqa: F401
from .test_membership_lifecycle import _activate

API = "/api/v1/admin/analytics"
NOW = datetime.now(UTC)
TODAY = NOW.date()


def _windows(end, days):
    """The current range ending on ``end`` and the previous range of the same length."""
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return (
        {"date_from": start.isoformat(), "date_to": end.isoformat()},
        {"date_from": prev_start.isoformat(), "date_to": prev_end.isoformat()},
    )


def _get(api, path, params):
    res = api.get(f"{API}/{path}", query_string=params)
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _pair(metric):
    return metric["value"], metric["previous"]


def _expected(now: dict, before: dict) -> dict:
    """{key: (current, previous)} with 0 where a period has no row for the key."""
    return {k: (now.get(k, 0), before.get(k, 0)) for k in set(now) | set(before)}


def test_website_overview_matches_traffic_report(seeded, as_role):
    rows = []
    for day in (TODAY - timedelta(days=2), TODAY - timedelta(days=3), TODAY - timedelta(days=9)):
        rows += [
            (day, "/about", "page", "", None, "search", {"referrer_host": "google.com"}),
            (day, "/about", "page", "", None, "search", {"referrer_host": "google.com"}),
            (day, "/shop", "shop", "", None, "direct", {"visitor": "d" * 16}),
            (day, "/shop", "shop", "", None, "direct", {"visitor": "d" * 16}),
        ]
    rows.append((TODAY, "/about", "page", "", None, "search", {"referrer_host": "google.com"}))
    _seed_views(seeded, rows)
    from app.services.analytics.rollup import maintain

    with seeded.app_context():
        assert maintain()["rolled_up"] == 3  # today stays raw
    api = as_role("seo_manager")
    cur, prev = _windows(TODAY, 7)
    ov = _get(api, "overview", cur)["sections"]["website"]
    now, before = _get(api, "traffic", cur), _get(api, "traffic", prev)
    assert _pair(ov["page_views"]) == (now["totals"]["views"], before["totals"]["views"])
    assert _pair(ov["visitors_daily_sum"]) == (
        now["totals"]["visitors_daily_sum"],
        before["totals"]["visitors_daily_sum"],
    )
    assert (now["totals"]["views"], before["totals"]["views"]) == (9, 4)
    # Rolled-up source rows are summed across days in SQL: same figures as before.
    sources = {s["source"]: (s["views"], s["visitors"]) for s in now["sources"]}
    assert sources == {"search": (5, 5), "direct": (4, 2)}
    assert now["referrers"] == [{"host": "google.com", "views": 5, "visitors": 5}]
    assert ov["series"] == now["series"]


def test_commerce_overview_matches_commerce_report(shop, as_role):  # noqa: F811
    app, ids = shop
    with app.app_context():
        c = db.session.scalar(select(Customer))
        guide = db.session.get(Product, ids["guide"])
        _order(c, [(guide, 1, 1000)], paid_at=NOW - timedelta(days=10))
        db.session.commit()
    finance = as_role("finance_manager")
    cur, prev = _windows(TODAY, 7)
    for mode in ("live", "test"):
        ov = _get(finance, "overview", cur | {"mode": mode})["sections"]["commerce"]
        now = _get(finance, "commerce", cur | {"mode": mode})
        before = _get(finance, "commerce", prev | {"mode": mode})
        for key in ("gross", "refunds", "net"):
            expected = _expected(
                {c["currency"]: c[key]["amount_minor"] for c in now["currencies"]},
                {c["currency"]: c[key]["amount_minor"] for c in before["currencies"]},
            )
            assert {r["currency"]: _pair(r) for r in ov[key]} == expected, (mode, key)
        assert {r["currency"]: _pair(r) for r in ov["paid_orders"]} == _expected(
            {c["currency"]: c["orders"] for c in now["currencies"]},
            {c["currency"]: c["orders"] for c in before["currencies"]},
        )
        assert ov["top_products"] == [
            {k: p[k] for k in ("title", "currency", "units", "revenue")}
            for p in now["products"][:5]
        ]
        assert ov["other_mode_payments"] == sum(
            m["verified_sales"] for m in now["modes"] if m["mode"] != mode
        )
    live = _get(finance, "overview", cur)["sections"]["commerce"]
    usd = {r["currency"]: _pair(r) for r in live["gross"]}["USD"]
    assert usd == (9100, 1000)


def test_learning_overview_matches_learning_report(lms, as_role):  # noqa: F811
    admin = as_role("administrator")
    cur, prev = _windows(TODAY, 4)  # D2 (2 days ago) now, D1 (5 days ago) before
    ov = _get(admin, "overview", cur)["sections"]["learning"]
    now, before = _get(admin, "learning", cur), _get(admin, "learning", prev)
    for key in ("new_enrollments", "completions", "starts", "active_learners"):
        assert _pair(ov[key]) == (now["period"][key], before["period"][key]), key
    assert ov["current_enrollments"]["value"] == now["current"]["enrollments"]
    assert ov["completion_rate"]["value"] == now["current"]["completion_rate"]
    assert now["period"]["new_enrollments"] or before["period"]["new_enrollments"]


def test_membership_overview_matches_membership_report(club, client, as_role, seeded):  # noqa: F811
    m = _activate(club, client)
    tx = m["paystack"].charge_renewal(m["code"])
    _send_webhook(client, m["paystack"], "charge.success", tx)  # renewal dated in the future
    finance = as_role("finance_manager")
    cur, prev = _windows(TODAY + timedelta(days=60), 61)
    ov = _get(finance, "overview", cur)["sections"]["membership"]
    now, before = _get(finance, "membership", cur), _get(finance, "membership", prev)
    for key in ("new_subscriptions", "renewals"):
        assert _pair(ov[key]) == (now["period"][key], before["period"][key]), key
    assert ov["paid_members"]["value"] == now["current"]["paid_subscribers"] == 1
    assert ov["complimentary"]["value"] == now["current"]["complimentary"]
    for key in ("revenue", "net_revenue"):
        assert {(r["mode"], r["currency"]): _pair(r) for r in ov[key]} == _expected(
            {(r["mode"], r["amount"]["currency"]): r["amount"]["amount_minor"] for r in now[key]},
            {
                (r["mode"], r["amount"]["currency"]): r["amount"]["amount_minor"]
                for r in before[key]
            },
        ), key
    assert [r["value"] for r in ov["mrr_estimate"]] == [r["mrr"] for r in now["recurring_estimate"]]
    assert now["period"]["renewals"] == 1


def _subscriber(email, status, *, created, confirmed=None, unsubscribed=None):
    db.session.add(
        Subscriber(
            public_id=secrets.token_hex(8),
            email=email,
            status=status,
            source="footer",
            created_at=created,
            confirmed_at=confirmed,
            unsubscribed_at=unsubscribed,
        )
    )


def test_audience_overview_matches_audience_report(seeded, as_role):
    recent, older = NOW - timedelta(days=2), NOW - timedelta(days=9)
    with seeded.app_context():
        _subscriber("a@example.com", "subscribed", created=recent, confirmed=recent)
        _subscriber("b@example.com", "pending", created=recent)
        _subscriber("c@example.com", "subscribed", created=older, confirmed=older)
        _subscriber(
            "d@example.com", "unsubscribed", created=older, confirmed=older, unsubscribed=recent
        )
        db.session.add(
            Campaign(
                public_id=secrets.token_hex(8),
                name="Letter",
                status="sent",
                completed_at=recent,
                eligible_count=2,
                send_mode="live",
            )
        )
        db.session.commit()
    api = as_role("newsletter_manager")
    cur, prev = _windows(TODAY, 7)
    ov = _get(api, "overview", cur)["sections"]["audience"]
    now, before = _get(api, "audience", cur), _get(api, "audience", prev)
    for key in ("signups", "new_subscriptions", "unsubscriptions", "campaigns_sent"):
        assert _pair(ov[key]) == (now["period"][key], before["period"][key]), key
    assert ov["subscribed"]["value"] == now["current"]["subscribed"] == 2
    assert _pair(ov["signups"]) == (2, 2) and _pair(ov["unsubscriptions"]) == (1, 0)


def _queries(app, fn) -> int:
    with app.app_context():
        engine = db.engine
        count = 0

        def inc(*_args, **_kwargs):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", inc)
        try:
            fn()
        finally:
            event.remove(engine, "before_cursor_execute", inc)
    return count


def test_overview_issues_far_fewer_queries_than_full_reports(shop, as_role):  # noqa: F811
    app, _ids = shop
    as_role("super_admin")
    from app.services.analytics import overview
    from app.services.analytics.audience import audience_report
    from app.services.analytics.commerce import commerce_report
    from app.services.analytics.learning import learning_report
    from app.services.analytics.membership import membership_analytics
    from app.services.analytics.reports import traffic_report

    cur, prev = _windows(TODAY, 365)

    def actor():
        return db.session.scalar(select(User).order_by(User.id.desc()).limit(1))

    def full_reports_twice():  # what the overview did before Batch 12.2
        user = actor()
        for args in (cur, prev):
            traffic_report(args)
            commerce_report(args | {"mode": "live"})
            learning_report(args, user)
            membership_analytics(args, user)
            audience_report(args)

    def new_overview():
        data = overview.overview_report(cur, actor())
        assert set(data["sections"]) == {
            "website",
            "commerce",
            "learning",
            "membership",
            "audience",
        }

    before = _queries(app, full_reports_twice)
    after = _queries(app, new_overview)
    assert after * 2 < before, (after, before)  # the 12-month trend alone is ~125 queries


# ---- N+1 queries in admin listings ----------------------------------------------------


def test_affiliate_link_list_queries_do_not_grow_with_links(seeded):
    from app.models import AffiliateClickDaily, AffiliateLink
    from app.services.partnerships.affiliates import link_dict, list_links

    def add_links(n, start):
        with seeded.app_context():
            for i in range(start, start + n):
                link = AffiliateLink(
                    slug=f"l{i}", name=f"Link {i}", target_url="https://x.example/"
                )
                db.session.add(link)
                db.session.flush()
                db.session.add(AffiliateClickDaily(link_id=link.id, day=TODAY, clicks=i + 1))
            db.session.commit()

    def listed():
        with seeded.app_context():
            return list_links({})

    add_links(2, 0)
    few = _queries(seeded, listed)
    add_links(6, 2)
    many = _queries(seeded, listed)
    assert few == many  # clicks are summed in one grouped query
    rows = listed()
    assert [r["total_clicks"] for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
    with seeded.app_context():
        one = db.session.scalar(select(AffiliateLink).where(AffiliateLink.slug == "l4"))
        assert link_dict(one)["total_clicks"] == 5  # single-link path unchanged


def test_entitlement_list_queries_do_not_grow_with_rows(shop):  # noqa: F811
    from app.models import Entitlement, EntitlementEvent, Order
    from app.services.commerce.entitlements import entitlement_dict, list_entitlements

    app, _ids = shop
    with app.app_context():
        orders = db.session.scalars(select(Order).order_by(Order.id)).all()

    def grant(batch):
        with app.app_context():
            for oid in batch:
                order = db.session.get(Order, oid)
                item = order.items[0]
                e = Entitlement(
                    grant_key=f"test:{oid}",
                    customer_id=order.customer_id,
                    product_id=item.product_id,
                    order_id=order.id,
                    source="purchase",
                    purchased_versions={},
                )
                db.session.add(e)
                db.session.flush()
                for action in ("granted", "renewed"):
                    db.session.add(EntitlementEvent(entitlement_id=e.id, action=action))
            db.session.commit()

    def listed():
        with app.app_context():
            return list_entitlements({"page": 1, "page_size": 100})

    ids = [o.id for o in orders]
    grant(ids[:2])
    few = _queries(app, listed)
    grant(ids[2:])
    many = _queries(app, listed)
    assert len(ids) > 4 and few == many
    rows, total = listed()
    assert total == len(ids)
    with app.app_context():
        numbers = {o.id: o.number for o in db.session.scalars(select(Order))}
        for row in rows:
            assert row["order_number"] == numbers[row["order_id"]]
            assert [ev["action"] for ev in row["events"]] == ["granted", "renewed"]
        single = entitlement_dict(db.session.scalar(select(Entitlement).limit(1)))
        assert [ev["action"] for ev in single["events"]] == ["granted", "renewed"]
