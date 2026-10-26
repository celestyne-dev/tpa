"""Customer accounts, checkout, Paystack verification and webhooks, fulfilment,
secure downloads, free products, refunds, reports and payment settings."""

from __future__ import annotations

import os
import secrets

import pytest

from app.extensions import db, limiter
from app.models import (
    Customer,
    DownloadEvent,
    EmailDelivery,
    Entitlement,
    Order,
    PaymentEvent,
    PaymentTransaction,
    User,
)
from app.services.mail import MemoryBackend

from .conftest import (
    PASSWORD,
    Shopper,
    csrf,
    enable_test_checkout,
    login,
    minimal_pdf,
    register_customer,
)
from .test_commerce_catalogue import PRODUCTS, _create, _sellable

WEBHOOK = "/api/v1/payments/paystack/webhook"


def _key():
    return secrets.token_hex(16)


def _checkout(shopper, product_ids, currency="USD", expected=None, key=None, quote=None):
    if expected is None:
        quote = shopper.post(
            "/api/v1/cart/quote",
            {"items": [{"product_id": p} for p in product_ids], "currency": currency},
        ).get_json()["data"]
        expected = quote["total"]["amount_minor"]
    return shopper.post(
        "/api/v1/checkout",
        {
            "items": [{"product_id": p} for p in product_ids],
            "currency": currency,
            "expected_total_minor": expected,
            "idempotency_key": key or _key(),
            "accept_terms": True,
        },
    )


def _public_id(app, product_id):
    from app.models import Product

    with app.app_context():
        return db.session.get(Product, product_id).public_id


def _send_webhook(client, paystack, event, data, secret=None):
    raw, headers = paystack.webhook(event, data, **({"secret": secret} if secret else {}))
    return client.post(WEBHOOK, data=raw, headers=headers)


@pytest.fixture()
def shop(seeded, as_role, paystack):
    """A store with one sellable product, test checkout enabled and a verified test customer."""
    admin = as_role("super_admin", email="owner@example.org")
    product = _sellable(admin, "Calm Mornings Workbook", price=1500)
    admin.post(f"{PRODUCTS}/{product['id']}/prices", {"currency": "KES", "amount_minor": 195000})
    enable_test_checkout(seeded)
    shopper = register_customer(seeded)
    return {
        "app": seeded,
        "admin": admin,
        "product": product,
        "public_id": _public_id(seeded, product["id"]),
        "shopper": shopper,
        "paystack": paystack,
    }


