"""Batch 13.2: statistics retention matches the policies, purchases stay closed while no
payment provider is connected, the legal drafts describe what actually runs, and
newsletter, accounts and purchases are for people aged 18 or older (no birth dates)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.cms.templates import LEGAL_DOCUMENTS
from app.extensions import db
from app.models import AnalyticsDailyPage, AnalyticsRollupDay, Customer, Subscriber

from .conftest import PASSWORD
from .test_commerce_checkout import shop  # noqa: F401  (fixture)
from .test_newsletter_collection import collecting  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
REG = "/api/v1/account/register"
SUB = "/api/v1/newsletter/subscribe"
AGE = "I confirm that I am 18 or older."


# ---- statistics retention ----------------------------------------------------------------


def test_retention_defaults_match_the_policies(app):
    assert app.config["ANALYTICS_RAW_RETENTION_DAYS"] == 90
    assert app.config["ANALYTICS_AGGREGATE_RETENTION_DAYS"] == 365
    for template in ("deploy/env/production.env.example", "deploy/env/staging.env.example"):
        text = (ROOT / template).read_text(encoding="utf-8")
        assert "\nANALYTICS_RAW_RETENTION_DAYS=90\n" in text, template
        assert "\nANALYTICS_AGGREGATE_RETENTION_DAYS=365\n" in text, template
    env = (ROOT / "backend/.env.example").read_text(encoding="utf-8")
    assert "\nANALYTICS_AGGREGATE_RETENTION_DAYS=365\n" in env


def test_cleanup_keeps_12_months_of_totals_and_90_days_of_visits(seeded):
    from app.services.analytics.rollup import maintain

    from .test_analytics import _seed_views

    today = datetime.now(UTC).date()
    days = {
        "visits_kept": today - timedelta(days=89),
        "visits_gone": today - timedelta(days=91),
        "totals_kept": today - timedelta(days=364),
        "totals_gone": today - timedelta(days=366),
    }
    _seed_views(seeded, [(d, "/", "home", "", None, "direct", {}) for d in days.values()])
    from app.models import AnalyticsPageView as V

    with seeded.app_context():
        maintain()
        raw = set(db.session.scalars(db.select(V.day)))
        rolled = set(db.session.scalars(db.select(AnalyticsRollupDay.day)))
        pages = set(db.session.scalars(db.select(AnalyticsDailyPage.day)))
    assert raw == {days["visits_kept"]}
    assert days["totals_kept"] in rolled and days["totals_kept"] in pages
    assert days["visits_gone"] in rolled  # visits deleted only after their day is totalled
    assert days["totals_gone"] not in rolled and days["totals_gone"] not in pages


def test_overview_does_not_compare_with_deleted_statistics(seeded, as_role):
    analyst = as_role("super_admin")
    year = analyst.get("/api/v1/admin/analytics/overview?range=365d").get_json()["data"]
    views = year["sections"]["website"]["page_views"]
    assert views["previous"] is None and views["change"] is None
    month = analyst.get("/api/v1/admin/analytics/overview?range=30d").get_json()["data"]
    assert month["sections"]["website"]["page_views"]["previous"] is not None


def test_deploy_check_flags_retention_longer_than_the_policies(app, monkeypatch):
    from app.services.deploy_check import _privacy

    monkeypatch.setenv("PRIVACY_STATISTICS_MODE", "consent")
    [ok] = _privacy(
        {"PRIVACY_STATISTICS_MODE": "consent", "ANALYTICS_AGGREGATE_RETENTION_DAYS": 365}
    )
    assert ok["level"] == "ok"
    [long] = _privacy(
        {"PRIVACY_STATISTICS_MODE": "consent", "ANALYTICS_AGGREGATE_RETENTION_DAYS": 760}
    )
    assert long["level"] == "warning" and "760" in long["message"]


# ---- purchases while Paystack isn't connected ---------------------------------------------


def test_purchases_are_closed_while_no_payment_provider_is_connected(seeded, client, app):
    assert not app.config["PAYSTACK_SECRET_KEY"]
    site = client.get("/api/v1/site").get_json()["data"]
    assert site["shop"]["purchases_open"] is False
    res = client.post(
        "/api/v1/checkout/guest",
        json={
            "email": "buyer@example.com",
            "items": [{"product_id": "x"}],
            "currency": "USD",
            "expected_total_minor": 100,
            "idempotency_key": "a" * 32,
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    assert res.status_code == 409 and "not open" in res.get_json()["error"]["message"]


def test_purchases_open_by_themselves_once_checkout_is_configured(seeded, client, paystack):
    from .conftest import enable_test_checkout

    enable_test_checkout(seeded)
    assert client.get("/api/v1/site").get_json()["data"]["shop"]["purchases_open"] is True


def test_legal_drafts_describe_payments_as_planned():
    for key in ("cookies", "refunds", "privacy_revised"):
        text = json.dumps(LEGAL_DOCUMENTS[key], ensure_ascii=False)
        assert "Payments are processed by Paystack" not in text, key
        assert "secure payment page of our payment provider, Paystack" not in text, key
        assert "not yet" in text or "not available yet" in text, key
    refunds = json.dumps(LEGAL_DOCUMENTS["refunds"], ensure_ascii=False)
    assert "no payment provider is connected" in refunds
    cookies = json.dumps(LEGAL_DOCUMENTS["cookies"], ensure_ascii=False)
    assert "Payments (planned)" in cookies


# ---- contact details and disclosures -------------------------------------------------------


def test_drafts_reflect_the_real_contact_options():
    drafts = {k: v for k, v in LEGAL_DOCUMENTS.items() if k != "privacy"}  # live policy kept
    for key, doc in drafts.items():
        assert "contact form" not in json.dumps(doc, ensure_ascii=False).lower(), key
    privacy = json.dumps(LEGAL_DOCUMENTS["privacy_revised"], ensure_ascii=False)
    assert "partnership inquiry form" in privacy
    assert "mailto:contact@thinkpositivealways.com" in privacy
    assert "mailto:contact@thinkpositivealways.com" in json.dumps(LEGAL_DOCUMENTS["cookies"])
    for template in ("deploy/env/production.env.example", "deploy/env/staging.env.example"):
        text = (ROOT / template).read_text(encoding="utf-8")
        assert "\nCONTACT_EMAIL=contact@thinkpositivealways.com\n" in text


def test_privacy_draft_explains_what_is_stored():
    text = json.dumps(LEGAL_DOCUMENTS["privacy_revised"], ensure_ascii=False)
    for disclosure in (
        "record of your consent",  # newsletter consent records
        "18 or older",
        "signed-in session",  # customer sessions
        "each order will record",  # orders
        "When you download a resource",  # downloads
        "access and security logs",  # logs
        "Individual visit records up to 90 days; daily totals up to 12 months",
    ):
        assert disclosure in text, disclosure
    assert "date of birth" in text and "Implementation pending" not in text


def test_every_legal_document_is_still_pending_review():
    for key, doc in LEGAL_DOCUMENTS.items():
        assert doc["review_status"] == "pending_review" and doc["effective_date"] == "", key


# ---- 18+ -----------------------------------------------------------------------------------


def _register(client, **extra):
    body = {
        "email": "young@example.com",
        "password": PASSWORD,
        "display_name": "Reader",
        "accept_terms": True,
        **extra,
    }
    return client.post(REG, json=body)


def test_registration_needs_the_age_confirmation(seeded, client):
    for value in (None, False, "true", 1):
        extra = {} if value is None else {"age_confirmed": value}
        res = _register(client, **extra)
        assert res.status_code == 400, value
        assert res.get_json()["error"]["details"]["age_confirmed"] == [
            "Please confirm that you are 18 or older."
        ]
    with seeded.app_context():
        assert (
            db.session.scalar(db.select(Customer).where(Customer.email == "young@example.com"))
            is None
        )
    assert _register(client, age_confirmed=True).status_code == 201


def test_newsletter_signup_needs_the_age_confirmation_and_records_it(seeded, collecting, client):  # noqa: F811
    body = {"email": "reader@example.com", "consent": True, "source": "footer"}
    res = client.post(SUB, json=body)
    assert res.status_code == 400 and "age_confirmed" in res.get_json()["error"]["details"]
    with seeded.app_context():
        assert db.session.scalar(db.select(Subscriber)) is None
    assert client.post(SUB, json={**body, "age_confirmed": True}).status_code == 202
    with seeded.app_context():
        sub = db.session.scalar(db.select(Subscriber))
        assert sub.consent_text.endswith(AGE)
        # Nothing about the person's age beyond the confirmation is stored.
        columns = {c.name for c in Subscriber.__table__.columns}
        assert not {"birth_date", "date_of_birth", "dob", "age"} & columns
        assert not {"birth_date", "date_of_birth", "dob", "age"} & {
            c.name for c in Customer.__table__.columns
        }


def test_checkout_needs_the_age_confirmation(shop):  # noqa: F811
    from .test_commerce_checkout import _key

    shopper = shop["shopper"]
    body = {
        "items": [{"product_id": shop["public_id"]}],
        "currency": "USD",
        "expected_total_minor": 1500,
        "idempotency_key": _key(),
        "accept_terms": True,
    }
    res = shopper.post("/api/v1/checkout", body)
    assert res.status_code == 400 and "age_confirmed" in res.get_json()["error"]["details"]
    ok = shopper.post("/api/v1/checkout", {**body, "age_confirmed": True})
    assert ok.status_code == 201, ok.get_json()


def test_guest_checkout_needs_the_age_confirmation(shop, client):  # noqa: F811
    shop["app"].config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    from .test_commerce_checkout import _key

    body = {
        "email": "buyer@example.com",
        "items": [{"product_id": shop["public_id"]}],
        "currency": "USD",
        "expected_total_minor": 1500,
        "idempotency_key": _key(),
        "accept_terms": True,
    }
    res = client.post("/api/v1/checkout/guest", json=body)
    assert res.status_code == 400 and "age_confirmed" in res.get_json()["error"]["details"]
    assert (
        client.post("/api/v1/checkout/guest", json={**body, "age_confirmed": True}).status_code
        == 201
    )
