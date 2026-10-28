"""Batch 10.2: test-mode subscription checkout and verified first-payment activation."""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CustomerSubscription,
    EmailDelivery,
    Entitlement,
    Order,
    SubscriptionEvent,
    SubscriptionPeriod,
)

from .conftest import enable_test_checkout, register_customer
from .test_commerce_checkout import _checkout, _send_webhook
from .test_memberships import PLANS, PUBLIC, _eligible, _publish, _ready_plan

ACCOUNT = "/api/v1/account/membership"


def _key():
    return secrets.token_hex(16)


@pytest.fixture()
def club(seeded, as_role, paystack):
    """A published plan synced with the (fake) Paystack test account, billing open in
    test mode, and a verified test customer."""
    admin = as_role("super_admin", email="owner@example.org")
    guide = _eligible(admin, "Calm Guide")
    plan = _ready_plan(admin, guide)
    plan = _publish(admin, plan).get_json()["data"]
    enable_test_checkout(seeded, ("USD",))
    seeded.config["MEMBERSHIP_BILLING_MODE"] = "test"
    res = admin.post(f"{PLANS}/{plan['id']}/provider-sync", {"lock_version": plan["lock_version"]})
    assert res.status_code == 200, res.get_json()
    plan = res.get_json()["data"]
    member = register_customer(seeded, "member@example.com")
    public = member.get(PUBLIC).get_json()["data"]
    price = next(p for p in public["plans"][0]["prices"] if p["interval"] == "month")
    return {
        "app": seeded,
        "admin": admin,
        "guide": guide,
        "plan": plan,
        "price": price,
        "member": member,
        "paystack": paystack,
    }


def _join(club, shopper=None, key=None, expected=None):
    return (shopper or club["member"]).post(
        f"{ACCOUNT}/checkout",
        {
            "price_id": club["price"]["id"],
            "idempotency_key": key or _key(),
            "expected_amount_minor": club["price"]["price"]["amount_minor"]
            if expected is None
            else expected,
            "currency": "USD",
            "accept_terms": True,
        },
    )


def _reference(club, sub_id):
    with club["app"].app_context():
        sub = db.session.scalar(
            select(CustomerSubscription).where(CustomerSubscription.public_id == sub_id)
        )
        order = db.session.get(Order, sub.order_id)
        return order.attempts[-1].reference


def _membership_entitlements(club):
    with club["app"].app_context():
        return db.session.scalars(
            select(Entitlement).where(Entitlement.source == "membership")
        ).all()


def test_checkout_is_closed_until_billing_is_verified_and_enabled(seeded, as_role, paystack):
    admin = as_role("super_admin", email="owner@example.org")
    guide = _eligible(admin, "Calm Guide")
    plan = _publish(admin, _ready_plan(admin, guide)).get_json()["data"]
    member = register_customer(seeded, "member@example.com")
    data = member.get(PUBLIC).get_json()["data"]
    assert data["billing"]["available"] is False and data["billing"]["status"] == "coming_soon"
    price = data["plans"][0]["prices"][0]
    res = member.post(
        f"{ACCOUNT}/checkout",
        {
            "price_id": price["id"],
            "idempotency_key": _key(),
            "expected_amount_minor": price["price"]["amount_minor"],
            "currency": "USD",
            "accept_terms": True,
        },
    )
    assert res.status_code == 409 and res.get_json()["error"]["code"] == (
        "membership_checkout_unavailable"
    )
    # Even with the flag set, checkout stays closed while USD/test checkout isn't enabled.
    seeded.config["MEMBERSHIP_BILLING_MODE"] = "test"
    assert member.get(PUBLIC).get_json()["data"]["billing"]["available"] is False
    seeded.config["MEMBERSHIP_BILLING_MODE"] = "live"  # never supported
    enable_test_checkout(seeded, ("USD",))
    assert member.get(PUBLIC).get_json()["data"]["billing"]["available"] is False
    # Provider sync refuses a live key; here the key is a test key, so it works.
    seeded.config["MEMBERSHIP_BILLING_MODE"] = "test"
    res = admin.post(f"{PLANS}/{plan['id']}/provider-sync", {"lock_version": plan["lock_version"]})
    assert res.status_code == 200
    assert res.get_json()["data"]["provider_plans"][0]["mode"] == "test"
    assert not paystack.transactions  # nothing was charged or initialised