def _paid_order(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    assert res.status_code == 201, res.get_json()
    order = res.get_json()["data"]["order"]
    shop["paystack"].pay(order["payment"]["reference"])
    tx = shop["paystack"].transactions[order["payment"]["reference"]]
    res = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert res.status_code == 200, res.get_json()
    return order


# ---- customer accounts ----------------------------------------------------------------------


def test_customer_registration_login_and_isolation_from_admin(seeded, client):
    shopper = register_customer(seeded, verify=False, test_account=False)
    me = shopper.get("/api/v1/account/me").get_json()["data"]["customer"]
    assert me["email"] == "reader@example.com" and me["email_verified"] is False
    assert "password" not in str(me)
    # Registering never creates administrators or roles.
    with seeded.app_context():
        assert db.session.scalar(db.select(User).where(User.email == "reader@example.com")) is None
    # A customer session never authenticates against the admin API.
    assert shopper.get("/api/v1/admin/auth/me").status_code == 401
    assert shopper.get("/api/v1/admin/orders").status_code == 401
    # Mutations need the customer CSRF token.
    no_csrf = shopper.c.patch("/api/v1/account/me", json={"display_name": "X"})
    assert no_csrf.status_code == 403
    assert shopper.patch("/api/v1/account/me", {"display_name": "Ann"}).status_code == 200
    # Cookies are HttpOnly (session) and scoped to the API.
    cookie = shopper.c.get_cookie("tpa_customer", path="/api/v1/")
    assert cookie.path == "/api/v1/" and cookie.http_only

    assert shopper.post("/api/v1/account/logout").status_code == 200
    assert shopper.get("/api/v1/account/me").status_code == 401
    fresh = Shopper(seeded.test_client())
    bad = fresh.c.post(
        "/api/v1/account/login", json={"email": "reader@example.com", "password": "nope"}
    )
    assert bad.status_code == 401 and "incorrect" in bad.get_json()["error"]["message"]
    ok = fresh.c.post(
        "/api/v1/account/login", json={"email": "READER@example.com", "password": PASSWORD}
    )
    assert ok.status_code == 200


def test_admin_session_is_not_a_customer_session(seeded, admin_factory):
    admin = admin_factory(["super_admin"], email="boss@example.org")
    assert admin.get("/api/v1/account/me").status_code == 401
    assert admin.get("/api/v1/account/library").status_code == 401


def test_registration_does_not_reveal_existing_accounts(seeded):
    register_customer(seeded, verify=False)
    MemoryBackend.outbox.clear()
    other = seeded.test_client()
    res = other.post(
        "/api/v1/account/register",
        json={
            "email": "reader@example.com",
            "password": PASSWORD,
            "display_name": "Someone",
            "accept_terms": True,
        },
    )
    assert res.status_code == 201 and res.get_json()["data"]["signed_in"] is False
    assert other.get_cookie("tpa_customer") is None
    assert "reset" in MemoryBackend.outbox[-1].subject.lower()  # the owner is told instead
    weak = other.post(
        "/api/v1/account/register",
        json={
            "email": "new@example.com",
            "password": "short",
            "display_name": "New",
            "accept_terms": True,
        },
    )
    assert weak.status_code == 400


def test_password_reset_and_email_verification_tokens_are_single_use(seeded):
    shopper = register_customer(seeded, verify=False, test_account=False)
    message = MemoryBackend.outbox[-1]
    token = message.text.split("#token=", 1)[1].split()[0]
    assert shopper.post("/api/v1/account/verify-email", {"token": token}).status_code == 200
    assert shopper.post("/api/v1/account/verify-email", {"token": token}).status_code == 400
    anon = seeded.test_client()
    res = anon.post("/api/v1/account/password-reset", json={"email": "reader@example.com"})
    assert res.status_code == 200
    same = anon.post("/api/v1/account/password-reset", json={"email": "nobody@example.com"})
    assert same.get_json() == res.get_json()  # no enumeration
    reset = MemoryBackend.outbox[-1].text.split("#token=", 1)[1].split()[0]
    new = "A-Brand-New-Passphrase-42"
    res = anon.post(
        "/api/v1/account/password-reset/complete", json={"token": reset, "password": new}
    )
    assert res.status_code == 200
    assert shopper.get("/api/v1/account/me").status_code == 401  # other sessions revoked
    assert (
        anon.post(
            "/api/v1/account/login", json={"email": "reader@example.com", "password": new}
        ).status_code
        == 200
    )


# ---- checkout gating ------------------------------------------------------------------------


def test_checkout_is_closed_by_default(seeded, as_role, paystack):
    admin = as_role("super_admin", email="owner@example.org")
    product = _sellable(admin)
    shopper = register_customer(seeded)
    status = shopper.get("/api/v1/shop/status").get_json()["data"]
    assert status["open"] is False and status["mode"] == "disabled"
    res = _checkout(shopper, [_public_id(seeded, product["id"])], expected=1500)
    assert res.status_code == 409 and res.get_json()["error"]["code"] == "checkout_closed"
    assert not paystack.calls  # nothing was sent to the provider


def test_test_mode_checkout_is_limited_to_test_accounts_and_verified_emails(shop):
    app = shop["app"]
    stranger = register_customer(app, "stranger@example.com", test_account=False)
    res = _checkout(stranger, [shop["public_id"]], expected=1500)
    assert res.status_code == 409 and res.get_json()["error"]["code"] == "checkout_closed"
    unverified = register_customer(app, "new@example.com", verify=False)
    res = _checkout(unverified, [shop["public_id"]], expected=1500)
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["code"] == "email_unverified"


# ---- order creation -------------------------------------------------------------------------


def test_checkout_uses_server_prices_and_rejects_tampering(shop):
    shopper = shop["shopper"]
    quote = shopper.post(
        "/api/v1/cart/quote",
        {
            "items": [{"product_id": shop["public_id"]}, {"product_id": shop["public_id"]}],
            "currency": "USD",
        },
    ).get_json()["data"]
    assert len(quote["lines"]) == 1  # duplicates collapse into one licence
    assert quote["total"] == {
        "amount_minor": 1500,
        "currency": "USD",
        "amount": "15.00",
        "formatted": "USD 15.00",
    }
    tampered = _checkout(shopper, [shop["public_id"]], expected=1)
    assert tampered.status_code == 409
    assert tampered.get_json()["error"]["details"]["code"] == "price_changed"
    no_terms = shopper.post(
        "/api/v1/checkout",
        {
            "items": [shop["public_id"]],
            "currency": "USD",
            "expected_total_minor": 1500,
            "idempotency_key": _key(),
        },
    )
    assert no_terms.status_code == 400
    unsupported = _checkout(shopper, [shop["public_id"]], currency="EUR", expected=1500)
    assert unsupported.status_code == 400

    res = _checkout(shopper, [shop["public_id"]], currency="KES")
    assert res.status_code == 201, res.get_json()
    body = res.get_json()["data"]
    assert body["authorization_url"].startswith("https://checkout.paystack.com/")
    order = body["order"]
    assert order["status"] == "awaiting_payment" and order["test_mode"] is True
    assert order["total"]["formatted"] == "KES 1,950.00"
    init = [c for c in shop["paystack"].calls if c[1] == "/transaction/initialize"][-1][2]
    assert init["amount"] == "195000" and init["currency"] == "KES"
    assert init["email"] == "reader@example.com"
    assert "callback_url" in init and order["id"] in init["callback_url"]
    with shop["app"].app_context():
        saved = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
        item = saved.items[0]
        assert (item.unit_amount_minor, item.currency, item.title) == (
            195000,
            "KES",
            "Calm Mornings Workbook",
        )


def test_duplicate_checkout_requests_are_idempotent(shop):
    shopper = shop["shopper"]
    key = _key()
    first = _checkout(shopper, [shop["public_id"]], key=key)
    second = _checkout(shopper, [shop["public_id"]], key=key)
    assert first.status_code == second.status_code == 201
    a, b = first.get_json()["data"], second.get_json()["data"]
    assert a["order"]["id"] == b["order"]["id"]
    assert a["authorization_url"] == b["authorization_url"]
    other_cart = _checkout(shopper, [shop["public_id"]], currency="KES", key=key)
    assert other_cart.status_code == 409
    with shop["app"].app_context():
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 1


def test_payment_initialisation_failure_is_honest_and_retryable(shop):
    shop["paystack"].fail_initialize = True
    res = _checkout(shop["shopper"], [shop["public_id"]])
    assert res.status_code == 502
    error = res.get_json()["error"]
    assert error["code"] == "payment_unavailable" and "not been charged" in error["message"]
    order_id = error["details"]["order"]
    shop["paystack"].fail_initialize = False
    retry = shop["shopper"].post(f"/api/v1/checkout/orders/{order_id}/retry")
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json()["data"]["authorization_url"]


# ---- verification, webhooks and fulfilment --------------------------------------------------


def test_browser_return_alone_never_marks_an_order_paid(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    # The shopper comes back from Paystack, but the provider has not confirmed payment.
    status = (
        shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    )
    assert status["order"]["status"] == "awaiting_payment" and status["outcome"] == "pending"
    assert shop["shopper"].get("/api/v1/account/library").get_json()["data"] == []
    # Once Paystack confirms it, the server-side verification fulfils the order.
    shop["paystack"].pay(order["payment"]["reference"])
    status = (
        shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    )
    assert status["outcome"] == "paid" and status["order"]["status"] == "paid"
    library = shop["shopper"].get("/api/v1/account/library").get_json()["data"]
    assert [i["product"]["title"] for i in library] == ["Calm Mornings Workbook"]


def test_signed_webhook_fulfils_once_and_replays_are_ignored(shop, client):
    order = _paid_order(shop, client)
    tx = shop["paystack"].transactions[order["payment"]["reference"]]
    replay = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert replay.status_code == 200 and replay.get_json()["data"]["status"] == "duplicate"
    with shop["app"].app_context():
        saved = db.session.scalar(db.select(Order).where(Order.public_id == order["id"]))
        assert saved.status == "paid" and saved.paid_at is not None
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
        assert db.session.scalar(db.select(db.func.count(PaymentTransaction.id))) == 1
        event = db.session.scalar(db.select(PaymentEvent))
        assert event.status == "processed" and event.received_count == 2
        assert "authorization" not in str(event.payload) and "email" not in event.payload
        templates = {e.template: e.status for e in db.session.scalars(db.select(EmailDelivery))}
        assert templates["order_confirmation"] == "memory"
        assert templates["download_instructions"] == "memory"
    detail = shop["shopper"].get(f"/api/v1/account/orders/{order['id']}").get_json()["data"]
    assert detail["receipt"]["number"].startswith("R-")
    assert (
        detail["receipt"]["total"]["formatted"] == "USD 15.00"
        and detail["receipt"]["mode"] == "test"
    )


def test_invalid_webhook_signatures_are_rejected(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    tx = shop["paystack"].pay(order["payment"]["reference"])
    forged = _send_webhook(
        client, shop["paystack"], "charge.success", tx, secret="sk_test_attacker"
    )
    assert forged.status_code == 401
    unsigned = client.post(WEBHOOK, json={"event": "charge.success", "data": tx})
    assert unsigned.status_code == 401
    with shop["app"].app_context():
        assert db.session.scalar(db.select(Order.status)) == "awaiting_payment"
        assert db.session.scalar(db.select(db.func.count(PaymentEvent.id))) == 0
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 0


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"amount": 100}, "amount"),
        ({"currency": "KES"}, "currency"),
        ({"domain": "live"}, "live payment"),
    ],
)
def test_inconsistent_payments_are_rejected_and_flagged(shop, client, change, reason):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    tx = shop["paystack"].pay(order["payment"]["reference"], **change)
    res = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "rejected"
    with shop["app"].app_context():
        saved = db.session.scalar(db.select(Order))
        assert saved.status == "awaiting_payment" and saved.needs_review
        assert reason in saved.review_reason
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 0
        assert db.session.scalar(db.select(db.func.count(PaymentTransaction.id))) == 0


