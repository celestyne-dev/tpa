"""Batch 17: memberships priced and charged in KES, card-only automatic renewal.

Runs the production policy (``CHARGE_CURRENCIES = ("KES",)``) with the fake Paystack test
account: KES 650 a month and KES 6,500 a year, set through the CMS (nothing here is a
built-in price).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CustomerSubscription,
    EmailDelivery,
    Entitlement,
    Order,
    SiteSetting,
    SubscriptionEvent,
)

from .conftest import enable_test_checkout, register_customer
from .membership_clock import FIRST_PAYMENT, clock  # noqa: F401
from .test_commerce_catalogue import PRODUCTS
from .test_commerce_checkout import _checkout, _key, _send_webhook
from .test_memberships import PLANS, PUBLIC, _eligible, _plan, _publish

ACCOUNT = "/api/v1/account/membership"
FIRST_END = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)  # the fake's first charge: 23 Oct


def _price(api, plan, interval, amount, currency=None):
    body = {"interval": interval, "amount": amount, "lock_version": plan["lock_version"]}
    if currency:
        body["currency"] = currency
    return api.post(f"{PLANS}/{plan['id']}/prices", body)


@pytest.fixture()
def kclub(seeded, as_role, paystack, clock):  # noqa: F811
    seeded.config["CHARGE_CURRENCIES"] = ("KES",)
    admin = as_role("super_admin", email="owner@example.org")
    guide = _eligible(admin, "Calm Guide")
    plan = _plan(
        admin,
        tagline="Everything you need for calmer days",
        description="Members read every premium guide.",
        benefits=["All premium guides"],
    )
    for interval, amount in (("month", "650"), ("year", "6500")):
        res = _price(admin, plan, interval, amount)
        assert res.status_code == 201, res.get_json()
        plan = res.get_json()["data"]
    res = admin.put(
        f"{PLANS}/{plan['id']}/access",
        {"product_ids": [guide["public_id"]], "lock_version": plan["lock_version"]},
    )
    plan = res.get_json()["data"]
    plan = _publish(admin, plan).get_json()["data"]
    enable_test_checkout(seeded, ("KES",))
    seeded.config["MEMBERSHIP_BILLING_MODE"] = "test"
    res = admin.post(f"{PLANS}/{plan['id']}/provider-sync", {"lock_version": plan["lock_version"]})
    assert res.status_code == 200, res.get_json()
    member = register_customer(seeded, "member@example.com")
    prices = {p["interval"]: p for p in member.get(PUBLIC).get_json()["data"]["plans"][0]["prices"]}
    return {
        "app": seeded,
        "admin": admin,
        "guide": guide,
        "plan": res.get_json()["data"],
        "prices": prices,
        "member": member,
        "paystack": paystack,
        "clock": clock,
    }


def _join(k, interval="month", **override):
    price = k["prices"][interval]
    body = {
        "price_id": price["id"],
        "idempotency_key": _key(),
        "expected_amount_minor": price["price"]["amount_minor"],
        "currency": price["price"]["currency"],
        "accept_terms": True,
    } | override
    return k["member"].post(f"{ACCOUNT}/checkout", body)


def _sub(k):
    with k["app"].app_context():
        sub = db.session.scalar(
            select(CustomerSubscription).order_by(CustomerSubscription.id.desc())
        )
        db.session.expunge(sub)
        return sub


def _reference(k):
    with k["app"].app_context():
        sub = db.session.scalar(
            select(CustomerSubscription).order_by(CustomerSubscription.id.desc())
        )
        return db.session.get(Order, sub.order_id).attempts[-1].reference


def _view(k):
    return k["member"].get(ACCOUNT).get_json()["data"]


def _events(k, type_):
    with k["app"].app_context():
        return db.session.scalars(
            select(SubscriptionEvent).where(SubscriptionEvent.type == type_)
        ).all()


def _templates(k):
    with k["app"].app_context():
        return [e.template for e in db.session.scalars(select(EmailDelivery))]


def _membership_ents(k):
    with k["app"].app_context():
        rows = db.session.scalars(select(Entitlement).where(Entitlement.source == "membership"))
        return [(e.status, e.expires_at) for e in rows]


def _activate(k, client, interval="month", **pay):
    """First payment verified on return, then Paystack's subscription.create webhook."""
    sub_id = _join(k, interval).get_json()["data"]["subscription"]["id"]
    ref = _reference(k)
    k["paystack"].pay(ref, **pay)
    assert k["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id}).status_code == 200
    remote = k["paystack"].subscribe(ref, email="member@example.com")
    assert _send_webhook(client, k["paystack"], "subscription.create", remote).status_code == 200
    return sub_id, remote["subscription_code"], ref


def _reconcile(k):
    from app.services.memberships.lifecycle import reconcile

    with k["app"].app_context():
        return reconcile(check_provider=False)


# ---- prices and Paystack plans ------------------------------------------------------------


def test_kes_prices_come_from_the_cms_and_sync_kes_paystack_plans(kclub):
    k = kclub
    assert k["prices"]["month"]["price"]["formatted"] == "KES 650.00"
    assert k["prices"]["year"]["price"]["formatted"] == "KES 6,500.00"
    detail = k["admin"].get(f"{PLANS}/{k['plan']['id']}").get_json()["data"]
    assert detail["price_currency"] == "KES"
    # USD prices can't be added: memberships charge in KES only.
    res = _price(k["admin"], detail, "month", "5.00", currency="USD")
    assert res.status_code == 400 and "KES" in str(res.get_json()["error"]["details"])
    plans = sorted(k["paystack"].plans.values(), key=lambda p: p["amount"])
    assert [(p["amount"], p["currency"], p["interval"]) for p in plans] == [
        (65000, "KES", "monthly"),
        (650000, "KES", "annually"),
    ]
    assert all(pp["verified_at"] for pp in detail["provider_plans"])
    # A new price is a new immutable version (the old one is retired, never edited).
    res = _price(k["admin"], detail, "month", "700")
    assert res.status_code == 201
    history = res.get_json()["data"]["price_history"]
    assert [(p["price"]["formatted"], p["status"]) for p in history if p["interval"] == "month"][
        :2
    ] == [("KES 700.00", "active"), ("KES 650.00", "retired")]


@pytest.mark.parametrize(("interval", "amount"), [("month", 65000), ("year", 650000)])
def test_monthly_and_yearly_checkout_charges_the_kes_plan_by_card_only(kclub, interval, amount):
    k = kclub
    res = _join(k, interval)
    assert res.status_code == 201, res.get_json()
    [init] = [b for _, path, b in k["paystack"].calls if path == "/transaction/initialize"]
    assert init["currency"] == "KES" and int(init["amount"]) == amount
    assert init["plan"] == next(
        pp["plan_code"] for pp in k["plan"]["provider_plans"] if pp["interval"] == interval
    )
    assert init["channels"] == ["card"]  # no M-Pesa for automatic renewals


def test_checkout_refuses_another_currency_or_a_changed_amount(kclub):
    res = _join(kclub, currency="USD")
    assert res.status_code == 400 and "currency" in res.get_json()["error"]["details"]
    res = _join(kclub, expected_amount_minor=1)
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "price_changed"
    assert not [c for c in kclub["paystack"].calls if c[1] == "/transaction/initialize"]


def test_membership_needs_a_confirmed_account(kclub, client):
    stranger = register_customer(kclub["app"], "new@example.com", verify=False)
    res = stranger.post(
        f"{ACCOUNT}/checkout",
        {
            "price_id": kclub["prices"]["month"]["id"],
            "idempotency_key": _key(),
            "expected_amount_minor": 65000,
            "currency": "KES",
            "accept_terms": True,
        },
    )
    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "email_verification_required"
    assert client.post(f"{ACCOUNT}/checkout", json={}).status_code == 401


# ---- first payment and automatic renewal ---------------------------------------------------


def test_reusable_card_and_linked_subscription_confirm_automatic_renewal(kclub, client):
    k = kclub
    sub_id, code, ref = _activate(k, client)
    view = _view(k)["subscription"]
    assert view["status"] == "active" and view["renewal"] == "automatic"
    assert view["renews_on"] == view["current_period_end"]
    assert view["price"]["formatted"] == "KES 650.00"
    # Repeated returns and webhooks change nothing.
    for _ in range(2):
        k["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
        tx = k["paystack"].transactions[ref]
        assert _send_webhook(client, k["paystack"], "charge.success", tx).status_code == 200
        remote = k["paystack"].subscriptions[code]
        _send_webhook(client, k["paystack"], "subscription.create", remote)
    with k["app"].app_context():
        assert db.session.scalar(select(db.func.count(CustomerSubscription.id))) == 1
        assert db.session.scalar(select(db.func.count(Order.id))) == 1
    assert len(_events(k, "activated")) == 1
    assert len(_events(k, "recurring_confirmed")) == 1
    assert len(_membership_ents(k)) == 1
    assert _templates(k).count("membership_activated") == 1


@pytest.mark.parametrize(
    "pay", [{"channel": "mobile_money"}, {"reusable": False}], ids=["mpesa", "not_reusable"]
)
def test_payment_that_cannot_renew_honours_the_period_but_never_renews(kclub, client, pay):
    k = kclub
    sub_id = _join(k).get_json()["data"]["subscription"]["id"]
    ref = _reference(k)
    k["paystack"].pay(ref, **pay)
    k["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    view = _view(k)["subscription"]
    # Paid, so the period is honoured, but it is clearly not renewing.
    assert view["status"] == "active" and view["renewal"] == "unavailable"
    assert view["cancel_at_period_end"] is True and view["renews_on"] is None
    assert len(_membership_ents(k)) == 1
    assert "membership_recurring_unavailable" in _templates(k)
    with k["app"].app_context():
        order = db.session.scalar(select(Order))
        assert order.needs_review and "can't renew automatically" in order.review_reason
    # If Paystack creates a subscription anyway, it is disabled at once: no charge follows.
    remote = k["paystack"].subscribe(ref, email="member@example.com")
    _send_webhook(client, k["paystack"], "subscription.create", remote)
    assert k["paystack"].subscriptions[remote["subscription_code"]]["status"] == "non-renewing"
    assert _view(k)["subscription"]["renewal"] == "unavailable"
    # At the end of the paid period the membership ends and its access with it.
    k["clock"].set(FIRST_END + timedelta(hours=1))
    _reconcile(k)
    assert _sub(k).status == "ended"
    assert [s for s, _ in _membership_ents(k)] == ["revoked"]


def test_missing_subscription_confirmation_is_handled_safely(kclub, client):
    k = kclub
    sub_id = _join(k).get_json()["data"]["subscription"]["id"]
    k["paystack"].pay(_reference(k))
    k["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    assert _view(k)["subscription"]["renewal"] == "setting_up"  # webhook not here yet
    k["clock"].set(FIRST_PAYMENT + timedelta(hours=2))
    assert _reconcile(k)["recurring_unavailable"] == 0
    assert _view(k)["subscription"]["renewal"] == "setting_up"
    k["clock"].set(FIRST_PAYMENT + timedelta(hours=25))
    assert _reconcile(k)["recurring_unavailable"] == 1
    view = _view(k)["subscription"]
    assert view["renewal"] == "unavailable" and view["status"] == "active"
    assert "membership_recurring_unavailable" in _templates(k)
    assert _reconcile(k)["recurring_unavailable"] == 0  # once


@pytest.mark.parametrize("tamper", [{"amount": 64999}, {"currency": "USD"}])
def test_wrong_amount_or_currency_never_activates(kclub, client, tamper):
    k = kclub
    sub_id = _join(k).get_json()["data"]["subscription"]["id"]
    ref = _reference(k)
    tx = k["paystack"].pay(ref, **tamper)
    k["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    _send_webhook(client, k["paystack"], "charge.success", tx)
    assert _sub(k).status != "active"
    assert _membership_ents(k) == []


# ---- renewals, failures and cancellation ----------------------------------------------------


def test_successful_kes_renewal_extends_once(kclub, client):
    k = kclub
    _, code, _ = _activate(k, client)
    tx = k["paystack"].charge_renewal(code)
    assert tx["currency"] == "KES" and tx["amount"] == 65000
    assert _send_webhook(client, k["paystack"], "charge.success", tx).status_code == 200
    assert _send_webhook(client, k["paystack"], "charge.success", tx).get_json()["data"] == {
        "status": "duplicate"
    }
    sub = _sub(k)
    second_end = datetime(2026, 12, 23, 10, 0, tzinfo=UTC)
    assert sub.status == "active"
    assert sub.current_period_end.replace(tzinfo=UTC) == second_end
    assert _view(k)["subscription"]["renews_on"].startswith("2026-12-23")
    [(status, expires)] = _membership_ents(k)
    assert status == "active" and expires.replace(tzinfo=UTC) == second_end
    # A renewal in the wrong currency is never accepted.
    bad = k["paystack"].charge_renewal(code)
    k["paystack"].transactions[bad["reference"]]["currency"] = "USD"
    bad["currency"] = "USD"
    _send_webhook(client, k["paystack"], "charge.success", bad)
    assert _sub(k).current_period_end.replace(tzinfo=UTC) == second_end


def test_failed_renewal_grace_then_expiry(kclub, client):
    k = kclub
    _, code, _ = _activate(k, client)
    failed = {
        "invoice_code": "INV_k1",
        "status": "failed",
        "paid": False,
        "subscription": {"subscription_code": code},
        "domain": "test",
    }
    k["clock"].set(datetime(2026, 11, 22, tzinfo=UTC))
    assert _send_webhook(client, k["paystack"], "invoice.payment_failed", failed).status_code == 200
    assert _sub(k).status == "past_due"
    k["clock"].set(FIRST_END + timedelta(hours=12))
    _reconcile(k)
    assert _sub(k).status == "grace"
    assert [s for s, _ in _membership_ents(k)] == ["active"]  # access during grace
    k["clock"].set(FIRST_END + timedelta(days=4))
    _reconcile(k)
    sub = _sub(k)
    assert (sub.status, sub.end_reason) == ("ended", "payment_failed")
    assert [s for s, _ in _membership_ents(k)] == ["revoked"]


def test_cancellation_keeps_paid_access_then_entitlements_expire(kclub, client):
    k = kclub
    sub_id, code, _ = _activate(k, client)
    data = k["member"].post(f"{ACCOUNT}/cancel", {"subscription_id": sub_id}).get_json()["data"]
    assert data["subscription"]["renewal"] == "cancelled"
    assert k["paystack"].subscriptions[code]["status"] == "non-renewing"
    library = k["member"].get("/api/v1/account/library").get_json()["data"]
    assert [bool(i["files"]) for i in library] == [True]  # the paid time continues
    k["clock"].set(FIRST_END + timedelta(minutes=5))
    _reconcile(k)
    assert _sub(k).status == "ended"
    assert [s for s, _ in _membership_ents(k)] == ["revoked"]
    library = k["member"].get("/api/v1/account/library").get_json()["data"]
    assert all(not i["files"] for i in library)  # nothing can be downloaded any more


# ---- one-time purchases are unaffected -----------------------------------------------------


def test_one_time_purchases_keep_every_payment_method(kclub, client):
    k = kclub
    with k["app"].app_context():
        record = db.session.get(SiteSetting, "payments.channels") or SiteSetting(
            key="payments.channels"
        )
        record.value = ["card", "mobile_money"]
        db.session.add(record)
        db.session.commit()
    res = k["admin"].post(
        f"{PRODUCTS}/{k['guide']['id']}/prices", {"currency": "KES", "amount_minor": 195000}
    )
    assert res.status_code == 201, res.get_json()
    shopper = register_customer(k["app"], "buyer@example.com")
    res = _checkout(shopper, [k["guide"]["public_id"]], currency="KES", expected=195000)
    assert res.status_code == 201, res.get_json()
    init = [b for _, path, b in k["paystack"].calls if path == "/transaction/initialize"][-1]
    assert init["channels"] == ["card", "mobile_money"] and "plan" not in init
    # Memberships stay card-only on the same site.
    _join(k)
    init = [b for _, path, b in k["paystack"].calls if path == "/transaction/initialize"][-1]
    assert init["channels"] == ["card"]