def test_verified_first_payment_activates_once_and_grants_membership_access(club, client):
    member, paystack = club["member"], club["paystack"]
    key = _key()
    res = _join(club, key=key)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    sub_id = data["subscription"]["id"]
    assert data["subscription"]["status"] == "pending" and data["checkout_url"].startswith(
        "https://checkout.paystack.com/"
    )
    ref = _reference(club, sub_id)
    plan_code = club["plan"]["provider_plans"][0]["plan_code"]
    init = next(c for c in paystack.calls if c[1] == "/transaction/initialize")
    assert init[2]["plan"] == plan_code and init[2]["callback_url"].endswith(
        f"/account/membership?subscription={sub_id}"
    )
    # Local records exist before payment; no access yet.
    with club["app"].app_context():
        sub = db.session.scalar(select(CustomerSubscription))
        order = db.session.get(Order, sub.order_id)
        assert (order.kind, order.status, order.items[0].product_type) == (
            "subscription",
            "awaiting_payment",
            "membership",
        )
        period = db.session.scalar(select(SubscriptionPeriod))
        assert (period.sequence, period.status) == (1, "pending")
    assert _membership_entitlements(club) == []

    # Retries and second tabs resume the same checkout (no duplicates).
    again = _join(club, key=key)
    assert (
        again.status_code == 200
        and again.get_json()["data"]["checkout_url"] == data["checkout_url"]
    )
    other_tab = _join(club)
    assert other_tab.status_code == 200
    assert other_tab.get_json()["data"]["subscription"]["id"] == sub_id
    with club["app"].app_context():
        assert db.session.query(CustomerSubscription).count() == 1

    # The return page proves nothing until Paystack confirms the payment.
    res = member.post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    assert res.get_json()["data"]["outcome"] == "pending"
    assert res.get_json()["data"]["subscription"]["status"] == "pending"

    paystack.pay(ref)
    res = member.post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    data = res.get_json()["data"]
    assert data["outcome"] == "paid" and data["subscription"]["status"] == "active"
    assert data["subscription"]["test_mode"] is True
    assert [i["title"] for i in data["included"]] == ["Calm Guide"]
    [ent] = _membership_entitlements(club)
    assert ent.expires_at is not None and ent.grant_key.startswith("membership:subscription-")

    # The webhook for the same charge (and a replay) changes nothing.
    tx = paystack.transactions[ref]
    assert _send_webhook(client, paystack, "charge.success", tx).status_code == 200
    assert _send_webhook(client, paystack, "charge.success", tx).get_json()["data"] == {
        "status": "duplicate"
    }
    assert len(_membership_entitlements(club)) == 1
    with club["app"].app_context():
        activations = db.session.scalars(
            select(SubscriptionEvent).where(SubscriptionEvent.type == "activated")
        ).all()
        assert len(activations) == 1
        templates = {e.template for e in db.session.scalars(select(EmailDelivery))}
        assert {"membership_activated", "payment_received"} <= templates
        assert "download_instructions" not in templates
        period = db.session.scalar(select(SubscriptionPeriod))
        assert period.status == "paid" and period.period_end is not None

    view = member.get(ACCOUNT).get_json()["data"]
    assert view["subscription"]["status"] == "active"
    assert {e["type"] for e in view["events"]} >= {"checkout_started", "activated"}
    res = _join(club)
    assert res.status_code == 409 and res.get_json()["error"]["details"]["code"] == "already_member"


