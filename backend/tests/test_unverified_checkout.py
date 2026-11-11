"""Buying digital products before confirming the account email.

A confirmed email is not required to pay: the order belongs to the signed-in account,
access is granted only after Paystack verifies the payment, and downloads need that
account's session. Guest checkout is unchanged, guest-checkout purchases still need a
confirmed email to appear in an account, and a pre-registered account can't capture
anyone else's purchases.
"""

# ruff: noqa: F811 - the shared ``shop``/``gshop`` fixtures are imported from their modules

from __future__ import annotations

import pytest

from app.extensions import db
from app.models import Customer, EmailDelivery, Entitlement, Order
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Shopper, register_customer
from .test_commerce_checkout import (  # noqa: F401
    _checkout,
    _library_file,
    _send_webhook,
    shop,
)
from .test_guest_checkout import _mail_to, _paid_guest_order, _token_from, gshop  # noqa: F401


def _customer(app, email):
    with app.app_context():
        customer = db.session.scalar(db.select(Customer).where(Customer.email == email))
        return customer.id, customer.email_verified_at


def _order_row(app, public_id):
    with app.app_context():
        order = db.session.scalar(db.select(Order).where(Order.public_id == public_id))
        return order.customer_id, order.is_guest, order.status, order.email


def _pay(store, client, order):
    """Paystack charges the card and sends its signed webhook (the only way to fulfil)."""
    tx = store["paystack"].pay(order["payment"]["reference"])
    assert _send_webhook(client, store["paystack"], "charge.success", tx).status_code == 200


@pytest.mark.parametrize("verified", [True, False], ids=["verified", "unverified"])
def test_signed_in_customers_buy_with_or_without_a_confirmed_email(shop, client, verified):
    app = shop["app"]
    email = f"{'confirmed' if verified else 'new'}@example.com"
    MemoryBackend.outbox.clear()
    buyer = register_customer(app, email, verify=verified)
    # Registration still sends the confirmation email.
    assert any("/verify-email#token=" in m.text for m in _mail_to(email))
    customer_id, verified_at = _customer(app, email)
    assert (verified_at is not None) is verified

    res = _checkout(buyer, [shop["public_id"]])
    assert res.status_code == 201, res.get_json()
    order = res.get_json()["data"]["order"]
    owner, is_guest, status, order_email = _order_row(app, order["id"])
    assert (owner, is_guest, status, order_email) == (customer_id, False, "awaiting_payment", email)
    init = [body for _, path, body in shop["paystack"].calls if path == "/transaction/initialize"]
    assert init[-1]["email"] == email and init[-1]["reference"] == order["payment"]["reference"]

    # Nothing is granted before Paystack confirms the payment.
    assert buyer.get("/api/v1/account/library").get_json()["data"] == []
    pending = buyer.post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    assert pending["order"]["status"] == "awaiting_payment"
    assert buyer.get("/api/v1/account/library").get_json()["data"] == []

    _pay(shop, client, order)
    assert buyer.get(f"/api/v1/account/orders/{order['id']}").get_json()["data"]["status"] == "paid"
    item, version = _library_file(buyer)
    grant = buyer.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert grant.status_code == 200
    url = grant.get_json()["data"]["url"]
    download = buyer.get(url)
    assert download.status_code == 200 and download.data.startswith(b"%PDF")
    with app.app_context():
        entitlement = db.session.scalar(db.select(Entitlement))
        assert entitlement.customer_id == customer_id and entitlement.status == "active"
    # Buying doesn't confirm the address, and the paid emails carry no access link (the
    # library needs this account's session).
    assert (_customer(app, email)[1] is not None) is verified
    paid_mail = [m for m in _mail_to(email) if "/verify-email" not in m.text]
    assert paid_mail and not any("#token=" in m.text for m in paid_mail)


def test_unverified_customers_downloads_stay_private(shop, client):
    app = shop["app"]
    buyer = register_customer(app, "new@example.com", verify=False)
    order = _checkout(buyer, [shop["public_id"]]).get_json()["data"]["order"]
    _pay(shop, client, order)
    item, version = _library_file(buyer)
    url = buyer.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    # Without the buyer's session, the link and the entitlement are useless.
    assert client.get(url).status_code == 403
    other = register_customer(app, "other@example.com", verify=False)
    assert other.get(url).status_code == 403
    assert other.get("/api/v1/account/library").get_json()["data"] == []
    assert other.get(f"/api/v1/account/orders/{order['id']}").status_code == 404
    res = other.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 404
    # Another customer can't verify, retry or cancel the order either.
    assert other.post(f"/api/v1/checkout/orders/{order['id']}/verify").status_code == 404


def test_unverified_customers_failed_payment_grants_nothing_and_can_retry(shop, client):
    app = shop["app"]
    buyer = register_customer(app, "new@example.com", verify=False)
    order = _checkout(buyer, [shop["public_id"]]).get_json()["data"]["order"]
    shop["paystack"].pay(order["payment"]["reference"], status="failed")
    status = buyer.post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    assert status["outcome"] == "failed" and status["order"]["status"] == "failed"
    assert buyer.get("/api/v1/account/library").get_json()["data"] == []
    with app.app_context():
        assert db.session.scalar(db.select(Entitlement)) is None
        assert db.session.scalar(
            db.select(EmailDelivery.status).where(EmailDelivery.template == "payment_failed")
        )
    retry = buyer.post(f"/api/v1/checkout/orders/{order['id']}/retry").get_json()["data"]
    new_reference = retry["order"]["payment"]["reference"]
    assert new_reference != order["payment"]["reference"]
    shop["paystack"].pay(new_reference)
    status = buyer.post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    assert status["order"]["status"] == "paid"
    assert len(buyer.get("/api/v1/account/library").get_json()["data"]) == 1