def test_webhook_for_an_unknown_reference_is_ignored(shop, client):
    data = {
        "id": 1,
        "reference": "SOMEONE-ELSE-1",
        "status": "success",
        "amount": 1,
        "currency": "USD",
        "domain": "test",
    }
    res = _send_webhook(client, shop["paystack"], "charge.success", data)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "ignored"


def test_provider_outage_during_webhook_is_retried_later(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    tx = shop["paystack"].pay(order["payment"]["reference"])
    shop["paystack"].fail_verify = True
    first = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert first.status_code == 503  # Paystack retries non-2xx deliveries
    shop["paystack"].fail_verify = False
    again = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert again.status_code == 200 and again.get_json()["data"]["status"] == "processed"
    with shop["app"].app_context():
        assert db.session.scalar(db.select(Order.status)) == "paid"


def test_abandoned_status_keeps_the_order_open_for_a_late_payment(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    for _ in range(2):  # the customer reloads the return page before paying
        status = (
            shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
        )
        assert status["outcome"] == "pending" and status["order"]["status"] == "awaiting_payment"
    with shop["app"].app_context():
        assert not db.session.scalar(
            db.select(EmailDelivery.id).where(EmailDelivery.template == "payment_failed")
        )
    # The customer then completes payment on Paystack; the signed webhook fulfils it.
    tx = shop["paystack"].pay(order["payment"]["reference"])
    res = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert res.status_code == 200
    library = shop["shopper"].get("/api/v1/account/library").get_json()["data"]
    assert [i["product"]["title"] for i in library] == ["Calm Mornings Workbook"]


def test_failed_payment_then_successful_retry(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    shop["paystack"].pay(order["payment"]["reference"], status="failed")
    status = (
        shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    )
    assert status["outcome"] == "failed" and status["order"]["status"] == "failed"
    assert status["order"]["can_retry"] is True
    with shop["app"].app_context():
        assert (
            db.session.scalar(
                db.select(EmailDelivery.status).where(EmailDelivery.template == "payment_failed")
            )
            == "memory"
        )
    retry = shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/retry").get_json()["data"]
    new_ref = retry["order"]["payment"]["reference"]
    assert new_ref != order["payment"]["reference"]
    shop["paystack"].pay(new_ref)
    status = (
        shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    )
    assert status["order"]["status"] == "paid"


def test_out_of_order_refund_event_is_deferred_until_payment_confirmed(shop, client):
    shop["app"].extensions  # noqa: B018
    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    ref = order["payment"]["reference"]
    tx = shop["paystack"].pay(ref)
    refund_data = {
        "id": 777,
        "status": "processed",
        "transaction_reference": ref,
        "amount": 1500,
        "currency": "USD",
        "domain": "test",
    }
    early = _send_webhook(client, shop["paystack"], "refund.processed", refund_data)
    assert early.get_json()["data"]["status"] == "deferred"
    assert _send_webhook(client, shop["paystack"], "charge.success", tx).status_code == 200
    with shop["app"].app_context():
        event = db.session.scalar(
            db.select(PaymentEvent).where(PaymentEvent.event_type == "refund.processed")
        )
        assert event.status == "processed"  # re-processed once the charge was confirmed
        saved = db.session.scalar(db.select(Order))
        assert saved.status == "paid" and saved.needs_review  # refund not started here
        assert saved.refunded_minor == 0  # never marked refunded without a matching refund


def test_repeated_finalisation_is_idempotent(shop, client):
    from app.payments.paystack import get_provider
    from app.services.commerce.payments import apply_verified

    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    shop["paystack"].pay(order["payment"]["reference"])
    with shop["app"].app_context():
        saved = db.session.scalar(db.select(Order))
        attempt = saved.attempts[-1]
        tx = get_provider().verify(attempt.reference)
        outcomes = [apply_verified(saved, attempt, tx, "test") for _ in range(3)]
        assert outcomes == ["paid", "already_paid", "already_paid"]
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
        assert db.session.scalar(db.select(db.func.count(PaymentTransaction.id))) == 1


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Concurrent finalisation needs a real database server (run with TEST_DATABASE_URL).",
)
def test_concurrent_finalisation_grants_access_once(shop, client):
    import threading

    from app.payments.paystack import get_provider
    from app.services.commerce.payments import apply_verified

    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    shop["paystack"].pay(order["payment"]["reference"])
    app = shop["app"]
    results, barrier = [], threading.Barrier(6)

    def worker():
        with app.app_context():
            saved = db.session.scalar(db.select(Order))
            attempt = saved.attempts[-1]
            tx = get_provider().verify(attempt.reference)
            barrier.wait()
            results.append(apply_verified(saved, attempt, tx, "concurrency"))
            db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results).count("paid") == 1, results
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
        assert db.session.scalar(db.select(db.func.count(PaymentTransaction.id))) == 1


# ---- downloads -------------------------------------------------------------------------------


def _library_file(shopper):
    item = shopper.get("/api/v1/account/library").get_json()["data"][0]
    return item, item["files"][0]["versions"][0]


def test_secure_downloads_after_verified_purchase(shop, client):
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 200
    url = res.get_json()["data"]["url"]
    assert url.startswith("/api/v1/downloads/") and "product-files" not in url
    download = shopper.get(url)
    assert download.status_code == 200 and download.data.startswith(b"%PDF")
    assert download.headers["Content-Disposition"].startswith("attachment;")
    assert "calm-mornings-workbook" in download.headers["Content-Disposition"]
    assert download.headers["Cache-Control"] == "private, no-store"
    assert "noindex" in download.headers["X-Robots-Tag"]
    # The link alone is useless without the owner's session.
    assert client.get(url).status_code == 403
    thief = register_customer(shop["app"], "thief@example.com")
    assert thief.get(url).status_code == 403
    assert (
        thief.post(
            f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
        ).status_code
        == 404
    )
    # Links expire after a few uses.
    for _ in range(4):
        assert shopper.get(url).status_code == 200
    assert shopper.get(url).status_code == 410
    with shop["app"].app_context():
        statuses = [e.status for e in db.session.scalars(db.select(DownloadEvent))]
        assert statuses.count("served") == 5 and "denied" in statuses


def test_unpaid_and_unauthenticated_downloads_are_refused(shop, client):
    res = _checkout(shop["shopper"], [shop["public_id"]])
    assert res.status_code == 201
    assert shop["shopper"].get("/api/v1/account/library").get_json()["data"] == []
    assert client.get("/api/v1/account/library").status_code == 401
    assert client.get("/api/v1/downloads/not-a-real-token").status_code == 404


def test_revoked_entitlements_block_new_downloads(shop, client, as_role):
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    url = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    support = as_role("orders_manager")
    res = support.post(f"/api/v1/admin/entitlements/{item['id']}/revoke", {"reason": "Chargeback"})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "revoked"
    assert shopper.get(url).status_code == 403  # an already issued link stops working
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 403
    viewer = as_role("customer_support")
    assert (
        viewer.post(f"/api/v1/admin/entitlements/{item['id']}/restore", {"reason": "x"}).status_code
        == 403
    )
    assert (
        support.post(
            f"/api/v1/admin/entitlements/{item['id']}/restore", {"reason": "Resolved"}
        ).status_code
        == 200
    )
    assert (
        shopper.post(
            f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
        ).status_code
        == 200
    )


def test_version_policy_latest_and_purchased_versions(shop, client):
    _paid_order(shop, client)
    admin, pid = shop["admin"], shop["product"]["id"]
    file_id = admin.get(f"{PRODUCTS}/{pid}/files").get_json()["data"]["files"][0]["id"]
    admin.upload(
        f"{PRODUCTS}/{pid}/files/{file_id}/versions", minimal_pdf(b"% second edition\n"), "v2.pdf"
    )
    item = shop["shopper"].get("/api/v1/account/library").get_json()["data"][0]
    kinds = {v["kind"]: v["version"] for v in item["files"][0]["versions"]}
    assert kinds == {"latest": 2, "purchased": 1}
    # Deactivating the file keeps it for people who already bought it.
    admin.patch(f"{PRODUCTS}/{pid}/files/{file_id}", {"status": "inactive"})
    item = shop["shopper"].get("/api/v1/account/library").get_json()["data"][0]
    assert [v["kind"] for v in item["files"][0]["versions"]] == ["purchased"]


def test_download_limits_when_configured(shop, client):
    from app.models import SiteSetting

    with shop["app"].app_context():
        db.session.add(SiteSetting(key="payments.download_limit", value=2))
        db.session.commit()
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    url = f"/api/v1/account/library/{item['id']}/downloads"
    assert shopper.post(url, {"version_id": version["version_id"]}).status_code == 200
    assert shopper.post(url, {"version_id": version["version_id"]}).status_code == 200
    third = shopper.post(url, {"version_id": version["version_id"]})
    assert (
        third.status_code == 403 and third.get_json()["error"]["code"] == "download_limit_reached"
    )


# ---- free products and bundles --------------------------------------------------------------


def test_free_products_grant_access_without_orders(seeded, as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    product = _create(admin, "Free Gratitude Worksheet", "worksheet", short_description="Free.")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"pricing_model": "free"})
    admin.upload(f"{PRODUCTS}/{product['id']}/files", minimal_pdf(), "sheet.pdf")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    admin.post(f"{PRODUCTS}/{product['id']}/publish")
    public = client.get(f"/api/v1/shop/products/{product['slug']}").get_json()["data"]
    assert public["availability"] == "free" and public["is_free"] and public["prices"] == []
    public_id = _public_id(seeded, product["id"])
    assert (
        client.post("/api/v1/account/free-claims", json={"product_id": public_id}).status_code
        == 401
    )
    shopper = register_customer(
        seeded, test_account=False
    )  # free claims work while checkout is closed
    first = shopper.post("/api/v1/account/free-claims", {"product_id": public_id})
    again = shopper.post("/api/v1/account/free-claims", {"product_id": public_id})
    assert first.status_code == 201 and again.status_code == 200
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 0
        ent = db.session.scalar(db.select(Entitlement))
        assert ent.source == "free" and ent.order_id is None
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 1
    quote = shopper.post(
        "/api/v1/cart/quote", {"items": [public_id], "currency": "USD"}
    ).get_json()["data"]
    assert quote["can_checkout"] is False and "free" in quote["lines"][0]["problem"]


