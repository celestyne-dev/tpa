"""Batch 10.4: membership administration, complimentary access, reports and compliance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, CustomerSubscription, Entitlement, MembershipGrant, Order

from .conftest import PASSWORD, register_customer
from .test_commerce_checkout import _key, _send_webhook
from .test_membership_checkout import ACCOUNT, _join, _reference, club  # noqa: F401
from .test_membership_lifecycle import _activate, _at, _ents, _sub

SUBS = "/api/v1/admin/membership-subscriptions"
GRANTS = "/api/v1/admin/membership-grants"
REPORTS = "/api/v1/admin/membership-reports"


@pytest.fixture()
def member(club, client):  # noqa: F811
    return _activate(club, client)


def _audits(app, action):
    with app.app_context():
        return db.session.scalars(select(AuditLog).where(AuditLog.action == action)).all()


def _detail(api, sub_id):
    return api.get(f"{SUBS}/{sub_id}").get_json()["data"]


def test_permissions_are_enforced_server_side(member, as_role):
    sub_id = member["sub_id"]
    support = as_role("customer_support")
    assert support.get(SUBS).status_code == 200
    detail = _detail(support, sub_id)
    assert detail["can"]["manage"] is True and detail["can"]["refund"] is False
    # Support can manage memberships but still can't refund without refunds.issue.
    oid = detail["orders"][0]["id"]
    res = support.post(
        f"/api/v1/admin/orders/{oid}/refunds", {"reason": "x", "idempotency_key": _key()}
    )
    assert res.status_code == 403
    finance, analyst = as_role("finance_manager"), as_role("analyst")
    for role, api in (("analyst", analyst), ("finance_manager", finance)):
        assert api.get(SUBS).status_code == 403, role
        assert api.get(f"{SUBS}/{sub_id}").status_code == 403, role
        body = {"lock_version": detail["lock_version"], "reason": "Not allowed"}
        assert api.post(f"{SUBS}/{sub_id}/cancel", body).status_code == 403, role
        assert api.post(GRANTS, {}).status_code == 403, role
    assert finance.get(REPORTS).status_code == 200
    assert analyst.get(REPORTS).status_code == 200
    assert support.get(REPORTS).status_code == 403
    # Customers never reach admin data; public plan API carries no subscriber data.
    assert member["member"].get(SUBS).status_code in (401, 403)
    public = member["app"].test_client().get("/api/v1/memberships").get_json()["data"]
    assert "subscribers" not in str(public) and "member@example.com" not in str(public)


def test_list_filters_and_detail(member, as_role, seeded):
    admin = as_role("administrator")
    other = register_customer(seeded, "second@example.com")
    _join(member, shopper=other)  # a pending checkout for another customer
    rows = admin.get(SUBS).get_json()
    assert rows["meta"]["total"] == 2
    found = admin.get(SUBS, query_string={"q": "member@"}).get_json()["data"]
    assert [r["id"] for r in found] == [member["sub_id"]]
    assert found[0]["next"]["type"] == "renewal"
    assert admin.get(SUBS, query_string={"status": "pending"}).get_json()["meta"]["total"] == 1
    assert (
        admin.get(SUBS, query_string={"flag": "payment_problem"}).get_json()["meta"]["total"] == 0
    )
    assert admin.get(SUBS, query_string={"status": "nope"}).status_code == 400
    page = admin.get(SUBS, query_string={"page": 2, "page_size": 1}).get_json()
    assert len(page["data"]) == 1 and page["meta"]["total"] == 2

    detail = _detail(admin, member["sub_id"])
    assert detail["customer"]["email"] == "member@example.com"
    assert detail["provider"]["linked"] is True and "email_token" not in str(detail)
    assert [p["status"] for p in detail["periods"]] == ["paid"]
    assert detail["orders"][0]["receipt_number"].startswith("R-")
    assert {"checkout_started", "activated", "provider_subscription_linked"} <= {
        e["type"] for e in detail["events"]
    }


def test_reconcile_cancel_and_audit_with_lock_versions(member, as_role):
    admin = as_role("administrator")
    sub_id, paystack = member["sub_id"], member["paystack"]
    detail = _detail(admin, sub_id)
    assert admin.post(f"{SUBS}/{sub_id}/reconcile", {}).status_code == 400  # lock required
    stale = {"lock_version": detail["lock_version"] - 1}
    assert admin.post(f"{SUBS}/{sub_id}/reconcile", stale).status_code == 409
    res = admin.post(f"{SUBS}/{sub_id}/reconcile", {"lock_version": detail["lock_version"]})
    assert res.status_code == 200
    result = res.get_json()["data"]["result"]
    assert result["provider"]["status"] == "active" and result["provider"]["plan_matches"]
    assert _audits(member["app"], "membership.reconciled")

    detail = res.get_json()["data"]["subscription"]
    body = {"lock_version": detail["lock_version"], "reason": "Customer asked by phone"}
    paystack.fail_disable = True
    assert admin.post(f"{SUBS}/{sub_id}/cancel", body).status_code == 502
    assert _sub(member).cancel_at_period_end is False
    paystack.fail_disable = False
    res = admin.post(f"{SUBS}/{sub_id}/cancel", body)
    assert res.status_code == 200
    data = res.get_json()["data"]["subscription"]
    assert data["cancel_at_period_end"] is True and data["status"] == "active"
    assert data["next"]["type"] == "cancellation"
    assert paystack.subscriptions[member["code"]]["status"] == "non-renewing"
    # The same submit again is refused (stale lock), never applied twice.
    assert admin.post(f"{SUBS}/{sub_id}/cancel", body).status_code == 409
    [log] = _audits(member["app"], "membership.cancelled_by_staff")
    assert log.details["reason"] == "Customer asked by phone"
    res = admin.post(
        f"{SUBS}/{sub_id}/cancel",
        {"lock_version": data["lock_version"], "reason": "Abuse", "immediate": True},
    )
    assert res.get_json()["data"]["subscription"]["status"] == "ended"
    assert [e.status for e in _ents(member)] == ["revoked"]


def test_grace_extension_is_bounded_and_only_for_failed_payments(member, as_role, monkeypatch):
    admin = as_role("administrator")
    sub_id = member["sub_id"]
    detail = _detail(admin, sub_id)
    body = {"lock_version": detail["lock_version"], "days": 5, "reason": "Card replaced"}
    assert (
        admin.post(f"{SUBS}/{sub_id}/extend-grace", body).get_json()["error"]["details"]["code"]
        == "not_past_due"
    )
    _at(monkeypatch, datetime(2026, 11, 24, tzinfo=UTC))
    from app.services.memberships.lifecycle import reconcile

    with member["app"].app_context():
        reconcile(check_provider=False)
    detail = _detail(admin, sub_id)
    assert detail["status"] == "grace"
    before = datetime.fromisoformat(detail["access_until"])
    body = {"lock_version": detail["lock_version"], "days": 5, "reason": "Card replaced"}
    assert admin.post(f"{SUBS}/{sub_id}/extend-grace", dict(body, days=30)).status_code == 400
    res = admin.post(f"{SUBS}/{sub_id}/extend-grace", body)
    assert res.status_code == 200
    after = datetime.fromisoformat(res.get_json()["data"]["subscription"]["access_until"])
    assert after - before == timedelta(days=5)
    assert _ents(member)[0].expires_at.replace(tzinfo=UTC) == after
    assert admin.post(f"{SUBS}/{sub_id}/extend-grace", body).status_code == 409  # replay
    lock = res.get_json()["data"]["subscription"]["lock_version"]
    for _ in range(5):  # bounded at 30 days after the paid period
        r = admin.post(f"{SUBS}/{sub_id}/extend-grace", {**body, "lock_version": lock, "days": 14})
        if r.status_code != 200:
            break
        lock = r.get_json()["data"]["subscription"]["lock_version"]
    assert r.get_json()["error"]["details"]["code"] == "grace_limit"
    final = datetime.fromisoformat(_detail(admin, sub_id)["access_until"])
    assert final == datetime(2026, 12, 23, 10, 0, tzinfo=UTC)
    assert len(_audits(member["app"], "membership.grace_extended")) >= 2


def test_complimentary_membership_grant_expiry_and_revoke(club, as_role, seeded):  # noqa: F811
    admin = as_role("administrator")
    guest = register_customer(seeded, "guest@example.com")
    with club["app"].app_context():
        from app.models import Customer

        cid = db.session.scalar(
            select(Customer.public_id).where(Customer.email == "guest@example.com")
        )
    expires = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    body = {
        "customer_id": cid,
        "plan_id": club["plan"]["id"],
        "expires_at": expires,
        "reason": "Podcast guest",
        "idempotency_key": _key(),
    }
    assert admin.post(GRANTS, dict(body, reason="")).status_code == 400
    too_long = (datetime.now(UTC) + timedelta(days=400)).date().isoformat()
    assert admin.post(GRANTS, dict(body, expires_at=too_long)).status_code == 400
    res = admin.post(GRANTS, body)
    assert res.status_code == 201
    grant = res.get_json()["data"]
    assert grant["status"] == "active" and grant["granted_by"]
    assert admin.post(GRANTS, body).get_json()["data"]["id"] == grant["id"]  # idempotent
    assert admin.post(GRANTS, dict(body, idempotency_key=_key())).status_code == 409
    with club["app"].app_context():
        ent = db.session.scalar(select(Entitlement).where(Entitlement.source == "membership"))
        assert ent.grant_key.startswith("membership:grant-") and ent.expires_at is not None
    view = guest.get(ACCOUNT).get_json()["data"]
    assert view["subscription"] is None
    assert view["complimentary"][0]["status"] == "active"
    assert "reason" not in view["complimentary"][0]  # staff notes stay internal
    report = admin.get(REPORTS).get_json()["data"]
    assert report["current"]["complimentary"] == 1 and report["current"]["paid_subscribers"] == 0
    assert report["access"]["complimentary_entitlements"] == 1

    res = admin.post(f"{GRANTS}/{grant['id']}/revoke", {"reason": "Ended early"})
    assert res.get_json()["data"]["status"] == "revoked"
    with club["app"].app_context():
        assert db.session.scalar(select(Entitlement.status)) == "revoked"
    assert len(_audits(club["app"], "membership.complimentary_granted")) == 1
    assert len(_audits(club["app"], "membership.complimentary_revoked")) == 1
    assert admin.get(GRANTS, query_string={"status": "revoked"}).get_json()["meta"]["total"] == 1


def test_reports_count_only_verified_money(member, as_role, seeded):
    admin = as_role("administrator")
    paystack = member["paystack"]
    # A renewal, a refund and an unpaid checkout by someone else.
    tx = paystack.charge_renewal(member["code"])
    _send_webhook(member["client"], paystack, "charge.success", tx)
    _join(member, shopper=register_customer(seeded, "pending@example.com"))
    with member["app"].app_context():
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
        {"provider_reference": "RF_9", "confirm": True},
    )
    data = admin.get(
        REPORTS, query_string={"date_from": "2026-01-01", "date_to": "2026-12-31"}
    ).get_json()["data"]
    assert data["current"]["paid_subscribers"] == 1 and data["current"]["monthly"] == 1
    assert data["current"]["pending_checkout"] == 1
    assert data["period"]["new_subscriptions"] == 1 and data["period"]["renewals"] == 1
    assert data["revenue"] == [{"mode": "test", "count": 2, "amount": data["revenue"][0]["amount"]}]
    assert data["revenue"][0]["amount"]["amount_minor"] == 999 * 2
    assert data["refunds"][0]["amount"]["amount_minor"] == 300
    assert data["net_revenue"][0]["amount"]["amount_minor"] == 999 * 2 - 300
    october = next(m for m in data["trend"] if m["month"] == "2026-10")
    assert october["new"] == 1 and october["churn_rate"] is None  # no base yet
    november = next(m for m in data["trend"] if m["month"] == "2026-11")
    assert november["active_at_start"] == 1 and november["churn_rate"] == 0
    assert data["access"]["entitlements"] == 1
    # Outside the date range: no revenue.
    empty = admin.get(
        REPORTS, query_string={"date_from": "2025-01-01", "date_to": "2025-01-31"}
    ).get_json()["data"]
    assert empty["revenue"] == [] and empty["period"]["new_subscriptions"] == 0
    assert admin.get(REPORTS, query_string={"date_from": "bad"}).status_code == 400


def test_export_and_deletion_stop_billing_safely(member, seeded):
    shopper, paystack = member["member"], member["paystack"]
    exported = shopper.post("/api/v1/account/export", {"password": PASSWORD}).get_json()["data"]
    [sub] = exported["memberships"]["subscriptions"]
    assert sub["status"] == "active" and sub["billing_periods"][0]["status"] == "paid"
    assert "email_token" not in str(exported["memberships"])

    paystack.fail_disable = True
    res = shopper.post("/api/v1/account/delete", {"password": PASSWORD})
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "membership_cancellation_failed"
    assert _sub(member).status == "active"  # nothing changed
    paystack.fail_disable = False
    assert shopper.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    s = _sub(member)
    assert (s.status, s.end_reason, s.provider_email_token) == ("ended", "account_deleted", None)
    assert paystack.subscriptions[member["code"]]["status"] == "non-renewing"
    with member["app"].app_context():
        order = db.session.get(Order, s.order_id)
        assert order.status == "paid"  # billing records are retained
        assert db.session.scalar(select(Entitlement.status)) == "revoked"


def test_deletion_blocked_while_membership_is_not_linked(club, client):  # noqa: F811
    sub_id = _join(club).get_json()["data"]["subscription"]["id"]
    club["paystack"].pay(_reference(club, sub_id))
    club["member"].post(f"{ACCOUNT}/verify", {"subscription_id": sub_id})
    res = club["member"].post("/api/v1/account/delete", {"password": PASSWORD})
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "membership_not_linked"
    with club["app"].app_context():
        assert db.session.scalar(select(CustomerSubscription.status)) == "active"
        assert db.session.scalar(select(MembershipGrant.id)) is None


def test_inclusion_and_overview_for_editors(club, as_role):  # noqa: F811
    product_id = club["guide"]["id"]
    res = as_role("product_manager").get(f"/api/v1/admin/membership-inclusion/{product_id}")
    assert [p["name"] for p in res.get_json()["data"]] == [club["plan"]["name"]]
    overview = as_role("administrator").get("/api/v1/admin/membership-overview").get_json()["data"]
    assert overview["live_billing"] is False and overview["grace_days"] == 3
    assert "secret" not in str(overview).lower()
