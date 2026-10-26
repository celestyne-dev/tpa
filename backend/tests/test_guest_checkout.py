"""Guest checkout: buying without an account, emailed access links, purchase recovery,
claiming purchases after registering, and the protections around all of them."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import (
    AuditLog,
    Customer,
    CustomerToken,
    DownloadGrant,
    EmailDelivery,
    Entitlement,
    Order,
)
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Shopper, register_customer
from .test_commerce_checkout import _key, _order_db_id, _send_webhook, shop  # noqa: F401

GUEST = "/api/v1/checkout/guest"
HEADER = "X-Guest-Order-Token"


@pytest.fixture()
def gshop(shop):  # noqa: F811
    """The shop with test checkout open to the public (as on staging), so guests can pay."""
    shop["app"].config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    MemoryBackend.outbox.clear()
    return shop


def _guest_checkout(client, store, email="Buyer@Example.com ", key=None, expected=1500, **extra):
    return client.post(
        GUEST,
        json={
            "email": email,
            "items": [{"product_id": store["public_id"]}],
            "currency": "USD",
            "expected_total_minor": expected,
            "idempotency_key": key or _key(),
            "accept_terms": True,
            **extra,
        },
    )


def _paid_guest_order(store, client, email="buyer@example.com"):
    res = _guest_checkout(client, store, email=email)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    reference = data["order"]["payment"]["reference"]
    tx = store["paystack"].pay(reference)
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert _send_webhook(client, store["paystack"], "charge.success", tx).status_code == 200
    return data["order"], data["order_token"]


def _token_from(message):
    return message.text.split("#token=", 1)[1].split()[0]


def _mail_to(email):
    return [m for m in MemoryBackend.outbox if m.to == email]


# ---- placing a guest order --------------------------------------------------------------


def test_guest_checkout_creates_an_order_without_an_account(gshop, client):
    res = _guest_checkout(client, gshop, name="Ama")
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert data["authorization_url"].startswith("https://")
    assert len(data["order_token"]) >= 40
    order = data["order"]
    assert order["guest"] is True and order["status"] == "awaiting_payment"
    assert order["email_hint"] == "b•••@example.com"  # never the full address
    assert order["downloads_available"] is False and order["library"] == []
    # No session or cookie is created, and the browser can't sign in as the buyer.
    assert client.get_cookie("tpa_customer", path="/api/v1/") is None
    with gshop["app"].app_context():
        stored = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
        assert stored.is_guest and stored.email == "buyer@example.com"  # normalised
        assert stored.guest_token_hash and data["order_token"] not in stored.guest_token_hash
        buyer = db.session.get(Customer, stored.customer_id)
        assert buyer.status == "guest" and buyer.password_hash is None
        assert buyer.display_name == "Ama"
        assert stored.attempts[0].status == "initialized"
    login = client.post(
        "/api/v1/account/login", json={"email": "buyer@example.com", "password": ""}
    )
    assert login.status_code in (400, 401)


def test_guest_checkout_validates_input_and_keeps_prices_on_the_server(gshop, client):
    assert _guest_checkout(client, gshop, email="not-an-email").status_code == 400
    assert _guest_checkout(client, gshop, email="").status_code == 400
    assert _guest_checkout(client, gshop, name="<script>").status_code == 400
    tampered = _guest_checkout(client, gshop, expected=1)
    assert tampered.status_code == 409
    assert tampered.get_json()["error"]["details"]["code"] == "price_changed"
    no_terms = client.post(
        GUEST,
        json={
            "email": "buyer@example.com",
            "items": [{"product_id": gshop["public_id"]}],
            "currency": "USD",
            "expected_total_minor": 1500,
            "idempotency_key": _key(),
        },
    )
    assert no_terms.status_code == 400
    with gshop["app"].app_context():
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 0


def test_guest_checkout_respects_the_checkout_gate(shop, client):  # noqa: F811
    # Test mode without public test checkout: only signed-in test accounts may pay.
    res = _guest_checkout(client, shop)
    assert res.status_code == 409 and "testing" in res.get_json()["error"]["message"]
    shop["app"].config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    shop["app"].config["ENV_NAME"] = "production"
    assert _guest_checkout(client, shop).status_code == 409


def test_guest_checkout_is_idempotent_and_rotates_the_order_token(gshop, client):
    key = _key()
    first = _guest_checkout(client, gshop, key=key).get_json()["data"]
    second = _guest_checkout(client, gshop, key=key).get_json()["data"]
    assert first["order"]["id"] == second["order"]["id"]
    assert first["authorization_url"] == second["authorization_url"]
    assert first["order_token"] != second["order_token"]
    oid = first["order"]["id"]
    old = client.get(f"/api/v1/checkout/guest-orders/{oid}", headers={HEADER: first["order_token"]})
    assert old.status_code == 404
    new = client.get(
        f"/api/v1/checkout/guest-orders/{oid}", headers={HEADER: second["order_token"]}
    )
    assert new.status_code == 200
    with gshop["app"].app_context():
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 1


def test_guest_checkout_never_reveals_existing_accounts(gshop, client):
    register_customer(gshop["app"], "member@example.com")
    known = _guest_checkout(client, gshop, email="member@example.com").get_json()["data"]
    unknown = _guest_checkout(client, gshop, email="stranger@example.com").get_json()["data"]
    assert set(known) == set(unknown)
    assert set(known["order"]) == set(unknown["order"])
    for data in (known, unknown):
        assert data["order"]["status"] == "awaiting_payment" and data["order"]["library"] == []
    # Nothing from the member's account is reachable with the guest order token.
    assert "member@example.com" not in str(known)


def test_guest_order_token_is_scoped_to_its_order(gshop, client):
    a = _guest_checkout(client, gshop, email="a@example.com").get_json()["data"]
    b = _guest_checkout(client, gshop, email="b@example.com").get_json()["data"]
    url = "/api/v1/checkout/guest-orders/{}"
    assert (
        client.get(url.format(a["order"]["id"]), headers={HEADER: a["order_token"]}).status_code
        == 200
    )
    for headers in ({HEADER: b["order_token"]}, {HEADER: "x" * 43}, {}):
        assert client.get(url.format(a["order"]["id"]), headers=headers).status_code == 404
    # Guest endpoints don't open account orders, and account endpoints don't open guest orders.
    member = register_customer(gshop["app"], "member@example.com")
    assert member.get(f"/api/v1/checkout/orders/{a['order']['id']}").status_code == 404
    # The token stops opening the order after the access window.
    with gshop["app"].app_context():
        order = db.session.scalar(db.select(Order).where(Order.public_id == a["order"]["id"]))
        order.created_at = datetime.now(UTC) - timedelta(hours=169)
        db.session.commit()
    assert (
        client.get(url.format(a["order"]["id"]), headers={HEADER: a["order_token"]}).status_code
        == 404
    )


# ---- payment, fulfilment and downloads --------------------------------------------------


def test_browser_return_alone_never_grants_guest_downloads(gshop, client):
    data = _guest_checkout(client, gshop).get_json()["data"]
    oid, token = data["order"]["id"], data["order_token"]
    res = client.post(f"/api/v1/checkout/guest-orders/{oid}/verify", headers={HEADER: token})
    assert res.status_code == 200
    assert res.get_json()["data"]["outcome"] == "pending"
    assert res.get_json()["data"]["order"]["status"] == "awaiting_payment"
    with gshop["app"].app_context():
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 0
    blocked = client.post(
        f"/api/v1/checkout/guest-orders/{oid}/downloads",
        json={"entitlement_id": 1, "version_id": 1},
        headers={HEADER: token},
    )
    assert blocked.status_code == 404


def test_verified_guest_payment_fulfils_once_and_emails_an_access_link(gshop, client):
    order, token = _paid_guest_order(gshop, client)
    reference = order["payment"]["reference"]
    tx = gshop["paystack"].transactions[reference]
    # A replayed webhook doesn't fulfil twice.
    assert _send_webhook(client, gshop["paystack"], "charge.success", tx).status_code == 200
    with gshop["app"].app_context():
        stored = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
        assert stored.status == "paid"
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
        templates = [
            d.template
            for d in db.session.scalars(
                db.select(EmailDelivery).where(EmailDelivery.order_id == stored.id)
            )
        ]
        assert templates.count("download_instructions") == 1
    mail = _mail_to("buyer@example.com")
    instructions = [m for m in mail if m.subject == "Your downloads are ready"][-1]
    assert "/purchases#token=" in instructions.text and "/account/library" not in instructions.text
    confirmation = [m for m in mail if m.subject.startswith("Order")][-1]
    assert "/purchases#token=" in confirmation.text and "/account/orders" not in confirmation.text
    # Every guest email in this batch carries the same, latest link.
    tokens = {_token_from(m) for m in mail if "#token=" in m.text}
    assert len(tokens) == 1
    # The order page (with the browser's order token) now offers downloads.
    status = client.get(
        f"/api/v1/checkout/guest-orders/{order['id']}", headers={HEADER: token}
    ).get_json()["data"]
    assert status["status"] == "paid" and status["downloads_available"] is True
    assert status["library"][0]["files"][0]["versions"]


def test_guest_downloads_from_the_order_page(gshop, client):
    order, token = _paid_guest_order(gshop, client)
    oid = order["id"]
    status = client.get(f"/api/v1/checkout/guest-orders/{oid}", headers={HEADER: token})
    item = status.get_json()["data"]["library"][0]
    version = item["files"][0]["versions"][0]
    res = client.post(
        f"/api/v1/checkout/guest-orders/{oid}/downloads",
        json={"entitlement_id": item["id"], "version_id": version["version_id"]},
        headers={HEADER: token},
    )
    assert res.status_code == 200, res.get_json()
    url = res.get_json()["data"]["url"]
    assert url.startswith("/api/v1/downloads/") and "product-files" not in url
    other = gshop["app"].test_client()
    download = other.get(url)  # no session needed for a guest grant, but still short-lived
    assert download.status_code == 200 and download.data.startswith(b"%PDF")
    assert download.headers["Cache-Control"] == "private, no-store"
    with gshop["app"].app_context():
        grant = db.session.scalar(db.select(DownloadGrant))
        assert grant.guest is True
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
    assert other.get(url).status_code == 410
    # Without the token, or with another order's token, nothing is authorised.
    other_order = _guest_checkout(client, gshop, email="c@example.com").get_json()["data"]
    for headers in ({}, {HEADER: other_order["order_token"]}):
        res = client.post(
            f"/api/v1/checkout/guest-orders/{oid}/downloads",
            json={"entitlement_id": item["id"], "version_id": version["version_id"]},
            headers=headers,
        )
        assert res.status_code == 404
    # After the download window the order page stops offering downloads (the email link stays).
    with gshop["app"].app_context():
        stored = db.session.scalar(db.select(Order).where(Order.public_id == oid))
        stored.paid_at = datetime.now(UTC) - timedelta(hours=25)
        db.session.commit()
    late = client.get(f"/api/v1/checkout/guest-orders/{oid}", headers={HEADER: token})
    assert late.get_json()["data"]["downloads_available"] is False
    assert late.get_json()["data"]["library"] == []
    res = client.post(
        f"/api/v1/checkout/guest-orders/{oid}/downloads",
        json={"entitlement_id": item["id"], "version_id": version["version_id"]},
        headers={HEADER: token},
    )
    assert res.status_code == 404


def test_guest_failed_payment_retry_and_cancel(gshop, client):
    data = _guest_checkout(client, gshop).get_json()["data"]
    oid, token = data["order"]["id"], data["order_token"]
    gshop["paystack"].pay(data["order"]["payment"]["reference"], status="failed")
    res = client.post(f"/api/v1/checkout/guest-orders/{oid}/verify", headers={HEADER: token})
    body = res.get_json()["data"]
    assert body["outcome"] == "failed" and body["order"]["status"] == "failed"
    failed_mail = [m for m in _mail_to("buyer@example.com") if "not completed" in m.subject][-1]
    assert "/account/orders" not in failed_mail.text
    retry = client.post(f"/api/v1/checkout/guest-orders/{oid}/retry", headers={HEADER: token})
    assert retry.status_code == 200
    new_ref = retry.get_json()["data"]["order"]["payment"]["reference"]
    assert new_ref != data["order"]["payment"]["reference"]
    init = [body for method, path, body in gshop["paystack"].calls if path.endswith("initialize")]
    assert "guest=1" in init[-1]["callback_url"]
    cancel = client.post(f"/api/v1/checkout/guest-orders/{oid}/cancel", headers={HEADER: token})
    assert cancel.status_code == 200 and cancel.get_json()["data"]["status"] == "cancelled"
    # Mutations from other sites are refused.
    evil = client.post(
        f"/api/v1/checkout/guest-orders/{oid}/retry",
        headers={HEADER: token, "Origin": "https://evil.example"},
    )
    assert evil.status_code == 403
    evil = client.post(
        GUEST,
        json={"email": "x@example.com"},
        headers={"Origin": "https://evil.example"},
    )
    assert evil.status_code == 403


def test_guest_order_responses_are_private(gshop, client):
    data = _guest_checkout(client, gshop).get_json()["data"]
    res = client.get(
        f"/api/v1/checkout/guest-orders/{data['order']['id']}",
        headers={HEADER: data["order_token"]},
    )
    assert res.headers["Cache-Control"] == "no-store"
    assert "noindex" in res.headers["X-Robots-Tag"]
    res = client.post("/api/v1/guest/access-request", json={"email": "a@example.com"})
    assert res.headers["Cache-Control"] == "no-store"


# ---- access links and recovery ----------------------------------------------------------


def test_guest_access_link_opens_only_that_buyers_guest_purchases(gshop, client):
    _paid_guest_order(gshop, client)
    _paid_guest_order(gshop, client, email="other@example.com")
    token = _token_from(_mail_to("buyer@example.com")[-1])
    res = client.post("/api/v1/guest/library", json={"token": token})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["email_hint"] == "b•••@example.com"
    assert len(data["orders"]) == 1 and len(data["library"]) == 1
    item = data["library"][0]
    version = item["files"][0]["versions"][0]
    # The link is reusable until it expires (people come back to download again).
    assert client.post("/api/v1/guest/library", json={"token": token}).status_code == 200
    res = client.post(
        "/api/v1/guest/library/downloads",
        json={"token": token, "entitlement_id": item["id"], "version_id": version["version_id"]},
    )
    assert res.status_code == 200
    assert client.get(res.get_json()["data"]["url"]).status_code == 200
    # Another buyer's link can't reach this buyer's entitlement.
    other_token = _token_from(_mail_to("other@example.com")[-1])
    res = client.post(
        "/api/v1/guest/library/downloads",
        json={
            "token": other_token,
            "entitlement_id": item["id"],
            "version_id": version["version_id"],
        },
    )
    assert res.status_code == 404
    for bad in ("", "short", "x" * 43, None, 42):
        assert client.post("/api/v1/guest/library", json={"token": bad}).status_code == 400
    # Tokens of other kinds don't work as access links.
    with gshop["app"].app_context():
        assert (
            db.session.scalar(
                db.select(db.func.count(CustomerToken.id)).where(
                    CustomerToken.purpose == "guest_access"
                )
            )
            == 2
        )
    with gshop["app"].app_context():
        record = db.session.scalar(
            db.select(CustomerToken).where(
                CustomerToken.purpose == "guest_access", CustomerToken.used_at.is_(None)
            )
        )
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    expired = [
        t
        for t in (token, other_token)
        if client.post("/api/v1/guest/library", json={"token": t}).status_code == 400
    ]
    assert len(expired) == 1


def test_purchase_recovery_is_generic_and_replaces_old_links(gshop, client):
    _paid_guest_order(gshop, client)
    old = _token_from(_mail_to("buyer@example.com")[-1])
    register_customer(gshop["app"], "member@example.com")
    MemoryBackend.outbox.clear()
    answers = [
        client.post("/api/v1/guest/access-request", json={"email": email})
        for email in ("BUYER@example.com", "member@example.com", "nobody@example.com")
    ]
    assert {r.status_code for r in answers} == {202}
    assert len({r.get_data(as_text=True) for r in answers}) == 1  # identical bodies
    # Only the address with guest purchases gets an email.
    assert [m.to for m in MemoryBackend.outbox] == ["buyer@example.com"]
    new = _token_from(MemoryBackend.outbox[-1])
    assert new != old
    assert client.post("/api/v1/guest/library", json={"token": old}).status_code == 400
    assert client.post("/api/v1/guest/library", json={"token": new}).status_code == 200
    other = gshop["app"].test_client()
    other.environ_base["REMOTE_ADDR"] = "10.0.0.9"
    assert other.post("/api/v1/guest/access-request", json={"email": "nope"}).status_code == 400


def test_purchase_recovery_is_rate_limited_per_address(gshop):
    statuses = []
    for i in range(4):
        other = gshop["app"].test_client()
        other.environ_base["REMOTE_ADDR"] = f"10.0.0.{i + 1}"
        statuses.append(
            other.post(
                "/api/v1/guest/access-request", json={"email": "buyer@example.com"}
            ).status_code
        )
    assert statuses == [202, 202, 202, 429]


def test_refunds_and_revocations_apply_to_guest_purchases(gshop, client, as_role):
    from app.models import SiteSetting

    with gshop["app"].app_context():
        db.session.add(SiteSetting(key="payments.refunds_via_provider", value=True))
        db.session.commit()
    order, _ = _paid_guest_order(gshop, client)
    token = _token_from(_mail_to("buyer@example.com")[-1])
    item = client.post("/api/v1/guest/library", json={"token": token}).get_json()["data"][
        "library"
    ][0]
    version = item["files"][0]["versions"][0]
    url = client.post(
        "/api/v1/guest/library/downloads",
        json={"token": token, "entitlement_id": item["id"], "version_id": version["version_id"]},
    ).get_json()["data"]["url"]
    oid = _order_db_id(gshop["app"], order["id"])
    manager = as_role("orders_manager")
    detail = manager.get(f"/api/v1/admin/orders/{oid}").get_json()["data"]
    assert detail["guest_checkout"] is True and detail["customer"]["status"] == "guest"
    res = manager.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"reason": "Customer request", "idempotency_key": _key()},
    )
    refund = res.get_json()["data"]["refund"]
    data = {
        "id": int(refund["provider_refund_id"]),
        "status": "processed",
        "transaction_reference": order["payment"]["reference"],
        "amount": 1500,
        "currency": "USD",
        "domain": "test",
    }
    assert _send_webhook(client, gshop["paystack"], "refund.processed", data).status_code == 200
    assert client.get(url).status_code == 403  # an issued link stops working at once
    library = client.post("/api/v1/guest/library", json={"token": token}).get_json()["data"]
    assert library["library"][0]["status"] == "revoked" and library["library"][0]["files"] == []
    assert library["orders"][0]["status"] == "refunded"  # history is kept
    res = client.post(
        "/api/v1/guest/library/downloads",
        json={"token": token, "entitlement_id": item["id"], "version_id": version["version_id"]},
    )
    assert res.status_code == 403
    # Restoring access works for guest buyers too.
    restored = manager.post(f"/api/v1/admin/entitlements/{item['id']}/restore", {"reason": "ok"})
    assert restored.status_code == 200


# ---- claiming purchases with an account -------------------------------------------------


def _register(app, email, name="Buyer"):
    shopper = Shopper(app.test_client())
    res = shopper.c.post(
        "/api/v1/account/register",
        json={"email": email, "password": PASSWORD, "display_name": name, "accept_terms": True},
    )
    return shopper, res


def test_registering_and_confirming_the_email_claims_guest_purchases(gshop, client):
    order, _ = _paid_guest_order(gshop, client)
    MemoryBackend.outbox.clear()
    shopper, res = _register(gshop["app"], "buyer@example.com")
    # Looks exactly like a new sign-up.
    assert res.status_code == 201 and res.get_json()["data"]["signed_in"] is True
    fresh, fresh_res = _register(gshop["app"], "brand-new@example.com")
    assert set(res.get_json()["data"]) == set(fresh_res.get_json()["data"])
    verify = [m for m in MemoryBackend.outbox if m.to == "buyer@example.com"][-1]
    assert "Confirm your email" in verify.subject and "purchases" in verify.text
    # Before confirming, guest purchases stay out of the account.
    assert shopper.get("/api/v1/account/library").get_json()["data"] == []
    assert shopper.get("/api/v1/account/orders").get_json()["data"] == []
    assert shopper.get(f"/api/v1/account/orders/{order['id']}").status_code == 404
    with gshop["app"].app_context():
        ent_id = db.session.scalar(db.select(Entitlement.id))
        buyer = db.session.scalar(db.select(Customer).where(Customer.email == "buyer@example.com"))
        assert buyer.status == "active" and buyer.email_verified_at is None
    res = shopper.post(f"/api/v1/account/library/{ent_id}/downloads", {"version_id": 1})
    assert res.status_code == 404
    # The emailed guest link keeps working meanwhile.
    assert (
        shopper.post("/api/v1/account/verify-email", {"token": _token_from(verify)}).status_code
        == 200
    )
    library = shopper.get("/api/v1/account/library").get_json()["data"]
    assert len(library) == 1 and library[0]["order_number"] == order["number"]
    orders = shopper.get("/api/v1/account/orders").get_json()["data"]
    assert [o["id"] for o in orders] == [order["id"]]
    version = library[0]["files"][0]["versions"][0]
    res = shopper.post(
        f"/api/v1/account/library/{library[0]['id']}/downloads",
        {"version_id": version["version_id"]},
    )
    assert res.status_code == 200
    # Account downloads are session-bound as before.
    assert client.get(res.get_json()["data"]["url"]).status_code == 403
    assert shopper.get(res.get_json()["data"]["url"]).status_code == 200
    with gshop["app"].app_context():
        actions = [a.action for a in db.session.scalars(db.select(AuditLog))]
        assert "customer.guest_converted" in actions and "customer.email_verified" in actions


def test_someone_else_registering_the_buyers_email_gets_nothing(gshop, client):
    _paid_guest_order(gshop, client)
    attacker, res = _register(gshop["app"], "buyer@example.com", name="Mallory")
    assert res.status_code == 201
    assert attacker.get("/api/v1/account/library").get_json()["data"] == []
    assert attacker.get("/api/v1/account/orders").get_json()["data"] == []
    export = attacker.post("/api/v1/account/export", {"password": PASSWORD}).get_json()["data"]
    assert export["orders"] == [] and export["library"] == [] and export["downloads"] == []
    # Guest-access links can't be requested into the attacker's hands (they go to the inbox),
    # and the owner's existing link still works.
    owner_token = _token_from(
        [m for m in _mail_to("buyer@example.com") if "/purchases#token=" in m.text][-1]
    )
    assert client.post("/api/v1/guest/library", json={"token": owner_token}).status_code == 200
    # Deleting the unconfirmed account doesn't destroy the owner's purchases.
    res = attacker.post("/api/v1/account/delete", {"password": PASSWORD})
    assert res.status_code == 200 and res.get_json()["data"] == {"deleted": True}
    with gshop["app"].app_context():
        buyer = db.session.scalar(db.select(Customer).where(Customer.email == "buyer@example.com"))
        assert buyer.status == "guest" and buyer.password_hash is None
        assert db.session.scalar(db.select(Entitlement.status)) == "active"
    assert client.post("/api/v1/guest/library", json={"token": owner_token}).status_code == 200
    # The owner can still create their account later.
    owner, res = _register(gshop["app"], "buyer@example.com", name="Ama")
    assert res.get_json()["data"]["signed_in"] is True


def test_guest_purchase_for_a_pre_registered_unconfirmed_account_stays_hidden(gshop, client):
    attacker = register_customer(gshop["app"], "victim@example.com", verify=False)
    order, _ = _paid_guest_order(gshop, client, email="victim@example.com")
    assert attacker.get("/api/v1/account/library").get_json()["data"] == []
    assert attacker.get(f"/api/v1/account/orders/{order['id']}").status_code == 404
    # The real owner proves the inbox with a password reset and then sees the purchase.
    anon = gshop["app"].test_client()
    anon.post("/api/v1/account/password-reset", json={"email": "victim@example.com"})
    reset = _token_from(_mail_to("victim@example.com")[-1])
    new = "Owner-Owns-This-Inbox-77"
    assert (
        anon.post(
            "/api/v1/account/password-reset/complete", json={"token": reset, "password": new}
        ).status_code
        == 200
    )
    assert attacker.get("/api/v1/account/me").status_code == 401  # signed out everywhere
    owner = Shopper(gshop["app"].test_client())
    owner.c.post("/api/v1/account/login", json={"email": "victim@example.com", "password": new})
    assert len(owner.get("/api/v1/account/library").get_json()["data"]) == 1


def test_signed_in_customers_still_check_out_normally(gshop, client):
    from .test_commerce_checkout import _paid_order

    _paid_order(gshop, client)
    library = gshop["shopper"].get("/api/v1/account/library")
    assert len(library.get_json()["data"]) == 1
    with gshop["app"].app_context():
        order = db.session.scalar(db.select(Order))
        assert order.is_guest is False and order.guest_token_hash is None
    instructions = [m for m in MemoryBackend.outbox if m.subject == "Your downloads are ready"]
    assert "/account/library" in instructions[-1].text


def test_disabled_buyer_records_cannot_use_guest_checkout(gshop, client, as_role):
    _paid_guest_order(gshop, client)
    with gshop["app"].app_context():
        buyer = db.session.scalar(db.select(Customer).where(Customer.email == "buyer@example.com"))
        buyer_id = buyer.id
    manager = as_role("super_admin", email="boss@example.org")
    assert (
        manager.patch(f"/api/v1/admin/customers/{buyer_id}", {"status": "disabled"}).status_code
        == 200
    )
    res = _guest_checkout(client, gshop)
    assert (
        res.status_code == 409 and res.get_json()["error"]["code"] == "guest_checkout_unavailable"
    )
    token = secrets.token_urlsafe(32)
    assert client.post("/api/v1/guest/library", json={"token": token}).status_code == 400
    # Reactivating a never-registered buyer makes it a guest record again, not an account.
    manager.patch(f"/api/v1/admin/customers/{buyer_id}", {"status": "active"})
    with gshop["app"].app_context():
        assert db.session.get(Customer, buyer_id).status == "guest"