def test_bundle_purchase_preserves_entitlements_after_composition_changes(shop, client):
    admin, app = shop["admin"], shop["app"]
    second = _sellable(admin, "Evening Journal", price=900)
    bundle = _create(admin, "Starter Bundle", "bundle", short_description="Both titles.")
    admin.put(
        f"{PRODUCTS}/{bundle['id']}/bundle-items",
        {"product_ids": [shop["product"]["id"], second["id"]]},
    )
    admin.post(f"{PRODUCTS}/{bundle['id']}/prices", {"currency": "USD", "amount_minor": 2000})
    assert admin.patch(f"{PRODUCTS}/{bundle['id']}", {"sales_status": "on_sale"}).status_code == 200
    admin.post(f"{PRODUCTS}/{bundle['id']}/publish")
    bundle_public = _public_id(app, bundle["id"])
    quote = (
        shop["shopper"]
        .post(
            "/api/v1/cart/quote",
            {"items": [bundle_public, shop["public_id"]], "currency": "USD"},
        )
        .get_json()["data"]
    )
    assert quote["can_checkout"] is False  # an item already inside the bundle is flagged
    res = _checkout(shop["shopper"], [bundle_public])
    order = res.get_json()["data"]["order"]
    assert order["total"]["formatted"] == "USD 20.00"
    shop["paystack"].pay(order["payment"]["reference"])
    shop["shopper"].post(f"/api/v1/checkout/orders/{order['id']}/verify")
    # The bundle is changed after the sale: access already granted is preserved.
    admin.put(f"{PRODUCTS}/{bundle['id']}/bundle-items", {"product_ids": [second["id"]]})
    library = shop["shopper"].get("/api/v1/account/library").get_json()["data"]
    titles = sorted(i["product"]["title"] for i in library)
    assert titles == ["Calm Mornings Workbook", "Evening Journal", "Starter Bundle"]
    downloadable = [i for i in library if i["files"]]
    assert len(downloadable) == 2
    # Owned products cannot be bought again by accident.
    quote = (
        shop["shopper"]
        .post("/api/v1/cart/quote", {"items": [shop["public_id"]], "currency": "USD"})
        .get_json()["data"]
    )
    assert quote["lines"][0]["problem"] == "Already in your library."


