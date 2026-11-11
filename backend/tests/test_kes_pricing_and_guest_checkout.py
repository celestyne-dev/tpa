"""Batch 16: KES is the only charge currency, approximate USD amounts are display-only,
and guest checkout can be switched off.

These tests run the production policy (``CHARGE_CURRENCIES = ("KES",)``); the older suite
also prices in USD. They cover guest purchases, repeated Paystack callbacks and webhooks,
declined payments, claiming purchases with an account, currency display and download
security for guest buyers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.extensions import db
from app.models import Customer, Entitlement, Order, Receipt
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Shopper
from .test_commerce_checkout import _checkout, _key, _send_webhook, shop  # noqa: F401

GUEST = "/api/v1/checkout/guest"
HEADER = "X-Guest-Order-Token"
SETTINGS = "/api/v1/admin/settings"
KES_PRICE = 195000  # KES 1,950.00, set by the shop fixture


@pytest.fixture()
def kshop(shop):  # noqa: F811
    """The shop as in production: charges in KES only, test checkout open to guests."""
    shop["app"].config["CHARGE_CURRENCIES"] = ("KES",)
    shop["app"].config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    MemoryBackend.outbox.clear()
    return shop


def _guest(client, store, currency="KES", expected=KES_PRICE, email="buyer@example.com", **extra):
    return client.post(
        GUEST,
        json={
            "email": email,
            "items": [{"product_id": store["public_id"]}],
            "currency": currency,
            "expected_total_minor": expected,
            "idempotency_key": extra.pop("key", None) or _key(),
            "accept_terms": True,
            "age_confirmed": True,
            **extra,
        },
    )


def _site(client):
    return client.get("/api/v1/site").get_json()["data"]["shop"]


def _settings(store, **values):
    res = store["admin"].patch(SETTINGS, {"values": values})
    assert res.status_code == 200, res.get_json()


def _count(app, model):
    with app.app_context():
        return db.session.scalar(db.select(db.func.count(model.id)))


# ---- KES is the only charge currency ------------------------------------------------------


def test_orders_and_paystack_charges_are_in_kes_only(kshop, client):
    shopper = kshop["shopper"]
    quote = shopper.post(
        "/api/v1/cart/quote",
        {"items": [{"product_id": kshop["public_id"]}], "currency": "KES"},
    ).get_json()["data"]
    assert quote["total"] == {
        "amount_minor": KES_PRICE,
        "currency": "KES",
        "amount": "1950.00",
        "formatted": "KES 1,950.00",
    }
    assert quote["can_checkout"] is True and quote["checkout"]["currencies"] == ["KES"]
    # A USD price exists in the CMS, but it can never be charged.
    usd = shopper.post(
        "/api/v1/cart/quote",
        {"items": [{"product_id": kshop["public_id"]}], "currency": "USD"},
    ).get_json()["data"]
    assert usd["can_checkout"] is False
    res = _checkout(shopper, [kshop["public_id"]], currency="USD", expected=1500)
    assert res.status_code >= 400
    assert _guest(client, kshop, currency="USD", expected=1500).status_code >= 400
    assert not [c for c in kshop["paystack"].calls if c[1].endswith("initialize")]
    # KES works, and Paystack is asked for exactly the KES amount shown.
    res = _checkout(shopper, [kshop["public_id"]], currency="KES")
    assert res.status_code == 201, res.get_json()
    [init] = [b for _, path, b in kshop["paystack"].calls if path.endswith("initialize")]
    assert init["currency"] == "KES" and int(init["amount"]) == KES_PRICE
    assert res.get_json()["data"]["order"]["total"]["formatted"] == "KES 1,950.00"


def test_payment_settings_refuse_other_charge_currencies(kshop):
    res = kshop["admin"].patch("/api/v1/admin/payments/settings", {"currencies": ["USD", "KES"]})
    assert res.status_code == 400
    assert "KES only" in str(res.get_json()["error"]["details"]["currencies"])
    ok = kshop["admin"].patch("/api/v1/admin/payments/settings", {"currencies": ["KES"]})
    assert ok.status_code == 200, ok.get_json()


def test_shop_shows_kes_and_only_an_approximate_usd_estimate(kshop, client):
    public = _site(client)
    assert public["display_currencies"] == ["KES"]
    assert public["usd_estimate"] is None  # off by default: KES only
    # Turned on without a rate: still KES only.
    _settings(kshop, **{"shop.usd_estimate": True})
    assert _site(client)["usd_estimate"] is None
    for bad in ("0", "-5", "abc", "1e9", "129.123456", "<b>1</b>"):
        res = kshop["admin"].patch(SETTINGS, {"values": {"shop.usd_rate": bad}})
        assert res.status_code == 400, bad
    _settings(kshop, **{"shop.usd_rate": "129.50"})
    estimate = _site(client)["usd_estimate"]
    assert estimate["from"] == "KES" and estimate["to"] == "USD"
    assert estimate["kes_per_usd"] == "129.50"
    assert estimate["updated_at"]  # shown in the CMS and on the site
    # The admin sees when the rate was last changed.
    groups = kshop["admin"].get(SETTINGS).get_json()["data"]["groups"]
    [rate] = [s for g in groups for s in g["settings"] if s["key"] == "shop.usd_rate"]
    assert rate["type"] == "exchange_rate" and rate["updated_at"]
    # Products keep their KES price; nothing is converted on the server.
    products = client.get("/api/v1/shop/products").get_json()
    assert products["meta"]["display_currencies"] == ["KES"]
    item = next(p for p in products["data"] if p["id"] == kshop["public_id"])
    # Only the KES price is shown (the USD price set in the CMS is not offered).
    assert [p["currency"] for p in item["prices"]] == ["KES"]
    assert item["prices"][0]["amount_minor"] == KES_PRICE
    # Turning the estimate off removes it again.
    _settings(kshop, **{"shop.usd_estimate": False})
    assert _site(client)["usd_estimate"] is None


# ---- guest checkout -----------------------------------------------------------------------


def test_guest_purchase_in_kes_without_an_account_or_session(kshop, client):
    res = _guest(client, kshop, email="Buyer@Example.com ")
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert data["order"]["total"]["formatted"] == "KES 1,950.00"
    # Entering an email address never signs anyone in.
    cookies = res.headers.getlist("Set-Cookie")
    assert not [c for c in cookies if c.startswith("tpa_customer=")]
    assert client.get("/api/v1/account/me").status_code == 401
    with kshop["app"].app_context():
        buyer = db.session.scalar(db.select(Customer).where(Customer.email == "buyer@example.com"))
        assert buyer.status == "guest" and buyer.password_hash is None
    # Nothing is granted before Paystack confirms the payment.
    assert _count(kshop["app"], Entitlement) == 0


def test_repeated_callbacks_and_webhooks_fulfil_once(kshop, client):
    data = _guest(client, kshop).get_json()["data"]
    oid, token = data["order"]["id"], data["order_token"]
    reference = data["order"]["payment"]["reference"]
    tx = kshop["paystack"].pay(reference)
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for _ in range(3):  # the browser returns more than once…
        verify = client.post(f"/api/v1/checkout/guest-orders/{oid}/verify", headers={HEADER: token})
        assert verify.status_code == 200
    for _ in range(3):  # …and Paystack repeats the webhook
        assert _send_webhook(client, kshop["paystack"], "charge.success", tx).status_code == 200
    app = kshop["app"]
    assert _count(app, Entitlement) == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Order.id))) == 1
        assert db.session.scalar(db.select(db.func.count(Receipt.id))) == 1
        order = db.session.scalar(db.select(Order))
        assert order.status == "paid" and order.currency == "KES"
    # One receipt and one set of access instructions, with the KES amount charged.
    mail = [m for m in MemoryBackend.outbox if m.to == "buyer@example.com"]
    receipts = [m for m in mail if m.subject.startswith("Receipt")]
    assert len(receipts) == 1 and "KES 1,950.00" in receipts[0].text
    instructions = [m for m in mail if m.subject == "Your downloads are ready"]
    assert len(instructions) == 1 and "/purchases#token=" in instructions[0].text
    assert "/register" in instructions[0].text  # how to claim the purchase with an account


@pytest.mark.parametrize("status", ["failed", "abandoned"])
def test_declined_and_abandoned_payments_grant_nothing(kshop, client, status):
    data = _guest(client, kshop).get_json()["data"]
    oid, token = data["order"]["id"], data["order_token"]
    reference = data["order"]["payment"]["reference"]
    tx = kshop["paystack"].pay(reference, status=status)
    verify = client.post(f"/api/v1/checkout/guest-orders/{oid}/verify", headers={HEADER: token})
    assert verify.status_code == 200
    assert verify.get_json()["data"]["order"]["status"] != "paid"
    _send_webhook(client, kshop["paystack"], "charge.success", tx)  # forged "success"
    assert _count(kshop["app"], Entitlement) == 0
    downloads = client.post(
        f"/api/v1/checkout/guest-orders/{oid}/downloads",
        json={"entitlement_id": 1, "version_id": 1},
        headers={HEADER: token},
    )
    assert downloads.status_code == 404
    # A payment of the wrong amount or currency is never accepted either.
    data = _guest(client, kshop).get_json()["data"]
    tx = kshop["paystack"].pay(data["order"]["payment"]["reference"], currency="USD")
    _send_webhook(client, kshop["paystack"], "charge.success", tx)
    assert _count(kshop["app"], Entitlement) == 0


def test_guest_checkout_can_be_switched_off(kshop, client):
    _settings(kshop, **{"shop.guest_checkout": False})
    assert _site(client)["guest_checkout"] is False
    res = _guest(client, kshop)
    assert res.status_code == 403
    assert res.get_json()["error"]["code"] == "guest_checkout_disabled"
    assert not [c for c in kshop["paystack"].calls if c[1].endswith("initialize")]
    # Signed-in checkout is unaffected.
    assert _checkout(kshop["shopper"], [kshop["public_id"]], currency="KES").status_code == 201
    quote = (
        kshop["shopper"]
        .post(
            "/api/v1/cart/quote",
            {"items": [{"product_id": kshop["public_id"]}], "currency": "KES"},
        )
        .get_json()["data"]
    )
    assert quote["checkout"]["guest_checkout"] is False
    _settings(kshop, **{"shop.guest_checkout": True})
    assert _guest(client, kshop).status_code == 201


def test_claiming_guest_purchases_needs_the_confirmed_email(kshop, client):
    data = _guest(client, kshop, email="claim@example.com").get_json()["data"]
    tx = kshop["paystack"].pay(data["order"]["payment"]["reference"])
    assert _send_webhook(client, kshop["paystack"], "charge.success", tx).status_code == 200
    account = Shopper(kshop["app"].test_client())
    res = account.post(
        "/api/v1/account/register",
        {
            "email": "claim@example.com",
            "password": PASSWORD,
            "display_name": "Claire",
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert res.status_code in (200, 201), res.get_json()
    # Not before the address is confirmed…
    assert account.get("/api/v1/account/library").get_json()["data"] == []
    message = [m for m in MemoryBackend.outbox if m.to == "claim@example.com"][-1]
    token = message.text.split("#token=", 1)[1].split()[0]
    assert account.post("/api/v1/account/verify-email", {"token": token}).status_code == 200
    # …then the purchase is in the library, still bound by the download rules.
    library = account.get("/api/v1/account/library").get_json()["data"]
    assert len(library) == 1
    item = library[0]
    version = item["files"][0]["versions"][0]
    link = account.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    assert kshop["app"].test_client().get(link).status_code == 403  # bound to the session
    assert account.get(link).status_code == 200