def test_subscription_webhook_links_but_never_activates_and_out_of_order_charge_works(club, client):
    member, paystack = club["member"], club["paystack"]
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    ref = _reference(club, sub_id)
    paystack.pay(ref)
    remote = paystack.subscribe(ref, email="member@example.com")
    # subscription.create arrives first: the code is linked, nothing is activated.
    res = _send_webhook(client, paystack, "subscription.create", remote)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "processed"
    assert _send_webhook(client, paystack, "subscription.create", remote).get_json()["data"] == {
        "status": "duplicate"
    }
    with club["app"].app_context():
        sub = db.session.scalar(select(CustomerSubscription))
        assert sub.status == "pending"
        assert sub.provider_subscription_code == remote["subscription_code"]
        assert sub.provider_email_token == remote["email_token"]
    assert _membership_entitlements(club) == []
    # Then the charge webhook activates (verified with Paystack first).
    tx = paystack.transactions[ref]
    assert _send_webhook(client, paystack, "charge.success", tx).status_code == 200
    assert member.get(ACCOUNT).get_json()["data"]["subscription"]["status"] == "active"
    assert len(_membership_entitlements(club)) == 1


@pytest.mark.parametrize(
    "tamper",
    [
        {"amount": 1},
        {"currency": "KES"},
        {"domain": "live"},
        {"plan": "PLN_other"},
    ],
)
def test_mismatched_payments_never_activate(club, tamper):
    member, paystack = club["member"], club["paystack"]
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    ref = _reference(club, sub_id)
    paystack.pay(ref)
    paystack.transactions[ref].update(tamper)
    data = member.post(f"{ACCOUNT}/verify", {"subscription_id": sub_id}).get_json()["data"]
    assert data["outcome"] == "mismatch" and data["subscription"]["status"] == "pending"
    assert _membership_entitlements(club) == []
    with club["app"].app_context():
        order = db.session.scalar(select(Order).where(Order.kind == "subscription"))
        assert order.needs_review and order.status == "awaiting_payment"


def test_checkout_rules_price_integrity_and_privacy(club, seeded):
    member = club["member"]
    res = _join(club, expected=1)
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "price_changed"
    bad = member.post(f"{ACCOUNT}/checkout", {"price_id": club["price"]["id"]})
    assert bad.status_code == 400
    res = _join(club, shopper=register_customer(seeded, "new@example.com", verify=False))
    assert res.status_code == 403 and res.get_json()["error"]["code"] == (
        "email_verification_required"
    )
    # Test-mode checkout is limited to test accounts.
    real = register_customer(seeded, "real@example.com", test_account=False)
    res = _join(club, shopper=real)
    assert res.status_code == 409

    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    other = register_customer(seeded, "other@example.com")
    assert other.post(f"{ACCOUNT}/verify", {"subscription_id": sub_id}).status_code == 404
    assert other.get(ACCOUNT).get_json()["data"]["subscription"] is None
    assert club["app"].test_client().get(ACCOUNT).status_code == 401


def test_provider_plan_drift_blocks_checkout(club):
    plan_code = club["plan"]["provider_plans"][0]["plan_code"]
    club["paystack"].plans[plan_code]["amount"] = 1
    res = _join(club)
    assert res.status_code == 409 and res.get_json()["error"]["code"] == (
        "membership_checkout_unavailable"
    )
    plan = club["admin"].get(f"{PLANS}/{club['plan']['id']}").get_json()["data"]
    res = club["admin"].post(
        f"{PLANS}/{plan['id']}/provider-sync", {"lock_version": plan["lock_version"]}
    )
    assert res.status_code == 409


def test_separate_purchases_are_preserved(club, client):
    member, paystack = club["member"], club["paystack"]
    res = _checkout(member, [club["guide"]["public_id"]])
    assert res.status_code == 201, res.get_json()
    order = res.get_json()["data"]["order"]
    paystack.pay(order["payment"]["reference"])
    _send_webhook(
        client, paystack, "charge.success", paystack.transactions[order["payment"]["reference"]]
    )
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    paystack.pay(_reference(club, sub_id))
    member.post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    with club["app"].app_context():
        rows = db.session.scalars(
            select(Entitlement).where(Entitlement.product_id == club["guide"]["id"])
        ).all()
        assert sorted(r.source for r in rows) == ["membership", "purchase"]
        purchase = next(r for r in rows if r.source == "purchase")
        assert purchase.status == "active" and purchase.expires_at is None