# ---- refunds ---------------------------------------------------------------------------------


def _order_db_id(app, public_id):
    with app.app_context():
        return db.session.scalar(db.select(Order.id).where(Order.public_id == public_id))


def test_manual_refund_workflow_never_pretends(shop, client, as_role):
    order = _paid_order(shop, client)
    oid = _order_db_id(shop["app"], order["id"])
    support = as_role("customer_support")
    assert support.get(f"/api/v1/admin/orders/{oid}").status_code == 200
    assert (
        support.post(
            f"/api/v1/admin/orders/{oid}/refunds", {"reason": "x", "idempotency_key": _key()}
        ).status_code
        == 403
    )
    finance = as_role("finance_manager")
    key = _key()
    too_much = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"amount_minor": 99999, "reason": "x", "idempotency_key": _key()},
    )
    assert too_much.status_code == 400
    res = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"amount_minor": 500, "reason": "Partial goodwill", "idempotency_key": key},
    )
    assert res.status_code == 201
    refund = res.get_json()["data"]["refund"]
    assert refund["status"] == "manual_review" and refund["method"] == "manual"
    again = finance.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"amount_minor": 500, "reason": "Partial goodwill", "idempotency_key": key},
    )
    assert again.get_json()["data"]["refund"]["id"] == refund["id"]  # repeated request
    detail = again.get_json()["data"]["order"]
    assert detail["status"] == "paid" and detail["refunded"]["amount_minor"] == 0
    assert detail["refundable"]["amount_minor"] == 1000
    url = f"/api/v1/admin/orders/{oid}/refunds/{refund['id']}/complete"
    assert finance.post(url, {"provider_reference": "RF_123"}).status_code == 400  # no confirmation
    res = finance.post(url, {"provider_reference": "RF_123", "confirm": True})
    assert res.status_code == 200
    detail = res.get_json()["data"]["order"]
    assert (
        detail["status"] == "partially_refunded" and detail["refunded"]["formatted"] == "USD 5.00"
    )
    # Partial refunds keep download access by default.
    assert (
        shop["shopper"].get("/api/v1/account/library").get_json()["data"][0]["status"] == "active"
    )


