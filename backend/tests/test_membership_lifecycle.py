"""Batch 10.3: renewals, failed payments, grace, cancellation, reconciliation, refunds."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CustomerSubscription,
    EmailDelivery,
    Entitlement,
    Order,
    PaymentEvent,
    SubscriptionEvent,
    SubscriptionPeriod,
)

from .test_commerce_checkout import _checkout, _key, _send_webhook
from .test_membership_checkout import ACCOUNT, _join, _reference, club  # noqa: F401

FIRST_END = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)  # first charge paid 23 Oct


def _activate(club, client):  # noqa: F811
    """An active, Paystack-linked member (first payment verified, subscription.create seen)."""
    paystack = club["paystack"]
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    ref = _reference(club, sub_id)
    paystack.pay(ref)
    club["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    remote = paystack.subscribe(ref, email="member@example.com")
    assert _send_webhook(client, paystack, "subscription.create", remote).status_code == 200
    return club | {"sub_id": sub_id, "code": remote["subscription_code"], "client": client}


@pytest.fixture()
def member(club, client):  # noqa: F811
    return _activate(club, client)


def _sub(m):
    with m["app"].app_context():
        sub = db.session.scalar(
            select(CustomerSubscription).where(CustomerSubscription.public_id == m["sub_id"])
        )
        db.session.expunge(sub)
        return sub


def _ents(m, source="membership"):
    with m["app"].app_context():
        rows = db.session.scalars(select(Entitlement).where(Entitlement.source == source)).all()
        for r in rows:
            db.session.expunge(r)
        return rows


def _templates(m):
    with m["app"].app_context():
        return [e.template for e in db.session.scalars(select(EmailDelivery))]


def _events(m):
    with m["app"].app_context():
        return [e.type for e in db.session.scalars(select(SubscriptionEvent))]


def _at(monkeypatch, when):
    import app.services.memberships.lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "_now", lambda: when)


def _reconcile(m, **kwargs):
    from app.services.memberships.lifecycle import reconcile

    with m["app"].app_context():
        return reconcile(**kwargs)


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=UTC)


def test_verified_renewal_adds_one_period_and_extends_access_once(member):
    m, paystack, client = member, member["paystack"], member["client"]
    assert _aware(_sub(m).current_period_end) == FIRST_END
    tx = paystack.charge_renewal(m["code"])
    res = _send_webhook(client, paystack, "charge.success", tx)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "processed"
    sub = _sub(m)
    second_end = datetime(2026, 12, 23, 10, 0, tzinfo=UTC)
    assert sub.status == "active" and _aware(sub.current_period_end) == second_end
    [ent] = _ents(m)
    assert _aware(ent.expires_at) == second_end
    # Replays, a different delivery of the same charge and the paid invoice change nothing.
    assert _send_webhook(client, paystack, "charge.success", tx).get_json()["data"] == {
        "status": "duplicate"
    }
    invoice = {
        "invoice_code": "INV_1",
        "status": "success",
        "paid": True,
        "subscription": {"subscription_code": m["code"]},
        "transaction": {"reference": tx["reference"]},
        "domain": "test",
    }
    assert _send_webhook(client, paystack, "invoice.update", invoice).status_code == 200
    from app.services.commerce.payments import get_provider
    from app.services.memberships.lifecycle import renew

    with m["app"].app_context():
        live = db.session.get(CustomerSubscription, sub.id)
        assert renew(live, get_provider().verify(tx["reference"]))[1] == "Renewal already recorded."
        periods = db.session.scalars(
            select(SubscriptionPeriod).order_by(SubscriptionPeriod.sequence)
        ).all()
        assert [(p.sequence, p.status) for p in periods] == [(1, "paid"), (2, "paid")]
        renewal = db.session.get(Order, periods[1].order_id)
        assert (renewal.kind, renewal.status, renewal.total_minor) == ("subscription", "paid", 999)
    assert _templates(m).count("membership_renewed") == 1
    assert _events(m).count("renewed") == 1
    view = m["member"].get(ACCOUNT).get_json()["data"]
    assert [p["sequence"] for p in view["periods"]] == [2, 1]
    assert view["periods"][0]["order"] is not None


@pytest.mark.parametrize("tamper", [{"amount": 1}, {"domain": "live"}, {"currency": "NGN"}])
def test_mismatched_renewal_is_flagged_and_never_extends(member, tamper):
    m, paystack = member, member["paystack"]
    tx = paystack.charge_renewal(m["code"])
    paystack.transactions[tx["reference"]].update(tamper)
    res = _send_webhook(m["client"], paystack, "charge.success", tx)
    assert res.get_json()["data"]["status"] == "rejected"
    assert _aware(_sub(m).current_period_end) == FIRST_END
    assert _aware(_ents(m)[0].expires_at) == FIRST_END
    with m["app"].app_context():
        order = db.session.scalars(select(Order).order_by(Order.id.desc())).first()
        assert order.needs_review and order.status == "awaiting_payment"


def test_unknown_events_and_foreign_charges_are_never_payments(member):
    m, paystack, client = member, member["paystack"], member["client"]
    weird = {"id": 1, "reference": "nope", "status": "success", "amount": 999999, "domain": "test"}
    assert _send_webhook(client, paystack, "transfer.success", weird).get_json()["data"] == {
        "status": "ignored"
    }
    assert _send_webhook(client, paystack, "charge.success", weird).get_json()["data"] == {
        "status": "ignored"
    }
    # A verified charge on our plan by another Paystack customer is not this member's renewal.
    tx = paystack.charge_renewal(m["code"])
    paystack.transactions[tx["reference"]]["customer"] = {"customer_code": "CUS_stranger"}
    stranger = dict(tx, customer={"customer_code": "CUS_stranger"})
    data = _send_webhook(client, paystack, "charge.success", stranger).get_json()["data"]
    assert data["status"] == "rejected"
    assert _aware(_sub(m).current_period_end) == FIRST_END


def test_failed_payment_grace_then_expiry_preserves_purchases(club, client, monkeypatch):  # noqa: F811
    paystack = club["paystack"]
    # A separately purchased copy of the included guide (bought before joining).
    order = _checkout(club["member"], [club["guide"]["public_id"]]).get_json()["data"]["order"]
    paystack.pay(order["payment"]["reference"])
    _send_webhook(
        client, paystack, "charge.success", paystack.transactions[order["payment"]["reference"]]
    )
    m = _activate(club, client)
    failed = {
        "invoice_code": "INV_f1",
        "status": "failed",
        "paid": False,
        "subscription": {"subscription_code": m["code"]},
        "domain": "test",
    }
    # A stale failure (current period still well in the future) is ignored.
    _at(monkeypatch, datetime(2026, 11, 1, tzinfo=UTC))
    _send_webhook(client, paystack, "invoice.payment_failed", failed)
    assert _sub(m).status == "active"

    _at(monkeypatch, datetime(2026, 11, 22, tzinfo=UTC))
    failed["invoice_code"] = "INV_f2"
    assert _send_webhook(client, paystack, "invoice.payment_failed", failed).status_code == 200
    sub = _sub(m)
    grace_end = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)  # period end + 3 days
    assert sub.status == "past_due" and _aware(sub.access_until) == grace_end
    assert _aware(_ents(m)[0].expires_at) == grace_end
    assert "membership_payment_failed" in _templates(m)

    # Reconciliation moves into grace after the paid period and never stretches it.
    _at(monkeypatch, datetime(2026, 11, 24, tzinfo=UTC))
    _reconcile(m)
    _reconcile(m)
    sub = _sub(m)
    assert sub.status == "grace" and _aware(sub.access_until) == grace_end

    _at(monkeypatch, datetime(2026, 11, 27, tzinfo=UTC))
    counts = _reconcile(m)
    assert counts["ended"] == 1
    sub = _sub(m)
    assert (sub.status, sub.end_reason) == ("ended", "payment_failed")
    assert [e.status for e in _ents(m)] == ["revoked"]
    assert [e.status for e in _ents(m, "purchase")] == ["active"]
    assert paystack.subscriptions[m["code"]]["status"] == "non-renewing"  # charges stopped
    assert "membership_ended" in _templates(m)

    # A late renewal for the ended membership is flagged, not silently reactivated.
    tx = paystack.charge_renewal(m["code"])
    _send_webhook(client, paystack, "charge.success", tx)
    assert _sub(m).status == "ended"
    with m["app"].app_context():
        late = db.session.scalars(select(Order).order_by(Order.id.desc())).first()
        assert late.status == "paid" and late.needs_review


def test_reconcile_without_events_starts_grace_even_if_paystack_is_down(member, monkeypatch):
    m, paystack = member, member["paystack"]
    _at(monkeypatch, datetime(2026, 11, 24, tzinfo=UTC))

    def down(*_a, **_k):
        from app.payments.base import ProviderError

        raise ProviderError("Paystack could not be reached. Please try again.")

    monkeypatch.setattr(paystack.provider, "fetch_subscription", down)
    counts = _reconcile(m)
    assert counts["grace"] == 1 and counts["provider_errors"] == 1
    sub = _sub(m)
    assert sub.status == "grace"
    assert _aware(sub.access_until) == datetime(2026, 11, 26, 10, 0, tzinfo=UTC)
    # The renewal arrives late (within grace): access continues from the old anniversary.
    tx = paystack.charge_renewal(m["code"])
    _send_webhook(m["client"], paystack, "charge.success", tx)
    sub = _sub(m)
    assert sub.status == "active" and sub.past_due_since is None
    assert _aware(sub.current_period_end) == datetime(2026, 12, 23, 10, 0, tzinfo=UTC)


def test_cancel_keeps_paid_access_resume_and_end(member, monkeypatch):
    m, paystack = member, member["paystack"]
    shopper = m["member"]
    body = {"subscription_id": m["sub_id"]}
    paystack.fail_disable = True
    res = shopper.post(f"{ACCOUNT}/cancel", body)
    assert res.status_code == 502 and _sub(m).cancel_at_period_end is False  # nothing changed
    paystack.fail_disable = False
    data = shopper.post(f"{ACCOUNT}/cancel", body).get_json()["data"]["subscription"]
    assert data["cancel_at_period_end"] is True and data["status"] == "active"
    assert data["can_resume"] is True and data["can_cancel"] is False
    assert _aware(_sub(m).access_until) == FIRST_END
    assert _ents(m)[0].status == "active"
    assert paystack.subscriptions[m["code"]]["status"] == "non-renewing"
    assert "membership_cancelled" in _templates(m)
    assert shopper.post(f"{ACCOUNT}/cancel", body).status_code == 200  # idempotent

    data = shopper.post(f"{ACCOUNT}/resume", body).get_json()["data"]["subscription"]
    assert data["cancel_at_period_end"] is False
    assert paystack.subscriptions[m["code"]]["status"] == "active"
    shopper.post(f"{ACCOUNT}/cancel", body)
    paystack.fail_enable = True
    res = shopper.post(f"{ACCOUNT}/resume", body)
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "resume_unavailable"

    _at(monkeypatch, datetime(2026, 11, 20, tzinfo=UTC))
    _reconcile(m)
    assert _sub(m).status == "active"  # paid time remains
    _at(monkeypatch, datetime(2026, 11, 23, 11, 0, tzinfo=UTC))
    _reconcile(m)
    sub = _sub(m)
    assert (sub.status, sub.end_reason) == ("ended", "cancelled")
    assert [e.status for e in _ents(m)] == ["revoked"]
    assert shopper.post(f"{ACCOUNT}/resume", body).status_code == 409


def test_cancel_requires_a_linked_subscription_and_is_private(club, seeded):  # noqa: F811
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    club["paystack"].pay(_reference(club, sub_id))
    club["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    res = club["member"].post(f"{ACCOUNT}/cancel", {"subscription_id": sub_id})
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "subscription_not_linked"
    from .conftest import register_customer

    other = register_customer(seeded, "other@example.com")
    for path in ("cancel", "resume", "payment-method"):
        assert other.post(f"{ACCOUNT}/{path}", {"subscription_id": sub_id}).status_code == 404


def test_payment_method_link_is_provider_hosted(member):
    res = member["member"].post(f"{ACCOUNT}/payment-method", {"subscription_id": member["sub_id"]})
    assert res.status_code == 200
    assert res.get_json()["data"]["url"].startswith("https://paystack.com/manage/subscriptions/")


def test_cancellation_at_paystack_is_confirmed_before_use(member):
    m, paystack = member, member["paystack"]
    hint = {"subscription_code": m["code"], "status": "non-renewing", "domain": "test"}
    # The event claims non-renewing, but Paystack still reports active: no change.
    res = _send_webhook(m["client"], paystack, "subscription.not_renew", hint)
    assert res.status_code == 200 and _sub(m).cancel_at_period_end is False
    paystack.subscriptions[m["code"]]["status"] = "non-renewing"
    hint["status"] = "non-renewing-2"
    _send_webhook(m["client"], paystack, "subscription.not_renew", hint)
    sub = _sub(m)
    assert sub.cancel_at_period_end is True and sub.status == "active"
    assert _aware(sub.access_until) == FIRST_END


def test_failure_before_link_is_deferred_then_retried(club, client, monkeypatch):  # noqa: F811
    paystack = club["paystack"]
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    ref = _reference(club, sub_id)
    paystack.pay(ref)
    club["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    remote = paystack.subscribe(ref, email="member@example.com")
    failed = {"invoice_code": "INV_x", "subscription": remote, "status": "failed", "domain": "test"}
    _at(monkeypatch, datetime(2026, 11, 22, tzinfo=UTC))
    res = _send_webhook(client, paystack, "invoice.payment_failed", failed)
    assert res.get_json()["data"]["status"] == "deferred"
    _send_webhook(client, paystack, "subscription.create", remote)
    counts = _reconcile(club, check_provider=False)
    assert counts["events_retried"] == 1
    with club["app"].app_context():
        assert db.session.scalar(select(CustomerSubscription.status)) == "past_due"
        assert (
            db.session.scalar(
                select(PaymentEvent.status).where(
                    PaymentEvent.event_type == "invoice.payment_failed"
                )
            )
            == "processed"
        )


def test_refund_with_revoke_ends_membership_and_dispute_is_flagged(member, as_role):
    m, paystack = member, member["paystack"]
    with m["app"].app_context():
        sub = db.session.scalar(select(CustomerSubscription))
        first = db.session.get(Order, sub.order_id)
        oid, reference = first.id, first.attempts[-1].reference
    dispute = {
        "id": 77,
        "status": "awaiting-merchant-feedback",
        "domain": "test",
        "transaction": {"id": 1, "reference": reference},
    }
    assert _send_webhook(m["client"], paystack, "charge.dispute.create", dispute).status_code == 200
    assert "payment_disputed" in _events(m) and _sub(m).status == "active"

    finance = as_role("finance_manager")
    res = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {
            "amount_minor": 300,
            "reason": "Goodwill",
            "revoke_access": False,
            "idempotency_key": _key(),
        },
    )
    refund = res.get_json()["data"]["refund"]
    finance.post(
        f"/api/v1/admin/orders/{oid}/refunds/{refund['id']}/complete",
        {"provider_reference": "RF_1", "confirm": True},
    )
    assert _sub(m).status == "active"
    res = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"reason": "Customer request", "revoke_access": True, "idempotency_key": _key()},
    )
    refund = res.get_json()["data"]["refund"]
    res = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds/{refund['id']}/complete",
        {"provider_reference": "RF_2", "confirm": True},
    )
    assert res.status_code == 200
    sub = _sub(m)
    assert (sub.status, sub.end_reason) == ("ended", "refunded")
    assert [e.status for e in _ents(m)] == ["revoked"]
    assert paystack.subscriptions[m["code"]]["status"] == "non-renewing"


def test_interrupted_or_concurrent_renewal_never_duplicates(member, monkeypatch):
    """A delivery that dies after recording the renewal order (or races another delivery)
    is finished by the next one: one order, one period, one extension."""
    import app.services.commerce.payments as payments
    from app.services.commerce.payments import get_provider
    from app.services.memberships.lifecycle import renew

    m, paystack = member, member["paystack"]
    tx = paystack.charge_renewal(m["code"])
    real = payments.apply_verified
    monkeypatch.setattr(
        payments,
        "apply_verified",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("worker died")),
    )
    with m["app"].app_context():
        sub = db.session.scalar(select(CustomerSubscription))
        sub_id = sub.id
        with pytest.raises(RuntimeError):
            renew(sub, get_provider().verify(tx["reference"]))
    monkeypatch.setattr(payments, "apply_verified", real)
    for _ in range(2):
        _send_webhook(m["client"], paystack, "charge.success", dict(tx, status="success"))
    with m["app"].app_context():
        periods = db.session.scalars(select(SubscriptionPeriod)).all()
        assert sorted((p.sequence, p.status) for p in periods) == [(1, "paid"), (2, "paid")]
        assert db.session.query(Order).filter(Order.kind == "subscription").count() == 2
        # The database itself refuses a second period for the same order.
        from sqlalchemy.exc import IntegrityError

        db.session.add(
            SubscriptionPeriod(
                subscription_id=sub_id,
                sequence=3,
                status="pending",
                order_id=periods[1].order_id,
                amount_minor=999,
                currency="USD",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
    assert _events(m).count("renewed") == 1
