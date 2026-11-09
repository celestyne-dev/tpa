"""The Positive Reset in collection-only mode.

Website sign-ups are stored with their consent evidence as ``collected`` (the address is
not verified, because no email is sent) and exported for an external email service
provider. No SMTP, worker or NEWSLETTER_LIVE_ALLOWED is needed, and double opt-in keeps
working unchanged when the mode is switched back.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db, limiter
from app.models import (
    AuditLog,
    EmailMessage,
    EmailSuppression,
    SiteSetting,
    Subscriber,
    SubscriberEvent,
)
from app.services.newsletter import tokens
from app.services.newsletter.providers import MemoryProvider

from .test_newsletter import _link_token, _set, _work

SUB = "/api/v1/newsletter/subscribe"
STATUS = "/api/v1/newsletter/status"
EXPORT = "/api/v1/admin/subscribers/export/provider"
SETTINGS = "/api/v1/admin/email-settings"


def _signup(client, email="reader@example.com", **extra):
    payload = {
        "email": email,
        "first_name": "Ada",
        "consent": True,
        "age_confirmed": True,
        "consent_version": "2026-11-collection",
        "source": "article",
        "source_detail": "/articles/a-story",
        **extra,
    }
    return client.post(SUB, json=payload)


def _subscriber(app, email="reader@example.com"):
    with app.app_context():
        return db.session.scalar(db.select(Subscriber).where(Subscriber.email == email))


@pytest.fixture()
def collecting(seeded):
    """Collection-only with NO delivery configured: sending disabled, no mail backend,
    no sender address and live sending not allowed."""
    MemoryProvider.outbox.clear()
    seeded.config.update(
        NEWSLETTER_MAIL_BACKEND="none",
        MAIL_BACKEND="none",
        NEWSLETTER_FROM_EMAIL="",
        NEWSLETTER_LIVE_ALLOWED=False,
    )
    _set(
        seeded,
        **{
            "newsletter.is_open": True,
            "email.sending_mode": "disabled",
            "email.signup_mode": "collection_only",
        },
    )
    return seeded


def _rows(res):
    assert res.status_code == 200, res.get_data(as_text=True)
    return list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))


# ---- readiness ----------------------------------------------------------------------------


def test_collection_only_opens_without_delivery_but_only_when_switched_on(collecting, client):
    status = client.get(STATUS).get_json()["data"]
    assert status["signup_open"] is True and status["signup_mode"] == "collection_only"
    assert status["confirmation_email"] is False
    assert status["consent_version"] == "2026-11-collection"
    text = status["consent_text"]
    assert "daily email newsletter" in text and "store my email address" in text
    assert "email service provider" in text and "unsubscribe" in text
    assert "confirm" not in text.lower()  # promises no confirmation email
    site = client.get("/api/v1/site").get_json()["data"]["newsletter"]
    assert site["is_open"] is True and site["confirmation_email"] is False
    assert site["consent_version"] == "2026-11-collection"
    # The mode alone never opens sign-ups: the "sign-ups open" switch still decides.
    _set(collecting, **{"newsletter.is_open": False})
    closed = client.get(STATUS).get_json()["data"]
    assert closed["signup_open"] is False and closed["consent_text"] == ""
    assert _signup(client).status_code == 409


def test_double_opt_in_still_needs_delivery(seeded, client):
    _set(seeded, **{"newsletter.is_open": True, "email.sending_mode": "disabled"})
    status = client.get(STATUS).get_json()["data"]
    assert status["signup_mode"] == "double_opt_in" and status["signup_open"] is False


def test_signup_mode_is_an_audited_admin_setting_and_the_wording_is_versioned(seeded, as_role):
    manager = as_role("super_admin")
    assert (
        as_role("marketing_manager").patch(SETTINGS, {"signup_mode": "collection_only"}).status_code
        == 403
    )
    assert manager.patch(SETTINGS, {"signup_mode": "everything"}).status_code == 400
    res = manager.patch(SETTINGS, {"signup_mode": "collection_only"})
    assert res.status_code == 200 and res.get_json()["data"]["signup_mode"] == "collection_only"
    # Changing the collection wording needs a new version, so evidence stays exact.
    res = manager.patch(SETTINGS, {"collection_consent_text": "Yes, send me daily emails."})
    assert res.status_code == 400 and "collection_consent_version" in str(res.get_json())
    with seeded.app_context():
        assert db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "email.settings_updated")
        )
        # Switching the mode does not switch sign-ups on.
        assert db.session.get(SiteSetting, "newsletter.is_open") is None


# ---- sign-ups -----------------------------------------------------------------------------


def test_valid_signup_stores_consent_evidence_unverified_and_sends_nothing(collecting, client):
    res = _signup(client, " Reader@Example.com ")
    assert res.status_code == 202
    body = res.get_json()["data"]
    assert body["status"] == "received" and "inbox" not in body["message"]
    sub = _subscriber(collecting)
    assert sub.status == "collected" and sub.first_name == "Ada"
    assert sub.consent_at is not None and sub.consent_version == "2026-11-collection"
    assert "email service provider" in sub.consent_text and len(sub.consent_ip_hash) == 64
    assert sub.source == "article" and sub.source_detail == "/articles/a-story"
    # Not verified: no confirmation was sent and nothing says it was confirmed.
    assert sub.confirmation_sent_at is None and sub.confirmed_at is None
    assert sub.is_marketable is False
    with collecting.app_context():
        assert db.session.scalar(db.select(db.func.count(EmailMessage.id))) == 0
        [signup] = db.session.scalars(db.select(SubscriberEvent)).all()
        assert signup.event == "signup" and signup.details["mode"] == "collection_only"
    assert MemoryProvider.outbox == []


def test_consent_is_required_and_must_match_the_shown_wording(collecting, client):
    res = _signup(client, consent=False)
    assert res.status_code == 400 and "consent" in res.get_json()["error"]["details"]
    assert _signup(client, consent="yes").status_code == 400
    # A form showing the double opt-in wording (an out-of-date page) is asked to reload.
    stale = _signup(client, consent_version="2026-11")
    assert stale.status_code == 409
    assert stale.get_json()["error"]["details"]["code"] == "consent_changed"
    assert _subscriber(collecting) is None
    assert _signup(client, email="not-an-email").status_code == 400


def test_duplicates_create_no_second_record_and_reveal_nothing(collecting, client):
    first = _signup(client).get_json()
    second = _signup(client, first_name="Someone else", source="homepage").get_json()
    assert first == second
    with collecting.app_context():
        assert db.session.scalar(db.select(db.func.count(Subscriber.id))) == 1
    sub = _subscriber(collecting)
    assert sub.first_name == "Ada" and sub.source == "article"


def test_unsubscribed_addresses_are_never_silently_resubscribed(collecting, client):
    _signup(client)
    with collecting.app_context():
        sub = db.session.scalar(db.select(Subscriber))
        sub.status, sub.unsubscribed_at = "unsubscribed", datetime.now(UTC)
        db.session.add(
            EmailSuppression(email_hash=tokens.email_hash(sub.email), reason="unsubscribed")
        )
        db.session.commit()
        evidence = (sub.consent_at, sub.consent_text, sub.consent_version)
    limiter.reset()
    new = _signup(client, "someone-new@example.com").get_json()
    limiter.reset()
    again = _signup(client).get_json()
    assert again == new  # same answer as a brand-new address
    sub = _subscriber(collecting)
    assert sub.status == "unsubscribed"
    assert (sub.consent_at, sub.consent_text, sub.consent_version) == evidence
    with collecting.app_context():
        events = [
            e.event
            for e in db.session.scalars(
                db.select(SubscriberEvent).where(SubscriberEvent.subscriber_id == sub.id)
            )
        ]
    assert events[-1] == "signup_repeated"


def test_existing_subscribers_keep_their_consent_preferences_and_verification(seeded, client):
    """A confirmed double opt-in subscriber who uses a form in collection mode stays
    exactly as they were (no downgrade to unverified, no new consent record)."""
    confirmed_at = datetime.now(UTC) - timedelta(days=30)
    with seeded.app_context():
        db.session.add(
            Subscriber(
                public_id="p1",
                email="reader@example.com",
                first_name="Ada",
                status="subscribed",
                source="footer",
                consent_at=confirmed_at,
                consent_text="Yes, email me The Positive Reset each week.",
                consent_version="2026-10",
                confirmed_at=confirmed_at,
                preferences=["weekly", "products"],
                interests=[],
            )
        )
        db.session.commit()
    _set(
        seeded,
        **{"newsletter.is_open": True, "email.signup_mode": "collection_only"},
    )
    assert _signup(client, first_name="Changed").status_code == 202
    sub = _subscriber(seeded)
    assert sub.status == "subscribed" and sub.is_marketable
    assert sub.consent_version == "2026-10" and sub.preferences == ["weekly", "products"]
    assert sub.first_name == "Ada" and sub.notice_sent_at is None  # nothing emailed


def test_rate_limits_and_bot_traps_still_apply(collecting, client):
    assert _signup(client, "bot@example.com", website="http://spam").status_code == 202
    assert _signup(client, "fast@example.com", elapsed_ms=300).status_code == 202
    assert _subscriber(collecting, "bot@example.com") is None
    assert _subscriber(collecting, "fast@example.com") is None
    codes = [_signup(client, "same@example.com").status_code for _ in range(4)]
    assert codes[-1] == 429


# ---- export for the email service provider ------------------------------------------------


def _mixed_audience(app, client):
    _signup(client, "collected@example.com")
    limiter.reset()
    _signup(client, "gone@example.com")
    limiter.reset()
    _signup(client, "bounced@example.com")
    now = datetime.now(UTC)
    with app.app_context():
        db.session.add_all(
            [
                Subscriber(
                    public_id="v1",
                    email="verified@example.com",
                    status="subscribed",
                    consent_at=now - timedelta(days=9),
                    consent_text="Yes, email me The Positive Reset every day.",
                    consent_version="2026-11",
                    confirmation_sent_at=now - timedelta(days=9),
                    confirmed_at=now - timedelta(days=8),
                    preferences=["weekly"],
                    interests=[],
                ),
                Subscriber(
                    public_id="q1",
                    email="imported@example.com",
                    status="quarantined",
                    preferences=["weekly"],
                    interests=[],
                ),
            ]
        )
        gone = db.session.scalar(
            db.select(Subscriber).where(Subscriber.email == "gone@example.com")
        )
        gone.status = "unsubscribed"
        db.session.add(
            EmailSuppression(email_hash=tokens.email_hash("bounced@example.com"), reason="bounced")
        )
        db.session.commit()


def test_provider_export_labels_verification_and_leaves_out_unsubscribed_and_suppressed(
    collecting, client, as_role
):
    _mixed_audience(collecting, client)
    manager = as_role("newsletter_manager")
    rows = {r["email"]: r for r in _rows(manager.get(EXPORT))}
    assert set(rows) == {"collected@example.com", "verified@example.com"}
    collected, verified = rows["collected@example.com"], rows["verified@example.com"]
    # Collected website sign-ups: consent evidence, never described as confirmed.
    assert collected["status"] == "collected" and collected["email_verified"] == "no"
    assert collected["verification"] == "website_signup_no_confirmation_email_sent"
    assert collected["marketing_permission"].startswith("consent_given_email_not_verified")
    assert collected["consent_given"] == "yes" and collected["consent_at"]
    assert collected["consent_version"] == "2026-11-collection"
    assert "email service provider" in collected["consent_text"]
    assert collected["consent_source"] == "article"
    assert collected["consent_page"] == "/articles/a-story"
    assert collected["consent_ip_hash_recorded"] == "yes"
    assert collected["confirmed_at"] == "" and collected["confirmation_sent_at"] == ""
    # Double opt-in subscribers are the only verified ones.
    assert verified["email_verified"] == "yes"
    assert verified["verification"] == "double_opt_in_confirmed"
    assert verified["marketing_permission"] == "confirmed_opt_in"
    # Verified only, on request.
    only = _rows(manager.get(f"{EXPORT}?verified_only=1"))
    assert [r["email"] for r in only] == ["verified@example.com"]


def test_provider_export_is_restricted_and_audited(collecting, client, as_role):
    _signup(client)
    assert client.get(EXPORT).status_code == 401
    for role in ("administrator", "marketing_manager", "editor"):
        assert as_role(role).get(EXPORT).status_code == 403
    res = as_role("newsletter_manager").get(EXPORT)
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert "attachment" in res.headers["Content-Disposition"]
    assert res.headers["Cache-Control"] == "no-store"
    with collecting.app_context():
        log = db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "subscribers.exported_for_provider")
        )
        assert log is not None and log.details["count"] == 1
        assert log.details["verified_only"] is False


def test_export_neutralises_spreadsheet_formulas(collecting, client, as_role):
    _signup(client, first_name="=HYPERLINK(1)")
    [row] = _rows(as_role("newsletter_manager").get(EXPORT))
    assert row["first_name"].startswith("'")


# ---- future SMTP delivery -----------------------------------------------------------------


def test_switching_to_double_opt_in_later_asks_collected_contacts_to_confirm(seeded, client):
    """Collected contacts can be moved to double opt-in once delivery is set up: a new
    sign-up (or staff resending) emails a confirmation link and only the click verifies."""
    _set(seeded, **{"newsletter.is_open": True, "email.signup_mode": "collection_only"})
    assert _signup(client).status_code == 202
    assert _subscriber(seeded).status == "collected"
    # Delivery configured (testing: memory backend), back to double opt-in.
    _set(seeded, **{"email.sending_mode": "live", "email.signup_mode": "double_opt_in"})
    limiter.reset()
    res = client.post(
        SUB,
        json={
            "email": "reader@example.com",
            "consent": True,
            "age_confirmed": True,
            "consent_version": "2026-11",
        },
    )
    assert res.status_code == 202 and res.get_json()["data"]["status"] == "check_email"
    sub = _subscriber(seeded)
    assert sub.status == "pending" and sub.consent_version == "2026-11" and not sub.confirmed_at
    _work(seeded)
    token = _link_token("reader@example.com", "/newsletter/confirm")
    assert client.post("/api/v1/newsletter/confirm", json={"token": token}).status_code == 200
    sub = _subscriber(seeded)
    assert sub.status == "subscribed" and sub.confirmed_at and sub.is_marketable


def test_staff_can_ask_a_collected_contact_to_confirm_once_delivery_works(seeded, client, as_role):
    _set(seeded, **{"newsletter.is_open": True, "email.signup_mode": "collection_only"})
    _signup(client)
    sub_id = _subscriber(seeded).id
    manager = as_role("newsletter_manager")
    action = f"/api/v1/admin/subscribers/{sub_id}/resend-confirmation"
    assert manager.post(action, {}).status_code == 409  # sending disabled: nothing to send
    _set(seeded, **{"email.sending_mode": "live"})
    assert manager.post(action, {}).status_code == 200
    sub = _subscriber(seeded)
    assert sub.status == "pending" and sub.confirmation_sent_at and not sub.confirmed_at


def test_admin_tells_collected_signups_apart_from_verified_subscribers(collecting, client, as_role):
    _signup(client)
    manager = as_role("newsletter_manager")
    listing = manager.get("/api/v1/admin/subscribers").get_json()
    [row] = listing["data"]
    assert row["status"] == "collected" and row["verified"] is False
    assert row["marketable"] is False
    assert row["verification"] == "website_signup_no_confirmation_email_sent"
    assert listing["meta"]["status_counts"] == {"collected": 1}
    detail = manager.get(f"/api/v1/admin/subscribers/{row['id']}").get_json()["data"]
    assert detail["consent"]["confirmation_sent_at"] is None
    assert detail["consent"]["confirmed_at"] is None
    assert detail["consent"]["version"] == "2026-11-collection"
    filtered = manager.get("/api/v1/admin/subscribers?status=collected").get_json()
    assert filtered["meta"]["total"] == 1