def test_full_provider_refund_revokes_access_when_confirmed(shop, client, as_role):
    from app.models import SiteSetting

    with shop["app"].app_context():
        db.session.add(SiteSetting(key="payments.refunds_via_provider", value=True))
        db.session.commit()
    order = _paid_order(shop, client)
    oid = _order_db_id(shop["app"], order["id"])
    manager = as_role("orders_manager")
    res = manager.post(
        f"/api/v1/admin/orders/{oid}/refunds",
        {"reason": "Customer request", "idempotency_key": _key()},
    )
    assert res.status_code == 201, res.get_json()
    refund = res.get_json()["data"]["refund"]
    assert refund["status"] == "pending_provider" and refund["revoke_access"] is True
    assert res.get_json()["data"]["order"]["status"] == "paid"  # not refunded until confirmed
    data = {
        "id": int(refund["provider_refund_id"]),
        "status": "processed",
        "transaction_reference": order["payment"]["reference"],
        "amount": 1500,
        "currency": "USD",
        "domain": "test",
    }
    assert _send_webhook(client, shop["paystack"], "refund.processed", data).status_code == 200
    detail = manager.get(f"/api/v1/admin/orders/{oid}").get_json()["data"]
    assert detail["status"] == "refunded" and detail["refunds"][0]["status"] == "processed"
    library = shop["shopper"].get("/api/v1/account/library").get_json()["data"]
    assert library[0]["status"] == "revoked" and library[0]["files"] == []
    with shop["app"].app_context():
        assert (
            db.session.scalar(
                db.select(EmailDelivery.status).where(
                    EmailDelivery.template == "refund_confirmation"
                )
            )
            == "memory"
        )


