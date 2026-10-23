"""The Positive Reset: signup and consent, suppression, campaigns, the email queue,
automations, lead magnets and permissions."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db, limiter
from app.models import (
    Campaign,
    Customer,
    EmailAutomation,
    EmailMessage,
    EmailSuppression,
    LeadMagnetClaim,
    SiteSetting,
    Subscriber,
    SubscriberEvent,
)
from app.services.newsletter.providers import MemoryProvider, PermanentSendError, TransientSendError
from app.services.newsletter.worker import run_cycle

from .conftest import minimal_pdf, register_customer
from .test_commerce_catalogue import PRODUCTS, _create

SUB = "/api/v1/newsletter/subscribe"
ADMIN = "/api/v1/admin"


def _set(app, **values):
    with app.app_context():
        for key, value in values.items():
            record = db.session.get(SiteSetting, key) or SiteSetting(key=key)
            record.value = value
            db.session.add(record)
        db.session.commit()


@pytest.fixture()
def newsletter(seeded):
    """Signup open and sending live (readiness is tested separately)."""
    MemoryProvider.outbox.clear()
    MemoryProvider.fail_with.clear()
    _set(seeded, **{"newsletter.is_open": True, "email.sending_mode": "live"})
    return seeded


def _signup(client, email="reader@example.com", **extra):
    payload = {"email": email, "first_name": "Ada", "consent": True, "source": "footer", **extra}
    return client.post(SUB, json=payload)


def _work(app, times=1):
    with app.app_context():
        for _ in range(times):
            result = run_cycle(worker="test-worker")
        db.session.remove()
    return result


def _link_token(email, path):
    for message in reversed(MemoryProvider.outbox):
        if message.to == email and path in message.text:
            return message.text.split(f"{path}#token=", 1)[1].split()[0]
    raise AssertionError(f"no {path} email for {email}")


def _subscribe_confirmed(app, client, email="reader@example.com", **extra):
    assert _signup(client, email, **extra).status_code == 202
    _work(app)
    token = _link_token(email, "/newsletter/confirm")
    res = client.post("/api/v1/newsletter/confirm", json={"token": token})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]["preferences_token"]


def _subscriber(app, email="reader@example.com"):
    with app.app_context():
        return db.session.scalar(db.select(Subscriber).where(Subscriber.email == email))


# ---- signup, consent, verification ------------------------------------------------------


def test_signup_is_closed_until_sending_is_configured(seeded, client):
    site = client.get("/api/v1/site").get_json()["data"]
    assert site["newsletter"]["is_open"] is False and site["newsletter"]["consent_text"] == ""
    _set(seeded, **{"newsletter.is_open": True})  # the switch alone is not enough
    assert client.get("/api/v1/newsletter/status").get_json()["data"]["signup_open"] is False
    assert _signup(client).status_code == 409
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(Subscriber.id))) == 0


def test_double_opt_in_records_consent_evidence(newsletter, client):
    res = _signup(client, "Reader@Example.com ")
    assert res.status_code == 202 and res.get_json()["data"]["status"] == "check_email"
    pending = _subscriber(newsletter)
    assert pending.status == "pending" and not pending.is_marketable
    assert pending.consent_at and pending.consent_version == "2026-10"
    assert "unsubscribe" in pending.consent_text.lower() and len(pending.consent_ip_hash) == 64
    assert pending.source == "footer" and pending.preferences == ["weekly"]
    _work(newsletter)
    message = MemoryProvider.outbox[-1]
    assert message.to == "reader@example.com" and "Confirm" in message.html
    assert "List-Unsubscribe" not in message.headers  # transactional, not marketing
    token = _link_token("reader@example.com", "/newsletter/confirm")
    assert client.post("/api/v1/newsletter/confirm", json={"token": token}).status_code == 200
    assert client.post("/api/v1/newsletter/confirm", json={"token": token}).status_code == 200
    confirmed = _subscriber(newsletter)
    assert confirmed.status == "subscribed" and confirmed.confirmed_at and confirmed.is_marketable
    with newsletter.app_context():
        events = [e.event for e in db.session.scalars(db.select(SubscriberEvent))]
    assert events == ["signup", "confirmed"]
    bad = client.post("/api/v1/newsletter/confirm", json={"token": token[:-2] + "00"})
    assert bad.status_code == 400


def test_consent_is_required_and_changed_wording_is_detected(newsletter, client):
    res = client.post(SUB, json={"email": "a@example.com", "consent": False})
    assert res.status_code == 400 and "consent" in res.get_json()["error"]["details"]
    res = _signup(client, "b@example.com", consent_version="2025-01")
    assert res.status_code == 409


def test_duplicates_never_reveal_subscription_status(newsletter, client):
    first = _signup(client).get_json()
    second = _signup(client).get_json()
    assert first == second
    _work(newsletter)
    confirmations = [m for m in MemoryProvider.outbox if "/newsletter/confirm" in m.text]
    assert len(confirmations) == 1  # resend throttled
    token = _link_token("reader@example.com", "/newsletter/confirm")
    client.post("/api/v1/newsletter/confirm", json={"token": token})
    limiter.reset()
    assert _signup(client).get_json() == first  # already subscribed: same response
    _work(newsletter)
    notices = [m for m in MemoryProvider.outbox if "already subscribed" in m.subject]
    assert len(notices) == 1
    with newsletter.app_context():
        assert db.session.scalar(db.select(db.func.count(Subscriber.id))) == 1


def test_spam_protection_and_rate_limits(newsletter, client):
    assert _signup(client, "bot@example.com", website="http://spam").status_code == 202
    assert _signup(client, "fast@example.com", elapsed_ms=300).status_code == 202
    assert _subscriber(newsletter, "bot@example.com") is None
    assert _subscriber(newsletter, "fast@example.com") is None
    codes = [_signup(client, "same@example.com").status_code for _ in range(4)]
    assert codes[-1] == 429


def test_customers_are_never_subscribed_automatically(newsletter):
    register_customer(newsletter, "buyer@example.com")
    assert _subscriber(newsletter, "buyer@example.com") is None
    with newsletter.app_context():
        assert db.session.scalar(db.select(Customer).where(Customer.email == "buyer@example.com"))


# ---- unsubscribe and suppression --------------------------------------------------------


def test_one_click_unsubscribe_suppresses_and_resubscribe_needs_fresh_consent(newsletter, client):
    token = _subscribe_confirmed(newsletter, client)
    res = client.post(
        f"/api/v1/newsletter/unsubscribe/one-click?token={token}",
        data="List-Unsubscribe=One-Click",
        content_type="application/x-www-form-urlencoded",
    )
    assert res.status_code == 200
    gone = _subscriber(newsletter)
    assert gone.status == "unsubscribed" and gone.unsubscribed_at
    with newsletter.app_context():
        assert db.session.scalar(db.select(EmailSuppression)).reason == "unsubscribed"
        audit = db.session.scalar(
            db.select(SubscriberEvent).where(SubscriberEvent.event == "unsubscribed")
        )
        assert audit.details["via"] == "one_click"
    # Returning requires a new confirmation; suppression lifts only after confirming.
    limiter.reset()
    _signup(client)
    assert _subscriber(newsletter).status == "pending"
    with newsletter.app_context():
        assert db.session.scalar(db.select(db.func.count(EmailSuppression.id))) == 1
    _work(newsletter)
    confirm = _link_token("reader@example.com", "/newsletter/confirm")
    client.post("/api/v1/newsletter/confirm", json={"token": confirm})
    assert _subscriber(newsletter).status == "subscribed"
    with newsletter.app_context():
        assert db.session.scalar(db.select(db.func.count(EmailSuppression.id))) == 0
    # Preferences page works with the manage token, without revealing the full address.
    view = client.post("/api/v1/newsletter/preferences", json={"token": token}).get_json()["data"]
    assert view["email"].startswith("r") and "reader@" not in view["email"]
    res = client.put(
        "/api/v1/newsletter/preferences", json={"token": token, "preferences": ["daily"]}
    )
    assert res.get_json()["data"]["preferences"] == ["daily"]


def _feedback(client, events, secret="testing-feedback-secret"):
    raw = json.dumps({"events": events}).encode()
    stamp = str(int(time.time()))
    sig = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/email/feedback",
        data=raw,
        content_type="application/json",
        headers={"X-TPA-Timestamp": stamp, "X-TPA-Signature": sig},
    )


def test_complaints_suppress_permanently_and_feedback_must_be_signed(newsletter, client):
    _subscribe_confirmed(newsletter, client)
    assert (
        _feedback(
            client, [{"type": "complained", "email": "reader@example.com"}], "wrong"
        ).status_code
        == 401
    )
    assert (
        _feedback(client, [{"type": "complained", "email": "reader@example.com"}]).status_code
        == 200
    )
    assert _subscriber(newsletter).status == "complained"
    sent_before = len(MemoryProvider.outbox)
    limiter.reset()
    assert _signup(client).status_code == 202  # same public response
    _work(newsletter)
    assert (
        len(MemoryProvider.outbox) == sent_before and _subscriber(newsletter).status == "complained"
    )


def test_self_service_erasure_keeps_only_a_hashed_suppression(newsletter, client):
    token = _subscribe_confirmed(newsletter, client)
    assert client.post("/api/v1/newsletter/erase", json={"token": token}).status_code == 200
    assert _subscriber(newsletter) is None
    with newsletter.app_context():
        record = db.session.scalar(db.select(EmailSuppression))
        assert record.reason == "erased" and "reader" not in record.email_hash


# ---- campaigns and targeting ------------------------------------------------------------


def _campaign(admin, **fields):
    if "blocks" in fields:
        fields.setdefault("preheader", "")  # replace the template's guidance
    res = admin.post(f"{ADMIN}/newsletters", {"template_key": "weekly_edition", **fields})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


BODY = [{"type": "paragraph", "text": "Hello {{first_name}}, a short note on starting again."}]


def test_campaign_workflow_targeting_and_idempotent_queue(newsletter, client, as_role):
    admin = as_role("newsletter_manager", email="news@example.org")
    _subscribe_confirmed(newsletter, client, "one@example.com")
    _subscribe_confirmed(newsletter, client, "two@example.com")
    limiter.reset()
    _signup(client, "pending@example.com")  # never confirmed: not in any audience
    campaign = _campaign(admin, name="Weekly #1")
    cid = campaign["id"]
    res = admin.post(f"{ADMIN}/newsletters/{cid}/approve")
    assert res.status_code == 400 and "bracketed" in str(res.get_json())
    admin.patch(
        f"{ADMIN}/newsletters/{cid}", {"subject": "Starting again", "preheader": "", "blocks": BODY}
    )
    assert admin.post(f"{ADMIN}/newsletters/{cid}/approve").status_code == 200
    # Editing an approved campaign withdraws the approval.
    edited = admin.patch(f"{ADMIN}/newsletters/{cid}", {"name": "Weekly #1 (final)"}).get_json()[
        "data"
    ]
    assert edited["status"] == "draft"
    assert admin.post(f"{ADMIN}/newsletters/{cid}/send").status_code == 409
    admin.post(f"{ADMIN}/newsletters/{cid}/approve")
    preview = admin.post(f"{ADMIN}/newsletters/{cid}/preview").get_json()["data"]
    assert "Hello friend" in preview["html"] and "<script" not in preview["html"]
    assert admin.get(f"{ADMIN}/newsletters/{cid}").get_json()["data"]["status"] == "approved"
    assert admin.post(f"{ADMIN}/newsletters/{cid}/send").status_code == 200
    MemoryProvider.outbox.clear()
    _work(newsletter, times=2)
    sent = [m for m in MemoryProvider.outbox if m.subject == "Starting again"]
    assert sorted(m.to for m in sent) == ["one@example.com", "two@example.com"]
    message = sent[0]
    assert message.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "one-click?token=" in message.headers["List-Unsubscribe"]
    assert "{{" not in message.html and "Hello Ada" in message.text
    with newsletter.app_context():
        from app.services.newsletter.campaigns import prepare_sending

        stored = db.session.get(Campaign, cid)
        stored.queued_at = None  # simulate a re-run after an interruption
        stored.status = "sending"
        db.session.commit()
        prepare_sending()
        assert (
            db.session.scalar(
                db.select(db.func.count(EmailMessage.id)).where(EmailMessage.campaign_id == cid)
            )
            == 2
        )
    _work(newsletter)
    report = admin.get(f"{ADMIN}/newsletters/{cid}/report").get_json()["data"]
    assert (
        report["eligible"] == 2 and report["accepted"] == 2 and report["delivered_confirmed"] == 0
    )
    assert report["opens_and_clicks"] is None and report["status"] == "sent"


def test_segments_narrow_the_consenting_audience(newsletter, client, as_role):
    admin = as_role("newsletter_manager", email="news@example.org")
    _subscribe_confirmed(newsletter, client, "daily@example.com", preferences=["daily"])
    _subscribe_confirmed(newsletter, client, "weekly@example.com")
    admin.post(f"{ADMIN}/subscriber-tags", {"name": "Readers"})
    weekly = _subscriber(newsletter, "weekly@example.com")
    admin.put(f"{ADMIN}/subscribers/{weekly.id}/tags", {"tags": ["readers"]})

    def count(rules):
        res = admin.post(f"{ADMIN}/subscriber-segments/preview", {"rules": rules})
        return res.get_json()["data"]["count"]

    assert count([]) == 2
    assert count([{"field": "preference", "op": "has", "value": "daily"}]) == 1
    assert count([{"field": "tag", "op": "has", "value": "readers"}]) == 1
    assert count([{"field": "source", "op": "in", "value": ["homepage"]}]) == 0
    bad = admin.post(
        f"{ADMIN}/subscriber-segments/preview",
        {"rules": [{"field": "email", "op": "has", "value": "x"}]},
    )
    assert bad.status_code == 400


def test_scheduling_and_cancellation(newsletter, client, as_role):
    admin = as_role("newsletter_manager", email="news@example.org")
    _subscribe_confirmed(newsletter, client)
    cid = _campaign(admin, subject="Later", blocks=BODY)["id"]
    admin.post(f"{ADMIN}/newsletters/{cid}/approve")
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert (
        admin.post(f"{ADMIN}/newsletters/{cid}/schedule", {"scheduled_at": past}).status_code == 400
    )
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (
        admin.post(f"{ADMIN}/newsletters/{cid}/schedule", {"scheduled_at": future}).get_json()[
            "data"
        ]["campaign"]["status"]
        == "scheduled"
    )
    _work(newsletter)
    assert admin.get(f"{ADMIN}/newsletters/{cid}").get_json()["data"]["status"] == "scheduled"
    with newsletter.app_context():
        db.session.get(Campaign, cid).scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
        from app.services.newsletter.campaigns import prepare_sending, start_due_scheduled

        start_due_scheduled()
        prepare_sending()  # queued, not yet sent
    res = admin.post(f"{ADMIN}/newsletters/{cid}/cancel")
    assert res.status_code == 200 and res.get_json()["data"]["cancelled_messages"] == 1
    MemoryProvider.outbox.clear()
    _work(newsletter)
    assert MemoryProvider.outbox == []


def test_test_mode_and_test_sends_never_reach_the_audience(newsletter, client, as_role):
    admin = as_role("newsletter_manager", email="news@example.org")
    _subscribe_confirmed(newsletter, client, "reader@example.com")
    _subscribe_confirmed(newsletter, client, "tester@example.org")
    cid = _campaign(admin, subject="Dry run", blocks=BODY)["id"]
    res = admin.post(f"{ADMIN}/newsletters/{cid}/test", {"to": "stranger@example.com"})
    assert res.status_code == 400
    MemoryProvider.outbox.clear()
    res = admin.post(f"{ADMIN}/newsletters/{cid}/test").get_json()["data"]
    assert res["status"] == "accepted" and res["campaign"]["status"] == "draft"
    assert [m.to for m in MemoryProvider.outbox] == ["news@example.org"]
    assert MemoryProvider.outbox[0].subject.startswith("[TEST]")
    _set(newsletter, **{"email.sending_mode": "test"})
    admin.post(f"{ADMIN}/newsletters/{cid}/approve")
    admin.post(f"{ADMIN}/newsletters/{cid}/send")
    MemoryProvider.outbox.clear()
    _work(newsletter, times=2)
    assert [m.to for m in MemoryProvider.outbox] == ["tester@example.org"]
    report = admin.get(f"{ADMIN}/newsletters/{cid}/report").get_json()["data"]
    assert report["skipped_test_mode"] == 1 and report["send_mode"] == "test"


# ---- delivery queue ---------------------------------------------------------------------


def _queue_one(app, email="reader@example.com"):
    with app.app_context():
        from app.services.newsletter.queue import enqueue

        subscriber = db.session.scalar(db.select(Subscriber).where(Subscriber.email == email))
        message = enqueue(
            kind="automation",
            to=email,
            subscriber=subscriber,
            dedupe_key="manual:1",
            subject="Hello",
            html="<p>Hi</p>",
            text="Hi",
        )
        assert (
            enqueue(kind="automation", to=email, subscriber=subscriber, dedupe_key="manual:1")
            is None
        )
        db.session.commit()
        return message.id


def test_transient_failures_retry_and_bounces_suppress(newsletter, client):
    _subscribe_confirmed(newsletter, client)
    message_id = _queue_one(newsletter)
    MemoryProvider.fail_with.append(TransientSendError("Temporary SMTP error (421)."))
    _work(newsletter)
    with newsletter.app_context():
        message = db.session.get(EmailMessage, message_id)
        assert message.status == "queued" and message.attempts == 1 and "421" in message.error
        assert message.next_attempt_at.replace(tzinfo=UTC) > datetime.now(UTC)
        message.next_attempt_at = datetime.now(UTC)
        db.session.commit()
    MemoryProvider.fail_with.append(PermanentSendError("Recipient refused (550).", bounce=True))
    _work(newsletter)
    with newsletter.app_context():
        message = db.session.get(EmailMessage, message_id)
        assert message.status == "bounced" and message.accepted_at is None
    assert _subscriber(newsletter).status == "bounced"


def test_worker_restart_never_sends_twice(newsletter, client):
    _subscribe_confirmed(newsletter, client)
    first = _queue_one(newsletter)
    subscriber = _subscriber(newsletter)
    with newsletter.app_context():
        from app.services.newsletter.queue import enqueue, recover_stale

        message = enqueue(
            kind="automation",
            to=subscriber.email,
            subscriber=subscriber,
            dedupe_key="manual:2",
            subject="Two",
            text="Two",
        )
        db.session.flush()
        second = message.id
        old = datetime.now(UTC) - timedelta(hours=1)
        db.session.get(EmailMessage, first).status = "sending"
        db.session.get(EmailMessage, first).claimed_at = old  # died before sending
        crashed = db.session.get(EmailMessage, second)
        crashed.status, crashed.claimed_at, crashed.attempt_started_at = "sending", old, old
        db.session.commit()
        assert recover_stale() == {"requeued": 1, "unknown": 1}
    MemoryProvider.outbox.clear()
    _work(newsletter)
    assert [m.subject for m in MemoryProvider.outbox] == ["Hello"]
    with newsletter.app_context():
        assert db.session.get(EmailMessage, second).status == "unknown"


def test_sending_disabled_pauses_the_queue(newsletter, client):
    _subscribe_confirmed(newsletter, client)
    _queue_one(newsletter)
    _set(newsletter, **{"email.sending_mode": "disabled"})
    MemoryProvider.outbox.clear()
    result = _work(newsletter)
    assert MemoryProvider.outbox == [] and "disabled" in result["delivery"]["paused"]


# ---- automations ------------------------------------------------------------------------


def test_welcome_automation_sends_once(newsletter, client, as_role):
    admin = as_role("newsletter_manager", email="news@example.org")
    automations = admin.get(f"{ADMIN}/email-automations").get_json()["data"]
    welcome = next(a for a in automations if a["key"] == "confirmed_welcome")
    assert welcome["status"] == "draft"  # starters are never active by default
    blocked = admin.patch(f"{ADMIN}/email-automations/{welcome['id']}", {"status": "active"})
    assert blocked.status_code == 400  # starter guidance must be replaced first
    admin.put(
        f"{ADMIN}/email-automations/{welcome['id']}/steps",
        {
            "steps": [
                {"delay_minutes": 0, "subject": "Welcome to The Positive Reset", "blocks": BODY}
            ]
        },
    )
    assert (
        admin.patch(f"{ADMIN}/email-automations/{welcome['id']}", {"status": "active"}).status_code
        == 200
    )
    _subscribe_confirmed(newsletter, client)
    MemoryProvider.outbox.clear()
    _work(newsletter, times=3)
    welcomes = [m for m in MemoryProvider.outbox if m.subject == "Welcome to The Positive Reset"]
    assert len(welcomes) == 1 and "List-Unsubscribe" in welcomes[0].headers
    detail = admin.get(f"{ADMIN}/email-automations/{welcome['id']}").get_json()["data"]
    assert detail["enrollments"] == {"completed": 1} and detail["messages"] == {"accepted": 1}


def test_product_announcements_honour_the_products_preference(newsletter, client, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    _subscribe_confirmed(newsletter, client, "weekly@example.com")
    _subscribe_confirmed(
        newsletter, client, "shopper@example.com", preferences=["weekly", "products"]
    )
    with newsletter.app_context():
        automation = db.session.scalar(
            db.select(EmailAutomation).where(EmailAutomation.key == "product_announcement")
        )
        aid = automation.id
    res = admin.patch(f"{ADMIN}/email-automations/{aid}", {"required_preference": "weekly"})
    assert res.status_code == 400
    admin.put(
        f"{ADMIN}/email-automations/{aid}/steps",
        {"steps": [{"subject": "Now available", "blocks": BODY}]},
    )
    admin.patch(f"{ADMIN}/email-automations/{aid}", {"status": "active"})
    product = _create(admin, "Free Journal", "journal", short_description="A free journal.")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"pricing_model": "free"})
    admin.upload(f"{PRODUCTS}/{product['id']}/files", minimal_pdf(), "journal.pdf")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    admin.post(f"{PRODUCTS}/{product['id']}/publish")
    admin.post(f"{PRODUCTS}/{product['id']}/publish")  # republishing never announces again
    MemoryProvider.outbox.clear()
    _work(newsletter, times=3)
    assert [m.to for m in MemoryProvider.outbox if m.subject == "Now available"] == [
        "shopper@example.com"
    ]


# ---- lead magnets -----------------------------------------------------------------------


def _lead_magnet(admin, **extra):
    product = _create(admin, "Free Reflection Worksheet", "worksheet", short_description="Free.")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"pricing_model": "free"})
    admin.upload(f"{PRODUCTS}/{product['id']}/files", minimal_pdf(), "worksheet.pdf")
    admin.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    admin.post(f"{PRODUCTS}/{product['id']}/publish")
    res = admin.post(
        f"{ADMIN}/lead-magnets",
        {"title": "Reflection worksheet", "product_id": product["id"], **extra},
    )
    assert res.status_code == 201, res.get_json()
    magnet = res.get_json()["data"]
    assert (
        admin.patch(f"{ADMIN}/lead-magnets/{magnet['id']}", {"status": "active"}).status_code == 200
    )
    return magnet


def test_lead_magnet_delivery_without_forced_subscription(newsletter, client, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    magnet = _lead_magnet(admin)
    info = client.get(f"/api/v1/lead-magnets/{magnet['slug']}").get_json()["data"]
    assert (
        info["available"] and info["newsletter_optin"] == "optional" and info["formats"] == ["PDF"]
    )
    res = client.post(
        f"/api/v1/lead-magnets/{magnet['slug']}/claim", json={"email": "guest@example.com"}
    )
    assert res.status_code == 202
    assert _subscriber(newsletter, "guest@example.com") is None  # no silent subscription
    _work(newsletter)
    token = _link_token("guest@example.com", "/resources/access")
    access = client.post("/api/v1/lead-magnets/access", json={"token": token}).get_json()["data"]
    assert access["files"][0]["format"] == "PDF"
    grant = client.post(
        "/api/v1/lead-magnets/access/download",
        json={"token": token, "file_id": access["files"][0]["id"]},
    ).get_json()["data"]
    download = client.get(grant["url"])
    assert download.status_code == 200 and download.data.startswith(b"%PDF")
    assert "attachment" in download.headers["Content-Disposition"]
    tampered = client.get(grant["url"][:-3] + "abc")
    assert tampered.status_code == 404
    with newsletter.app_context():
        claim = db.session.scalar(db.select(LeadMagnetClaim))
        claim.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
    expired = client.post("/api/v1/lead-magnets/access", json={"token": token})
    assert expired.status_code == 410 and expired.get_json()["error"]["code"] == "link_expired"


def test_lead_magnet_optional_newsletter_uses_double_opt_in(newsletter, client, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    magnet = _lead_magnet(admin)
    client.post(
        f"/api/v1/lead-magnets/{magnet['slug']}/claim",
        json={"email": "fan@example.com", "newsletter_consent": True},
    )
    subscriber = _subscriber(newsletter, "fan@example.com")
    assert subscriber.status == "pending" and subscriber.source == "lead_magnet"
    required = admin.patch(f"{ADMIN}/lead-magnets/{magnet['id']}", {"newsletter_optin": "required"})
    assert required.status_code == 400  # a clear notice is mandatory


# ---- permissions, import/export ---------------------------------------------------------


def test_permissions_follow_least_privilege(newsletter, as_role):
    marketing = as_role("marketing_manager", email="mkt@example.org")
    cid = _campaign(marketing, subject="Hi", blocks=BODY)["id"]
    assert marketing.post(f"{ADMIN}/newsletters/{cid}/approve").status_code == 403
    assert marketing.post(f"{ADMIN}/newsletters/{cid}/send").status_code == 403
    assert marketing.get(f"{ADMIN}/subscribers/export").status_code == 403
    assert marketing.get(f"{ADMIN}/email-settings").status_code == 403
    editor = as_role("editor", email="ed@example.org")
    assert editor.get(f"{ADMIN}/subscribers").status_code == 403
    assert editor.get(f"{ADMIN}/newsletters").status_code == 403
    manager = as_role("newsletter_manager", email="news@example.org")
    assert manager.get(f"{ADMIN}/subscribers/export").status_code == 200
    assert manager.get(f"{ADMIN}/email-settings").status_code == 403  # sensitive
    owner = as_role("super_admin", email="owner@example.org")
    view = owner.get(f"{ADMIN}/email-settings").get_json()["data"]
    assert "password" not in json.dumps(view).lower()
    res = owner.patch(f"{ADMIN}/email-settings", {"sending_mode": "live"})
    assert res.status_code == 400  # readiness checks (live allowed, address, attestations)


def test_imports_are_quarantined_unless_consent_is_attested(newsletter, as_role):
    manager = as_role("newsletter_manager", email="news@example.org")
    csv_text = "email,first_name,consent_at\nold@example.com,Old,2025-01-02T10:00:00Z\nbad,,\n"
    res = manager.post(f"{ADMIN}/subscribers/import", {"content": csv_text}).get_json()["data"]
    assert res["created"] == 1 and res["quarantined"] == 1 and res["invalid"] == 1
    quarantined = _subscriber(newsletter, "old@example.com")
    assert quarantined.status == "quarantined" and not quarantined.is_marketable
    res = manager.post(
        f"{ADMIN}/subscribers/import",
        {
            "content": "email,consent_at\nnew@example.com,2025-01-02T10:00:00Z\n",
            "consent_attested": True,
        },
    )
    assert res.status_code == 400  # attestation needs a description of the consent source
    res = manager.post(
        f"{ADMIN}/subscribers/import",
        {
            "content": "email,consent_at\nnew@example.com,2025-01-02T10:00:00Z\n",
            "consent_attested": True,
            "consent_source": "Double opt-in form on the previous website (2025).",
        },
    ).get_json()["data"]
    assert res["subscribed"] == 1 and _subscriber(newsletter, "new@example.com").is_marketable
    export = manager.get(f"{ADMIN}/subscribers/export")
    assert export.status_code == 200 and b"old@example.com" in export.data