def test_wrong_amount_from_an_unverified_customer_is_not_fulfilled(shop, client):
    buyer = register_customer(shop["app"], "new@example.com", verify=False)
    order = _checkout(buyer, [shop["public_id"]]).get_json()["data"]["order"]
    tx = shop["paystack"].pay(order["payment"]["reference"], amount=100)  # less than the total
    res = _send_webhook(client, shop["paystack"], "charge.success", tx)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "rejected"
    status = _order_row(shop["app"], order["id"])[2]
    assert status != "paid"
    assert buyer.get("/api/v1/account/library").get_json()["data"] == []


def test_test_mode_still_limits_checkout_to_test_accounts(shop):
    stranger = register_customer(
        shop["app"], "stranger@example.com", verify=False, test_account=False
    )
    res = _checkout(stranger, [shop["public_id"]], expected=1500)
    assert res.status_code == 409 and res.get_json()["error"]["code"] == "checkout_closed"


# ---- guest checkout and ownership -----------------------------------------------------------


def test_guest_checkout_is_unchanged(gshop, client):
    order, order_token = _paid_guest_order(gshop, client)
    owner, is_guest, status, _ = _order_row(gshop["app"], order["id"])
    assert is_guest and status == "paid"
    # The emailed access link still opens the guest purchase.
    link = [m for m in _mail_to("buyer@example.com") if "/purchases#token=" in m.text][-1]
    library = client.post("/api/v1/guest/library", json={"token": _token_from(link)})
    assert library.status_code == 200 and len(library.get_json()["data"]["library"]) == 1


def test_unverified_account_sees_its_own_purchase_but_not_guest_purchases(gshop, client):
    """Someone registers the buyer's email without confirming it: they can buy for
    themselves, but the real owner's guest purchases stay hidden from them."""
    _paid_guest_order(gshop, client, email="buyer@example.com")
    squatter = Shopper(gshop["app"].test_client())
    squatter.c.post(
        "/api/v1/account/register",
        json={
            "email": "buyer@example.com",
            "password": PASSWORD,
            "display_name": "Mallory",
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert squatter.get("/api/v1/account/library").get_json()["data"] == []
    with gshop["app"].app_context():
        account = db.session.scalar(
            db.select(Customer).where(Customer.email == "buyer@example.com")
        )
        account.is_test_account = True
        db.session.commit()
    order = _checkout(squatter, [gshop["public_id"]]).get_json()["data"]["order"]
    _pay(gshop, client, order)
    library = squatter.get("/api/v1/account/library").get_json()["data"]
    orders = squatter.get("/api/v1/account/orders").get_json()["data"]
    # Only the account's own order: the guest order for the same product stays hidden.
    assert [o["id"] for o in orders] == [order["id"]]
    assert len(library) == 1
    with gshop["app"].app_context():
        rows = db.session.execute(
            db.select(Entitlement.order_id, Order.is_guest).join(
                Order, Order.id == Entitlement.order_id
            )
        ).all()
        assert sorted(is_guest for _, is_guest in rows) == [False, True]


def test_the_inbox_owner_takes_back_a_pre_registered_account(gshop, client):
    """A password reset proves the inbox, confirms the email and signs the squatter out."""
    squatter = register_customer(gshop["app"], "victim@example.com", verify=False)
    order = _checkout(squatter, [gshop["public_id"]]).get_json()["data"]["order"]
    _pay(gshop, client, order)
    anon = gshop["app"].test_client()
    anon.post("/api/v1/account/password-reset", json={"email": "victim@example.com"})
    reset = _token_from(_mail_to("victim@example.com")[-1])
    new = "Owner-Owns-This-Inbox-77"
    res = anon.post(
        "/api/v1/account/password-reset/complete", json={"token": reset, "password": new}
    )
    assert res.status_code == 200
    assert squatter.get("/api/v1/account/me").status_code == 401
    assert squatter.get("/api/v1/account/library").status_code == 401
    stale = anon.post(
        "/api/v1/account/login", json={"email": "victim@example.com", "password": PASSWORD}
    )
    assert stale.status_code == 401
    assert _customer(gshop["app"], "victim@example.com")[1] is not None


def test_registering_an_existing_unverified_email_changes_nothing(shop):
    first = register_customer(shop["app"], "new@example.com", verify=False)
    customer_id, _ = _customer(shop["app"], "new@example.com")
    second = Shopper(shop["app"].test_client())
    res = second.c.post(
        "/api/v1/account/register",
        json={
            "email": "new@example.com",
            "password": "Another-Password-123",
            "display_name": "Mallory",
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert res.status_code == 201 and res.get_json()["data"]["signed_in"] is False
    assert second.get("/api/v1/account/me").status_code == 401  # not signed in as them
    assert first.get("/api/v1/account/me").status_code == 200
    assert _customer(shop["app"], "new@example.com")[0] == customer_id
    login = second.c.post(
        "/api/v1/account/login",
        json={"email": "new@example.com", "password": "Another-Password-123"},
    )
    assert login.status_code == 401