def test_provider_refund_failure_is_recorded_not_refunded(shop, client, as_role):
    from app.models import SiteSetting
    from app.payments.base import ProviderError

    with shop["app"].app_context():
        db.session.add(SiteSetting(key="payments.refunds_via_provider", value=True))
        db.session.commit()
    order = _paid_order(shop, client)
    oid = _order_db_id(shop["app"], order["id"])

    def refuse(**_kw):
        raise ProviderError("Paystack: Refund not allowed for this transaction")

    shop["paystack"].provider.refund = refuse
    manager = as_role("orders_manager")
    res = manager.post(
        f"/api/v1/admin/orders/{oid}/refunds", {"reason": "x", "idempotency_key": _key()}
    )
    refund = res.get_json()["data"]["refund"]
    assert refund["status"] == "failed" and "not allowed" in refund["failure_reason"]
    assert res.get_json()["data"]["order"]["status"] == "paid"


# ---- admin, settings, reports, privacy -------------------------------------------------------


def test_order_admin_permissions_and_export(shop, client, as_role):
    order = _paid_order(shop, client)
    limiter.reset()
    support = as_role("customer_support")
    listing = support.get("/api/v1/admin/orders?q=reader").get_json()
    assert listing["meta"]["total"] == 1
    assert support.get("/api/v1/admin/orders/export").status_code == 403
    assert support.get("/api/v1/admin/payments/settings").status_code == 403
    assert support.get("/api/v1/admin/reports/revenue").status_code == 403
    finance = as_role("finance_manager")
    export = finance.get("/api/v1/admin/orders/export")
    assert export.status_code == 200 and order["number"] in export.get_data(as_text=True)
    assert export.headers["Content-Type"].startswith("text/csv")
    orders = as_role("orders_manager")
    assert orders.get("/api/v1/admin/payments/settings").status_code == 403
    assert (
        orders.patch("/api/v1/admin/payments/settings", {"checkout_mode": "disabled"}).status_code
        == 403
    )
    oid = _order_db_id(shop["app"], order["id"])
    detail = orders.get(f"/api/v1/admin/orders/{oid}").get_json()["data"]
    assert detail["attempts"][0]["status"] == "succeeded" and detail["events"]
    assert detail["entitlements"][0]["source"] == "purchase"
    assert (
        orders.post(f"/api/v1/admin/orders/{oid}/resend-receipt").get_json()["data"]["delivery"]
        == "memory"
    )
    editor = as_role("editor")
    assert editor.get("/api/v1/admin/orders").status_code == 403
    assert editor.get("/api/v1/admin/customers").status_code == 403


def test_payment_settings_are_super_admin_only_and_never_expose_secrets(shop, as_role):
    admin = shop["admin"]
    body = admin.get("/api/v1/admin/payments/settings").get_json()["data"]
    assert "sk_test" not in str(body) and "secret_key_configured" in body["provider"]
    assert body["provider"]["key_mode"] == "test" and body["effective_mode"] == "test"
    res = admin.patch("/api/v1/admin/payments/settings", {"checkout_mode": "live"})
    assert res.status_code == 400  # live needs a live key, deployment flag and checklist
    assert (
        admin.patch("/api/v1/admin/payments/settings", {"currencies": ["EUR"]}).status_code == 400
    )
    assert (
        admin.patch("/api/v1/admin/payments/settings", {"secret_key": "sk_live_x"}).status_code
        == 400
    )
    assert (
        admin.patch("/api/v1/admin/payments/settings", {"order_expiry_minutes": 5}).status_code
        == 400
    )
    assert (
        admin.patch("/api/v1/admin/payments/settings", {"checkout_mode": "disabled"}).status_code
        == 200
    )
    assert shop["shopper"].get("/api/v1/shop/status").get_json()["data"]["open"] is False
    limiter.reset()
    administrator = as_role("administrator")
    assert administrator.get("/api/v1/admin/payments/settings").status_code == 403
    site = shop["shopper"].get("/api/v1/site").get_data(as_text=True)
    assert "sk_test" not in site and "PAYSTACK" not in site.upper()


