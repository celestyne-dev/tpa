"""Batch 11.4: membership and audience analytics (aggregates only)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Campaign,
    Customer,
    CustomerSubscription,
    EmailMessage,
    LeadMagnet,
    LeadMagnetClaim,
    Product,
    Subscriber,
)

from .test_commerce_checkout import _key, _send_webhook
from .test_membership_checkout import club  # noqa: F401, F811
from .test_membership_lifecycle import _activate

MEMBERSHIP = "/api/v1/admin/analytics/membership"
AUDIENCE = "/api/v1/admin/analytics/audience"
NOW = datetime.now(UTC)


def _live_sub(app, email, *, interval, amount, cancelling=False):
    """A live-mode paid membership (inserted directly: live billing is disabled)."""
    with app.app_context():
        template = db.session.scalar(select(CustomerSubscription))
        c = Customer(
            public_id=secrets.token_hex(8),
            email=email,
            display_name=email,
            status="active",
            is_test_account=False,
            support_notes="",
        )
        db.session.add(c)
        db.session.flush()
        db.session.add(
            CustomerSubscription(
                public_id=secrets.token_urlsafe(12),
                customer_id=c.id,
                plan_id=template.plan_id,
                price_id=template.price_id,
                provider_plan_id=template.provider_plan_id,
                status="active",
                provider="paystack",
                mode="live",
                interval=interval,
                currency="USD",
                amount_minor=amount,
                idempotency_key=secrets.token_hex(8),
                end_reason="",
                activated_at=NOW,
                current_period_start=NOW,
                current_period_end=NOW + timedelta(days=30),
                cancel_at_period_end=cancelling,
            )
        )
        db.session.commit()


def test_membership_analytics_paid_complimentary_revenue_and_estimates(
    club,  # noqa: F811
    client,
    as_role,
    seeded,
):
    m = _activate(club, client)
    paystack = m["paystack"]
    tx = paystack.charge_renewal(m["code"])
    _send_webhook(client, paystack, "charge.success", tx)  # verified renewal
    with seeded.app_context():
        oid = db.session.scalar(select(CustomerSubscription.order_id))
    finance = as_role("finance_manager")
    refund = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {
            "amount_minor": 300,
            "reason": "Goodwill",
            "revoke_access": False,
            "idempotency_key": _key(),
        },
    ).get_json()["data"]["refund"]
    finance.post(
        f"/api/v1/admin/orders/{oid}/refunds/{refund['id']}/complete",
        {"provider_reference": "RF_1", "confirm": True},
    )
    from .conftest import register_customer

    register_customer(seeded, "guest@example.com")
    with seeded.app_context():
        cid = db.session.scalar(
            select(Customer.public_id).where(Customer.email == "guest@example.com")
        )
    admin = as_role("administrator")
    res = admin.post(
        "/api/v1/admin/membership-grants",
        {
            "customer_id": cid,
            "plan_id": m["plan"]["id"],
            "reason": "Podcast guest",
            "expires_at": (NOW + timedelta(days=30)).date().isoformat(),
            "idempotency_key": _key(),
        },
    )
    assert res.status_code == 201, res.get_json()
    _live_sub(seeded, "live1@example.com", interval="year", amount=12000)
    _live_sub(seeded, "live2@example.com", interval="month", amount=999, cancelling=True)

    data = finance.get(
        MEMBERSHIP,
        # The fake renewal is dated 23 November: include it.
        query_string={
            "date_from": (NOW - timedelta(days=60)).date().isoformat(),
            "date_to": (NOW + timedelta(days=60)).date().isoformat(),
        },
    ).get_json()["data"]
    assert data["current"]["paid_subscribers"] == 3 and data["current"]["complimentary"] == 1
    plans = {(r["interval"], r["mode"]): r["paid_members"] for r in data["by_plan"]}
    assert plans == {("month", "test"): 1, ("month", "live"): 1, ("year", "live"): 1}
    est = {r["mode"]: r for r in data["recurring_estimate"]}
    assert (
        est["test"]["mrr"]["amount_minor"] == 999 and est["test"]["arr"]["amount_minor"] == 999 * 12
    )
    assert (
        est["live"]["mrr"]["amount_minor"] == 1000 and est["live"]["subscriptions"] == 1
    )  # 12000/12
    assert data["recurring_at_risk"] == [
        {"mode": "live", "monthly": data["recurring_at_risk"][0]["monthly"]}
    ]
    assert data["recurring_at_risk"][0]["monthly"]["amount_minor"] == 999  # cancelling, not in MRR
    [rev] = data["revenue_by_plan"]
    assert rev["mode"] == "test" and rev["payments"] == 2
    assert (
        rev["gross"]["amount_minor"],
        rev["refunds"]["amount_minor"],
        rev["net"]["amount_minor"],
    ) == (1998, 300, 1698)
    assert data["revenue"][0]["mode"] == "test"  # realised revenue labelled by mode
    assert data["complimentary_by_plan"][0]["members"] == 1
    assert data["period"]["renewals"] == 1
    assert "mrr" in data["definitions"] and "Estimate" in data["definitions"]["mrr"]
    # Plan filter and date filter.
    filtered = finance.get(
        MEMBERSHIP, query_string={"range": "30d", "plan": m["plan"]["id"]}
    ).get_json()["data"]
    assert filtered["plan"]["id"] == m["plan"]["id"]
    assert finance.get(MEMBERSHIP, query_string={"plan": "nope"}).status_code == 404
    old = finance.get(
        MEMBERSHIP, query_string={"date_from": "2020-01-01", "date_to": "2020-01-31"}
    ).get_json()["data"]
    assert old["revenue"] == [] and old["revenue_by_plan"] == []
    assert "member@example.com" not in str(data) and "guest@example.com" not in str(data)


def _subscriber(
    email, status, *, created, confirmed=None, unsubscribed=None, source="footer", detail=""
):
    db.session.add(
        Subscriber(
            public_id=secrets.token_hex(8),
            email=email,
            status=status,
            source=source,
            source_detail=detail,
            created_at=created,
            confirmed_at=confirmed,
            unsubscribed_at=unsubscribed,
        )
    )


def test_audience_growth_sources_campaigns_and_lead_magnets(seeded, as_role):
    d1, d2, old = NOW - timedelta(days=3), NOW - timedelta(days=1), NOW - timedelta(days=200)
    with seeded.app_context():
        _subscriber("a@example.com", "subscribed", created=d1, confirmed=d1)
        _subscriber(
            "b@example.com",
            "subscribed",
            created=d1,
            confirmed=d2,
            source="lead_magnet",
            detail="calm-kit",
        )
        _subscriber("c@example.com", "pending", created=d2)
        _subscriber("d@example.com", "unsubscribed", created=old, confirmed=old, unsubscribed=d2)
        _subscriber("e@example.com", "subscribed", created=old, confirmed=old, source="import")
        product = db.session.scalar(select(Product))
        magnet = LeadMagnet(
            slug="calm-kit", title="Calm Kit", product_id=product.id, status="active"
        )
        db.session.add(magnet)
        db.session.flush()
        for i in range(2):
            db.session.add(
                LeadMagnetClaim(
                    lead_magnet_id=magnet.id,
                    email=f"x{i}@example.com",
                    token_hash=secrets.token_hex(32),
                    expires_at=NOW + timedelta(days=1),
                    created_at=d1,
                )
            )
        camp = Campaign(
            public_id=secrets.token_hex(8),
            name="October letter",
            status="sent",
            completed_at=d2,
            eligible_count=3,
            send_mode="live",
        )
        db.session.add(camp)
        db.session.flush()
        for i, status in enumerate(("accepted", "delivered", "bounced")):
            db.session.add(
                EmailMessage(
                    kind="campaign",
                    dedupe_key=f"c:{i}",
                    campaign_id=camp.id,
                    to_email=f"r{i}@example.com",
                    status=status,
                )
            )
        db.session.commit()
        campaign_id = camp.public_id

    api = as_role("newsletter_manager")
    data = api.get(AUDIENCE, query_string={"range": "30d"}).get_json()["data"]
    assert data["current"]["subscribed"] == 3 and data["current"]["pending"] == 1
    assert data["period"] == {
        "signups": 3,
        "new_subscriptions": 2,
        "unsubscriptions": 1,
        "net_growth": 1,
        "campaigns_sent": 1,
    }
    assert sum(t["new_subscriptions"] for t in data["trend"]) == 2
    sources = {s["source"]: s for s in data["sources"]}
    assert (
        sources["lead_magnet"]["new_subscriptions"] == 1
        and sources["import"]["subscribed_now"] == 1
    )
    [camp] = data["campaigns"]
    assert (camp["accepted"], camp["delivered_confirmed"], camp["bounced"]) == (3, 1, 1)
    assert data["engagement"]["opens"] is None and data["engagement"]["clicks"] is None
    assert data["engagement"]["delivery_feedback_recorded"] is True
    [lm] = data["lead_magnets"]
    assert (lm["slug"], lm["claims"], lm["confirmed_subscribers"]) == ("calm-kit", 2, 1)
    one = api.get(AUDIENCE, query_string={"campaign": campaign_id}).get_json()["data"]
    assert one["campaign"]["name"] == "October letter" and len(one["campaigns"]) == 1
    past = api.get(
        AUDIENCE, query_string={"date_from": "2020-01-01", "date_to": "2020-01-31"}
    ).get_json()["data"]
    assert past["period"]["new_subscriptions"] == 0 and past["campaigns"] == []
    text = str(data)
    for private in ("a@example.com", "x0@example.com", "r0@example.com"):
        assert private not in text


def test_permissions_per_tab(seeded, as_role, client):
    assert client.get(MEMBERSHIP).status_code == 401 and client.get(AUDIENCE).status_code == 401
    finance, marketing, support = (
        as_role("finance_manager"),
        as_role("marketing_manager"),
        as_role("customer_support"),
    )
    assert finance.get(MEMBERSHIP).status_code == 200 and finance.get(AUDIENCE).status_code == 403
    assert (
        marketing.get(AUDIENCE).status_code == 200 and marketing.get(MEMBERSHIP).status_code == 403
    )
    assert support.get(MEMBERSHIP).status_code == 403 and support.get(AUDIENCE).status_code == 403
    empty = marketing.get(AUDIENCE).get_json()["data"]
    assert empty["campaigns"] == [] and empty["lead_magnets"] == []
