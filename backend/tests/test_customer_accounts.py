"""Batch 07.5: customer registration, sign-in, recovery, account management and isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.extensions import db, limiter
from app.models import AuditLog, Customer, CustomerSession, Subscriber
from app.services.mail import MemoryBackend

from .conftest import PASSWORD, Shopper, register_customer
from .test_commerce_checkout import _paid_order, shop  # noqa: F401  (fixture)
from .test_newsletter import newsletter  # noqa: F401  (fixture)

REG = "/api/v1/account/register"
LOGIN = "/api/v1/account/login"


def _form(**extra):
    return {
        "display_name": "Ada Reader",
        "email": "ada@example.com",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "accept_terms": True,
        **extra,
    }


def _token(email, marker):
    message = [m for m in MemoryBackend.outbox if m.to == email and marker in m.text][-1]
    return message.text.split(f"{marker}#token=", 1)[1].split()[0]


# ---- registration -----------------------------------------------------------------------


def test_registration_validates_name_password_and_confirmation(seeded, client):
    res = client.post(REG, json=_form(display_name="  "))
    assert res.status_code == 400 and "display_name" in res.get_json()["error"]["details"]
    res = client.post(REG, json=_form(password_confirm="Something-Else-42"))
    assert res.status_code == 400 and "password_confirm" in res.get_json()["error"]["details"]
    res = client.post(REG, json=_form(password="short", password_confirm="short"))
    assert res.status_code == 400 and "password" in res.get_json()["error"]["details"]
    res = client.post(REG, json=_form(accept_terms=False))
    assert res.status_code == 400 and "accept_terms" in res.get_json()["error"]["details"]
    res = client.post(REG, json=_form(newsletter_opt_in="yes"))
    assert res.status_code == 400
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(Customer.id))) == 0


def test_registration_sends_verification_link_to_the_new_route(seeded, client):
    MemoryBackend.outbox.clear()
    res = client.post(REG, json=_form())
    assert res.status_code == 201
    body = res.get_json()["data"]
    assert body["signed_in"] is True and body["customer"]["email_verified"] is False
    assert body["newsletter"] == "not_requested"
    message = MemoryBackend.outbox[-1]
    assert "/verify-email#token=" in message.text and "/account/verify-email" not in message.text


def test_duplicate_registration_reveals_nothing(seeded):
    register_customer(seeded, email="ada@example.com", verify=False)
    MemoryBackend.outbox.clear()
    other = seeded.test_client()
    res = other.post(REG, json=_form(display_name="Someone Else"))
    fresh = seeded.test_client().post(REG, json=_form(email="new@example.com"))
    assert res.status_code == fresh.status_code == 201
    assert res.get_json()["data"]["signed_in"] is False
    assert set(res.get_json()["data"]) <= {"registered", "signed_in", "newsletter"}
    assert other.get_cookie("tpa_customer") is None
    # The owner is told by email instead (password reset link), never the requester.
    owner_mail = [m for m in MemoryBackend.outbox if m.to == "ada@example.com"]
    assert owner_mail and "/reset-password#token=" in owner_mail[-1].text


def test_newsletter_consent_is_explicit_and_double_opt_in(newsletter, client):  # noqa: F811
    assert client.post(REG, json=_form()).status_code == 201
    with newsletter.app_context():
        assert (
            db.session.scalar(db.select(Subscriber).where(Subscriber.email == "ada@example.com"))
            is None
        )
    other = newsletter.test_client()
    res = other.post(REG, json=_form(email="bo@example.com", newsletter_opt_in=True))
    assert res.status_code == 201 and res.get_json()["data"]["newsletter"] == "check_email"
    with newsletter.app_context():
        sub = db.session.scalar(db.select(Subscriber).where(Subscriber.email == "bo@example.com"))
        assert sub.status == "pending" and sub.source == "account" and sub.confirmed_at is None
    # Existing accounts get the same newsletter answer (no enumeration through it).
    limiter.reset()
    again = newsletter.test_client().post(
        REG, json=_form(email="bo@example.com", newsletter_opt_in=True)
    )
    assert again.get_json()["data"]["newsletter"] == "check_email"


def test_newsletter_opt_in_is_ignored_when_signups_are_closed(seeded, client):
    res = client.post(REG, json=_form(newsletter_opt_in=True))
    assert res.status_code == 201 and res.get_json()["data"]["newsletter"] == "unavailable"
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(Subscriber.id))) == 0


# ---- sign-in, sessions and sign-out -------------------------------------------------------


def _session_cookie(client):
    return client.get_cookie("tpa_customer", path="/api/v1/")


def test_keep_me_signed_in_controls_cookie_persistence_and_expiry(seeded):
    register_customer(seeded, email="ada@example.com", verify=False)
    short = seeded.test_client()
    assert (
        short.post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD}).status_code
        == 200
    )
    assert _session_cookie(short).expires is None  # ends with the browser session
    persistent = seeded.test_client()
    res = persistent.post(
        LOGIN, json={"email": "ada@example.com", "password": PASSWORD, "remember": True}
    )
    assert res.status_code == 200 and _session_cookie(persistent).expires is not None
    assert _session_cookie(persistent).http_only
    with seeded.app_context():
        sessions = db.session.scalars(db.select(CustomerSession).order_by(CustomerSession.id)).all()
        now = datetime.now(UTC)
        lifetimes = [
            (s.expires_at.replace(tzinfo=s.expires_at.tzinfo or UTC) - now) for s in sessions[-2:]
        ]
        assert lifetimes[0] <= timedelta(hours=12) and lifetimes[1] > timedelta(days=29)


def test_expired_and_signed_out_sessions_are_refused(seeded):
    shopper = register_customer(seeded, email="ada@example.com", verify=False)
    assert shopper.get("/api/v1/account/me").status_code == 200
    with seeded.app_context():
        for s in db.session.scalars(db.select(CustomerSession)):
            s.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    assert shopper.get("/api/v1/account/me").status_code == 401
    fresh = Shopper(seeded.test_client())
    fresh.c.post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD})
    assert fresh.post("/api/v1/account/logout").status_code == 200
    assert fresh.get("/api/v1/account/me").status_code == 401
    with seeded.app_context():
        actions = [a.action for a in db.session.scalars(db.select(AuditLog))]
        assert "customer.login" in actions and "customer.logout" in actions


def test_unverified_customers_can_sign_in_but_are_flagged(seeded):
    register_customer(seeded, email="ada@example.com", verify=False)
    res = seeded.test_client().post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD})
    assert res.status_code == 200 and res.get_json()["data"]["customer"]["email_verified"] is False


def test_login_failures_are_generic_and_rate_limited(seeded):
    register_customer(seeded, email="ada@example.com", verify=False)
    c = seeded.test_client()
    wrong = c.post(LOGIN, json={"email": "ada@example.com", "password": "Wrong-password-123"})
    unknown = c.post(LOGIN, json={"email": "nobody@example.com", "password": "Wrong-password-123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]
    codes = [
        c.post(
            LOGIN, json={"email": "ada@example.com", "password": "Wrong-password-123"}
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codes


# ---- verification and recovery ------------------------------------------------------------


def test_public_verification_resend_is_generic_and_limited(seeded, client):
    register_customer(seeded, email="ada@example.com", verify=False)
    MemoryBackend.outbox.clear()
    url = "/api/v1/account/verify-email/request"
    known = client.post(url, json={"email": "ada@example.com"})
    unknown = client.post(url, json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert [m.to for m in MemoryBackend.outbox] == ["ada@example.com"]
    # The newest link replaces the older ones.
    token = _token("ada@example.com", "/verify-email")
    assert client.post("/api/v1/account/verify-email", json={"token": token}).status_code == 200
    MemoryBackend.outbox.clear()
    client.post(url, json={"email": "ada@example.com"})
    assert MemoryBackend.outbox == []  # already verified: nothing sent
    codes = [client.post(url, json={"email": "ada@example.com"}).status_code for _ in range(4)]
    assert codes[-1] == 429


def test_password_reset_is_single_use_expiring_and_ends_all_sessions(seeded):
    shopper = register_customer(seeded, email="ada@example.com", verify=False)
    other_device = Shopper(seeded.test_client())
    other_device.c.post(
        LOGIN, json={"email": "ada@example.com", "password": PASSWORD, "remember": True}
    )
    anon = seeded.test_client()
    MemoryBackend.outbox.clear()
    assert (
        anon.post("/api/v1/account/password-reset", json={"email": "ada@example.com"}).status_code
        == 200
    )
    first = _token("ada@example.com", "/reset-password")
    anon.post("/api/v1/account/password-reset", json={"email": "ada@example.com"})
    second = _token("ada@example.com", "/reset-password")
    complete = "/api/v1/account/password-reset/complete"
    new_password = "A-brand-new-Passw0rd!"
    assert anon.post(complete, json={"token": first, "password": new_password}).status_code == 400
    assert anon.post(complete, json={"token": second, "password": new_password}).status_code == 200
    assert anon.post(complete, json={"token": second, "password": new_password}).status_code == 400
    assert shopper.get("/api/v1/account/me").status_code == 401
    assert other_device.get("/api/v1/account/me").status_code == 401
    ok = seeded.test_client().post(
        LOGIN, json={"email": "ada@example.com", "password": new_password}
    )
    assert ok.status_code == 200
    # Expired links are refused.
    anon.post("/api/v1/account/password-reset", json={"email": "ada@example.com"})
    expired = _token("ada@example.com", "/reset-password")
    with seeded.app_context():
        from app.models import CustomerToken

        for t in db.session.scalars(
            db.select(CustomerToken).where(CustomerToken.used_at.is_(None))
        ):
            t.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    assert (
        anon.post(
            complete, json={"token": expired, "password": "Yet-another-Passw0rd!"}
        ).status_code
        == 400
    )


# ---- account management -------------------------------------------------------------------


def test_profile_password_change_export_and_deletion_need_reauthentication(seeded):
    shopper = register_customer(seeded, email="ada@example.com")
    assert shopper.patch("/api/v1/account/me", {"display_name": ""}).status_code == 400
    assert shopper.patch("/api/v1/account/me", {"email": "x@example.com"}).status_code == 400
    assert shopper.patch("/api/v1/account/me", {"display_name": "Ada L."}).status_code == 200
    other_device = Shopper(seeded.test_client())
    other_device.c.post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD})
    bad = shopper.post(
        "/api/v1/account/password", {"current_password": "nope", "new_password": "x"}
    )
    assert bad.status_code == 401
    changed = shopper.post(
        "/api/v1/account/password",
        {"current_password": PASSWORD, "new_password": "A-brand-new-Passw0rd!"},
    )
    assert changed.status_code == 200
    assert shopper.get("/api/v1/account/me").status_code == 200  # this device stays signed in
    assert other_device.get("/api/v1/account/me").status_code == 401  # others are signed out
    assert shopper.get("/api/v1/account/export").status_code == 405
    assert shopper.post("/api/v1/account/export", {"password": PASSWORD}).status_code == 401
    export = shopper.post("/api/v1/account/export", {"password": "A-brand-new-Passw0rd!"})
    assert (
        export.status_code == 200
        and export.get_json()["data"]["profile"]["email"] == "ada@example.com"
    )
    assert shopper.post("/api/v1/account/delete", {"password": PASSWORD}).status_code == 401
    assert (
        shopper.post("/api/v1/account/delete", {"password": "A-brand-new-Passw0rd!"}).status_code
        == 200
    )
    assert shopper.get("/api/v1/account/me").status_code == 401


def test_account_newsletter_status_and_opt_in(newsletter):  # noqa: F811
    shopper = register_customer(newsletter, email="ada@example.com")
    status = shopper.get("/api/v1/account/newsletter").get_json()["data"]
    assert status["available"] is True and status["status"] == "none"
    assert status["preferences_token"] is None
    assert shopper.post("/api/v1/account/newsletter", {}).status_code == 400  # consent required
    res = shopper.post(
        "/api/v1/account/newsletter",
        {"consent": True, "consent_version": status["consent_version"]},
    )
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "check_email"
    status = shopper.get("/api/v1/account/newsletter").get_json()["data"]
    assert status["status"] == "pending" and status["preferences_token"]
    assert newsletter.test_client().get("/api/v1/account/newsletter").status_code == 401


# ---- isolation ----------------------------------------------------------------------------


def test_customers_cannot_reach_each_others_orders_library_or_downloads(shop, client):  # noqa: F811
    order = _paid_order(shop, client)
    owner = shop["shopper"]
    library = owner.get("/api/v1/account/library").get_json()["data"]
    assert len(library) == 1
    intruder = register_customer(shop["app"], email="intruder@example.com")
    assert intruder.get("/api/v1/account/orders").get_json()["data"] == []
    assert intruder.get(f"/api/v1/account/orders/{order['id']}").status_code == 404
    assert intruder.get("/api/v1/account/library").get_json()["data"] == []
    item = library[0]
    version = item["files"][0]["versions"][0]["version_id"]
    res = intruder.post(f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version})
    assert res.status_code == 404  # another customer's entitlement is invisible, not forbidden
    ok = owner.post(f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version})
    assert ok.status_code == 200
    anon = shop["app"].test_client()
    assert anon.get("/api/v1/account/orders").status_code == 401
    assert anon.get("/api/v1/account/library").status_code == 401


def test_ended_session_is_reported_once_and_its_cookies_cleared(seeded):
    shopper = register_customer(seeded, email="ada@example.com", verify=False)
    with seeded.app_context():
        for s in db.session.scalars(db.select(CustomerSession)):
            s.revoked_at = datetime.now(UTC)
        db.session.commit()
    res = shopper.get("/api/v1/account/me")
    assert res.status_code == 401 and res.get_json()["error"]["code"] == "session_expired"
    assert shopper.c.get_cookie("tpa_customer", path="/api/v1/") is None
    assert shopper.c.get_cookie("tpa_customer_csrf") is None
    again = shopper.get("/api/v1/account/me")
    assert (
        again.status_code == 401 and again.get_json()["error"]["code"] == "customer_auth_required"
    )