def test_revenue_report_separates_currencies_and_test_payments(shop, client, as_role):
    _paid_order(shop, client)
    res = _checkout(shop["shopper"], [shop["public_id"]], currency="KES")
    # Already owned: the second purchase is refused rather than double charging.
    assert res.status_code == 409
    finance = as_role("finance_manager")
    live = finance.get("/api/v1/admin/reports/revenue").get_json()["data"]
    assert live["mode"] == "live" and live["currencies"] == []
    test = finance.get("/api/v1/admin/reports/revenue?mode=test").get_json()["data"]
    usd = test["currencies"][0]
    assert (usd["currency"], usd["gross"]["formatted"], usd["paid_orders"]) == (
        "USD",
        "USD 15.00",
        1,
    )
    assert test["by_product"][0]["title"] == "Calm Mornings Workbook"
    assert any("never added together" in n for n in test["notes"])
    assert finance.get("/api/v1/admin/reports/revenue/export?mode=test").status_code == 200


def test_order_expiry_and_late_payment(shop, client):
    from datetime import UTC, datetime, timedelta

    from app.services.commerce.payments import expire_orders

    res = _checkout(shop["shopper"], [shop["public_id"]])
    order = res.get_json()["data"]["order"]
    with shop["app"].app_context():
        assert expire_orders(datetime.now(UTC) + timedelta(hours=2)) == 1
        db.session.commit()
    status = shop["shopper"].get(f"/api/v1/checkout/orders/{order['id']}").get_json()["data"]
    assert status["status"] == "cancelled"
    # The customer had actually paid on Paystack's page: the verified payment is honoured.
    tx = shop["paystack"].pay(order["payment"]["reference"])
    _send_webhook(client, shop["paystack"], "charge.success", tx)
    with shop["app"].app_context():
        saved = db.session.scalar(db.select(Order))
        assert saved.status == "paid" and saved.needs_review and "expired" in saved.review_reason


def test_customer_export_and_deletion_keep_financial_records(shop, client, as_role):
    _paid_order(shop, client)
    shopper = shop["shopper"]
    assert shopper.post("/api/v1/account/export", {"password": "wrong"}).status_code == 401
    export = shopper.post("/api/v1/account/export", {"password": PASSWORD}).get_json()["data"]
    assert export["profile"]["email"] == "reader@example.com" and len(export["orders"]) == 1
    assert shopper.post("/api/v1/account/delete", {"password": "wrong"}).status_code == 401
    assert shopper.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 200
    assert shopper.get("/api/v1/account/me").status_code == 401
    with shop["app"].app_context():
        customer = db.session.scalar(db.select(Customer))
        assert customer.status == "deleted" and customer.email.endswith("@deleted.invalid")
        assert customer.password_hash is None
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 1  # retained
        assert db.session.scalar(db.select(Entitlement.status)) == "revoked"


def test_customer_admin_support_actions(shop, as_role):
    support = as_role("customer_support")
    customers = support.get("/api/v1/admin/customers").get_json()["data"]
    cid = customers[0]["id"]
    assert (
        support.post(f"/api/v1/admin/customers/{cid}/password-reset").get_json()["data"]["delivery"]
        == "memory"
    )
    assert (
        support.patch(f"/api/v1/admin/customers/{cid}", {"status": "disabled"}).status_code == 403
    )
    assert (
        support.patch(
            f"/api/v1/admin/customers/{cid}", {"support_notes": "Asked about invoice"}
        ).status_code
        == 200
    )
    limiter.reset()
    admin = as_role("administrator")
    assert admin.patch(f"/api/v1/admin/customers/{cid}", {"status": "disabled"}).status_code == 200
    assert shop["shopper"].get("/api/v1/account/me").status_code == 401  # sessions revoked
    grant = admin.post(
        f"/api/v1/admin/customers/{cid}/entitlements",
        {"product_id": shop["product"]["id"], "reason": "Press copy"},
    )
    assert grant.status_code == 400  # account disabled
    admin.patch(f"/api/v1/admin/customers/{cid}", {"status": "active"})
    grant = admin.post(
        f"/api/v1/admin/customers/{cid}/entitlements",
        {"product_id": shop["product"]["id"], "reason": "Press copy"},
    )
    assert grant.status_code == 201 and grant.get_json()["data"]["source"] == "manual"


def test_csrf_and_origin_checks_on_checkout(shop):
    shopper = shop["shopper"]
    body = {
        "items": [shop["public_id"]],
        "currency": "USD",
        "expected_total_minor": 1500,
        "idempotency_key": _key(),
        "accept_terms": True,
    }
    assert shopper.c.post("/api/v1/checkout", json=body).status_code == 403
    evil = shopper.c.post(
        "/api/v1/checkout",
        json=body,
        headers={**shopper.headers(), "Origin": "https://evil.example"},
    )
    assert evil.status_code == 403


def test_admin_csrf_helper_still_required(seeded):
    from .conftest import make_user

    make_user(seeded, "pm@example.org", ["product_manager"])
    c = seeded.test_client()
    login(c, "pm@example.org")
    res = c.post(PRODUCTS, json={"title": "X", "product_type": "ebook"})
    assert res.status_code == 403
    res = c.post(PRODUCTS, json={"title": "X", "product_type": "ebook"}, headers=csrf(c))
    assert res.status_code == 201
