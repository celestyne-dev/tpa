"""Batch 07: partner CRM, inquiries, inventory and bookings, sponsored content, affiliates,
the media kit, reporting and permissions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.extensions import db, limiter
from app.models import AffiliateClickDaily, AuditLog, PartnershipInquiry
from app.services.mail import MemoryBackend

from .test_admin_content import _draft

ADMIN = "/api/v1/admin"


class _Loader:
    settings: dict = {}


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _partner(api, **extra):
    res = api.post(
        f"{ADMIN}/partners", {"name": "Calm Co", "website": "https://calm.example.com", **extra}
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


INQUIRY = {
    "organization": "Bright Org",
    "contact_name": "Sam Lee",
    "email": "sam@bright.example.com",
    "website": "https://bright.example.com",
    "collaboration_type": "sponsorship",
    "budget_range": "1000_5000",
    "objectives": "Reach readers interested in wellbeing.",
    "message": "We'd like to sponsor a series.",
    "privacy_consent": True,
    "elapsed_ms": 5000,
}


# ---- CRM and RBAC -----------------------------------------------------------------------


def test_partner_crud_and_rbac(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    partner = _partner(
        pm,
        contacts=[{"name": "Ann", "email": "ann@calm.example.com", "role": "Marketing"}],
        internal_notes="Negotiating 10% discount",
    )
    assert partner["contacts"][0]["email"] == "ann@calm.example.com"
    updated = pm.put(f"{ADMIN}/partners/{partner['id']}", {"status": "active"}).get_json()["data"]
    assert updated["status"] == "active"
    assert (
        pm.post(f"{ADMIN}/partners", {"name": "X", "website": "javascript:alert(1)"}).status_code
        == 400
    )

    writer = as_role("content_writer", email="writer@example.org")
    for url in (
        "/partners",
        "/partnership-inquiries",
        "/sponsorship-campaigns",
        "/ad-bookings",
        "/affiliate-links",
        "/partnership-finance",
        "/partnership-reports",
        "/media-kit",
    ):
        assert writer.get(f"{ADMIN}{url}").status_code == 403, url
    marketing = as_role("marketing_manager", email="mkt@example.org")
    assert marketing.get(f"{ADMIN}/partners").status_code == 403  # no CRM / contacts
    assert marketing.get(f"{ADMIN}/sponsorship-campaigns").status_code == 200
    assert pm.get(f"{ADMIN}/partnership-finance").status_code == 403
    with seeded.app_context():
        actions = {a.action for a in db.session.scalars(db.select(AuditLog))}
        assert {"partner.created", "partner.updated"} <= actions
        notes = [
            a.details
            for a in db.session.scalars(db.select(AuditLog))
            if a.action == "partner.created"
        ]
        assert "Negotiating" not in str(notes)  # notes are never copied into the audit log


def test_opportunity_stage_moves_are_validated(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    partner = _partner(pm)
    res = pm.post(
        f"{ADMIN}/opportunities",
        {
            "partner_id": partner["id"],
            "title": "Spring series",
            "expected_value_minor": 250000,
            "currency": "USD",
        },
    )
    assert res.status_code == 201, res.get_json()
    opp = res.get_json()["data"]
    assert opp["stage"] == "new_inquiry"
    assert (
        pm.post(f"{ADMIN}/opportunities/{opp['id']}/stage", {"stage": "contracted"}).status_code
        == 409
    )
    assert (
        pm.post(f"{ADMIN}/opportunities/{opp['id']}/stage", {"stage": "qualification"}).status_code
        == 200
    )
    assert pm.post(f"{ADMIN}/opportunities/{opp['id']}/stage", {"stage": "lost"}).status_code == 400
    res = pm.post(
        f"{ADMIN}/opportunities/{opp['id']}/interactions",
        {"kind": "call", "summary": "Intro call", "follow_up_on": "2026-11-02"},
    )
    assert res.status_code == 201, res.get_json()
    detail = pm.get(f"{ADMIN}/opportunities/{opp['id']}").get_json()["data"]
    assert len(detail["history"]) >= 2


# ---- public inquiry form ------------------------------------------------------------------


def test_inquiry_is_stored_before_success_and_rate_limited(seeded, client):
    limiter.reset()
    MemoryBackend.outbox.clear()
    res = client.post("/api/v1/partnership-inquiries", json=INQUIRY)
    assert res.status_code == 201 and res.get_json()["data"]["status"] == "received"
    assert res.headers["Cache-Control"] == "no-store"
    with seeded.app_context():
        stored = db.session.scalars(db.select(PartnershipInquiry)).all()
        assert len(stored) == 1 and stored[0].ip_hash != "127.0.0.1"
        # No notification address configured: recorded honestly, nothing sent.
        assert stored[0].notification_status == "no_recipient"
    assert not MemoryBackend.outbox

    # Spam: honeypot or instant submission is not stored and never told "received".
    bot = client.post("/api/v1/partnership-inquiries", json={**INQUIRY, "company_fax": "1"})
    assert bot.status_code == 202 and bot.get_json()["data"]["status"] != "received"
    fast = client.post("/api/v1/partnership-inquiries", json={**INQUIRY, "elapsed_ms": 200})
    assert fast.get_json()["data"]["status"] != "received"
    limiter.reset()  # the per-address limit (3/hour) is exercised below
    no_consent = client.post(
        "/api/v1/partnership-inquiries", json={**INQUIRY, "privacy_consent": False}
    )
    assert no_consent.status_code == 400
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(PartnershipInquiry.id))) == 1

    limiter.reset()
    codes = [
        client.post(
            "/api/v1/partnership-inquiries", json={**INQUIRY, "email": "same@bright.example.com"}
        ).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [201, 201, 201] and codes[3] == 429


def test_inquiry_notifies_team_when_mail_is_configured(seeded, client):
    seeded.config.update(PARTNERSHIP_NOTIFY_EMAIL="team@example.org", MAIL_BACKEND="memory")
    MemoryBackend.outbox.clear()
    assert client.post("/api/v1/partnership-inquiries", json=INQUIRY).status_code == 201
    assert [m.to for m in MemoryBackend.outbox] == ["team@example.org"]
    assert "sam@bright.example.com" not in MemoryBackend.outbox[0].text  # contacts stay in admin


# ---- campaigns ----------------------------------------------------------------------------


def test_campaign_transitions_need_approval_rights_dates_and_disclosure(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    eic = as_role("editor_in_chief", email="eic@example.org")
    partner = _partner(pm)
    campaign = pm.post(
        f"{ADMIN}/sponsorship-campaigns", {"partner_id": partner["id"], "name": "Autumn"}
    ).get_json()["data"]
    cid = campaign["id"]
    status = f"{ADMIN}/sponsorship-campaigns/{cid}/status"
    assert pm.post(status, {"status": "active"}).status_code == 409
    assert pm.post(status, {"status": "internal_review"}).status_code == 200
    assert pm.post(status, {"status": "approved"}).status_code == 403  # no approve right
    res = eic.post(status, {"status": "approved"})
    assert res.status_code == 400 and "dates" in str(res.get_json())
    today = date.today()
    pm.put(
        f"{ADMIN}/sponsorship-campaigns/{cid}",
        {
            "starts_on": (today + timedelta(days=5)).isoformat(),
            "ends_on": (today + timedelta(days=30)).isoformat(),
            "disclosure_text": "Sponsored by Calm Co.",
            "contracted_fee_minor": 150000,
            "currency": "KES",
        },
    )
    assert eic.post(status, {"status": "approved"}).status_code == 200
    assert pm.post(status, {"status": "active"}).status_code == 400  # not within its dates
    assert pm.post(status, {"status": "scheduled"}).status_code == 200
    # Editing a scheduled/approved campaign's terms withdraws approval.
    edited = pm.put(f"{ADMIN}/sponsorship-campaigns/{cid}", {"contracted_fee_minor": 1}).get_json()
    assert edited["data"]["status"] == "draft"
    assert (
        pm.post(
            f"{ADMIN}/sponsorship-campaigns",
            {"partner_id": partner["id"], "name": "Bad", "contracted_fee_minor": -5},
        ).status_code
        == 400
    )


# ---- inventory and bookings ---------------------------------------------------------------


def _placement(api, **extra):
    res = api.post(
        f"{ADMIN}/ad-placements",
        {
            "name": "Homepage sponsor",
            "key": "home-sponsor",
            "placement_type": "homepage_sponsor",
            "exclusive": True,
            **extra,
        },
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _booking(api, placement, partner, starts, ends, **extra):
    return api.post(
        f"{ADMIN}/ad-bookings",
        {
            "placement_id": placement["id"],
            "partner_id": partner["id"],
            "starts_at": _iso(starts),
            "ends_at": _iso(ends),
            "headline": "Breathe better",
            "link_url": "https://calm.example.com/offer",
            "agreed_fee_minor": 50000,
            "currency": "USD",
            **extra,
        },
    )


def test_cpm_requires_measured_impressions(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    res = pm.post(
        f"{ADMIN}/ad-placements",
        {"name": "S", "key": "side", "placement_type": "sidebar", "pricing_model": "cpm"},
    )
    assert res.status_code == 400


def test_exclusive_bookings_cannot_overlap_and_pending_ones_warn(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    placement, partner = _placement(pm), _partner(pm)
    now = datetime.now(UTC)
    first = _booking(pm, placement, partner, now + timedelta(days=1), now + timedelta(days=10))
    assert first.status_code == 201, first.get_json()
    b1 = first.get_json()["data"]
    second = _booking(pm, placement, partner, now + timedelta(days=5), now + timedelta(days=12))
    assert second.status_code == 201  # pending overlap: allowed with a warning
    assert second.get_json()["meta"]["conflicts"]["warnings"]
    b2 = second.get_json()["data"]
    assert (
        pm.post(f"{ADMIN}/ad-bookings/{b1['id']}/status", {"status": "approved"}).status_code == 200
    )
    # Approving the overlapping one is refused, and so is a new overlapping booking.
    assert (
        pm.post(f"{ADMIN}/ad-bookings/{b2['id']}/status", {"status": "approved"}).status_code == 409
    )
    clash = _booking(pm, placement, partner, now + timedelta(days=2), now + timedelta(days=3))
    assert clash.status_code == 409
    after = _booking(pm, placement, partner, now + timedelta(days=10), now + timedelta(days=11))
    assert after.status_code == 201  # touching end/start is not an overlap
    check = pm.post(
        f"{ADMIN}/ad-bookings/conflicts",
        {
            "placement_id": placement["id"],
            "starts_at": _iso(now + timedelta(days=3)),
            "ends_at": _iso(now + timedelta(days=4)),
        },
    )
    assert check.get_json()["data"]["blocking"]
    bad = _booking(pm, placement, partner, now + timedelta(days=20), now + timedelta(days=19))
    assert bad.status_code == 400
    unsafe = _booking(
        pm,
        placement,
        partner,
        now + timedelta(days=30),
        now + timedelta(days=31),
        link_url="javascript:alert(1)",
    )
    assert unsafe.status_code == 400


def test_only_approved_live_bookings_render_with_sponsored_links(seeded, as_role):
    from app.services.partnerships.advertising import live_creatives

    pm = as_role("partnerships_manager", email="pm@example.org")
    placement, partner = _placement(pm), _partner(pm)
    now = datetime.now(UTC)
    live = _booking(
        pm, placement, partner, now - timedelta(hours=1), now + timedelta(days=2)
    ).get_json()["data"]
    with seeded.app_context():
        assert live_creatives("home_sponsor") == []  # pending is never shown
    approved = pm.post(f"{ADMIN}/ad-bookings/{live['id']}/status", {"status": "approved"})
    assert approved.status_code == 200, approved.get_json()
    with seeded.app_context():
        shown = live_creatives("home_sponsor")
        assert len(shown) == 1 and shown[0]["link"]["sponsored"] is True
        assert shown[0]["label"] == "Sponsored" and shown[0]["sponsor"] == "Calm Co"
        assert live_creatives("home_sponsor", now=now + timedelta(days=3)) == []  # expired
    pm.post(f"{ADMIN}/ad-bookings/{live['id']}/status", {"status": "paused"})
    with seeded.app_context():
        assert live_creatives("home_sponsor") == []
    pm.post(f"{ADMIN}/ad-bookings/{live['id']}/status", {"status": "approved"})
    # Material edits to an approved booking need re-approval.
    edited = pm.put(f"{ADMIN}/ad-bookings/{live['id']}", {"headline": "New copy"}).get_json()[
        "data"
    ]
    assert edited["status"] == "pending"
    detail = pm.get(f"{ADMIN}/ad-bookings/{live['id']}").get_json()["data"]
    assert detail["history"][0]["to"] == "pending"


def test_paid_sections_render_only_live_creatives_on_pages(seeded, as_role, client):
    pm = as_role("partnerships_manager", email="pm@example.org")
    placement, partner = _placement(pm), _partner(pm)
    now = datetime.now(UTC)
    booking = _booking(
        pm, placement, partner, now - timedelta(hours=1), now + timedelta(days=2)
    ).get_json()["data"]
    pm.post(f"{ADMIN}/ad-bookings/{booking['id']}/status", {"status": "approved"})
    with seeded.app_context():
        from app.services.page_render import _computed

        data: dict = {}
        _computed(_Loader(), "sponsored_banner", {"placement": "home_sponsor"}, data, {})
        assert data["creatives"][0]["link"]["href"] == "https://calm.example.com/offer"
        empty: dict = {}
        _computed(_Loader(), "sponsored_banner", {"placement": "missing"}, empty, {})
        assert empty["creatives"] == []


# ---- sponsored articles -------------------------------------------------------------------


def test_sponsored_article_needs_disclosure_and_approval_before_publishing(seeded, as_role, client):
    admin = as_role("super_admin", email="owner@example.org")
    pm = as_role("partnerships_manager", email="pm@example.org")
    eic = as_role("editor_in_chief", email="eic@example.org")
    article = _draft(admin, seeded)
    aid = article["id"]
    url = f"{ADMIN}/articles/{aid}/sponsorship"
    res = admin.put(url, {"sponsor_name": "Calm Co", "label": "Featured", "disclosure_text": "x"})
    assert res.status_code == 400  # label must say sponsored/paid
    res = admin.put(
        url,
        {
            "sponsor_name": "Calm Co",
            "disclosure_text": "",
            "sponsored_links": ["https://calm.example.com/offer"],
        },
    )
    assert res.status_code == 200, res.get_json()
    assert admin.put(url, {"review_status": "approved"}).status_code == 400  # only via approve
    assert admin.put(url, {"sponsored_links": ["data:text/html,hi"]}).status_code == 400
    blocked = admin.post(f"{ADMIN}/articles/{aid}/publish")
    assert blocked.status_code == 400 and "sponsorship" in blocked.get_json()["error"]["details"]
    assert eic.post(f"{url}/approve").status_code == 400  # disclosure missing
    admin.put(url, {"disclosure_text": "This article is sponsored by Calm Co."})
    assert pm.post(f"{url}/approve").status_code == 403
    assert eic.post(f"{url}/approve").status_code == 200
    assert admin.post(f"{ADMIN}/articles/{aid}/publish").status_code == 200
    public = client.get(f"/api/v1/articles/{article['slug']}").get_json()["data"]["article"]
    assert public["sponsorship"] == {
        "label": "Sponsored Content",
        "sponsor": "Calm Co",
        "disclosure": "This article is sponsored by Calm Co.",
        "links": ["https://calm.example.com/offer"],
    }
    listed = client.get("/api/v1/articles").get_json()["data"]
    assert next(a for a in listed if a["id"] == str(aid))["sponsorship"]["sponsor"] == "Calm Co"
    # Published sponsored content keeps its disclosure.
    assert admin.delete(url).status_code == 409
    # Organic articles carry no sponsorship marker.
    other = next(a for a in listed if a["id"] != str(aid))
    assert other["sponsorship"] is None


def test_scheduled_publication_is_blocked_without_sponsor_approval(seeded, as_role):
    from app.models import Article
    from app.services.publication_service import publish_due_scheduled

    admin = as_role("super_admin", email="owner@example.org")
    eic = as_role("editor_in_chief", email="eic@example.org")
    article = _draft(admin, seeded)
    aid = article["id"]
    url = f"{ADMIN}/articles/{aid}/sponsorship"
    admin.put(url, {"sponsor_name": "Calm Co", "disclosure_text": "Sponsored by Calm Co."})
    eic.post(f"{url}/approve")
    when = _iso(datetime.now(UTC) + timedelta(hours=1))
    assert admin.post(f"{ADMIN}/articles/{aid}/publish", {"published_at": when}).status_code == 200
    # A material edit withdraws approval and takes the article off the schedule.
    admin.put(url, {"disclosure_text": "Paid partnership with Calm Co."})
    with seeded.app_context():
        stored = db.session.get(Article, aid)
        assert stored.status == "draft" and stored.sponsorship.review_status == "internal_review"
        stored.status, stored.published_at = "scheduled", datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()
        publish_due_scheduled()
        db.session.commit()
        assert db.session.get(Article, aid).status == "scheduled"  # still not published


# ---- newsletter sponsorship ---------------------------------------------------------------


def test_sponsored_newsletter_shows_disclosure_and_needs_approval_right(seeded, as_role):
    admin = as_role("super_admin", email="owner@example.org")
    news = as_role("newsletter_manager", email="news@example.org")
    res = admin.post(
        f"{ADMIN}/newsletters",
        {
            "template_key": "weekly_edition",
            "name": "Sponsored edition",
            "sponsorship": {
                "sponsor_name": "Calm Co",
                "disclosure_text": "This edition is sponsored by Calm Co.",
            },
        },
    )
    assert res.status_code == 201, res.get_json()
    cid = res.get_json()["data"]["id"]
    preview = admin.post(f"{ADMIN}/newsletters/{cid}/preview").get_json()["data"]
    assert "This edition is sponsored by Calm Co." in preview["html"]
    assert "This edition is sponsored by Calm Co." in preview["text"]
    assert news.patch(f"{ADMIN}/newsletters/{cid}", {"sponsorship": None}).status_code == 403
    bad = admin.post(
        f"{ADMIN}/newsletters",
        {"template_key": "weekly_edition", "name": "x", "sponsorship": {"sponsor_name": "Calm Co"}},
    )
    assert bad.status_code == 400


# ---- affiliates ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "http://merchant.example.com/p",
        "https://user:pw@merchant.example.com/",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.0.0.5/x",
        "//merchant.example.com/x",
        "/admin/users",
        "https://localhost:5173/admin",
    ],
)
def test_affiliate_link_rejects_unsafe_destinations(seeded, as_role, target):
    aff = as_role("affiliate_manager", email="aff@example.org")
    res = aff.post(f"{ADMIN}/affiliate-links", {"name": "Journal", "target_url": target})
    assert res.status_code == 400, target


def test_affiliate_redirect_counts_aggregates_and_never_opens_redirects(seeded, as_role, client):
    aff = as_role("affiliate_manager", email="aff@example.org")
    program = aff.post(
        f"{ADMIN}/affiliate-programs",
        {"name": "Books", "merchant": "Bookshop", "account_identifier": "SECRET-123"},
    ).get_json()["data"]
    assert program["account_identifier"] == "SECRET-123"
    mkt = as_role("marketing_manager", email="mkt@example.org")
    hidden = mkt.get(f"{ADMIN}/affiliate-programs").get_json()["data"][0]
    assert hidden["account_identifier"] is None and hidden["notes"] is None
    link = aff.post(
        f"{ADMIN}/affiliate-links",
        {
            "name": "Calm journal",
            "slug": "calm-journal",
            "program_id": program["id"],
            "target_url": "https://shop.example.com/journal?ref=1",
            "utm_source": "tpa",
            "utm_campaign": "autumn",
        },
    ).get_json()["data"]
    assert (
        aff.post(
            f"{ADMIN}/affiliate-links",
            {"name": "x", "target_url": "https://a.example.com", "utm_source": "<script>"},
        ).status_code
        == 400
    )
    res = client.get("/api/v1/go/calm-journal?from=/articles/calm&next=https://evil.example.com")
    assert res.status_code == 302
    assert res.headers["Location"].startswith("https://shop.example.com/journal?ref=1")
    assert "utm_source=tpa" in res.headers["Location"] and "evil" not in res.headers["Location"]
    assert res.headers["Cache-Control"] == "no-store"
    client.get("/api/v1/go/calm-journal?from=/articles/calm")
    client.get("/api/v1/go/calm-journal?from=javascript:alert(1)")
    assert client.get("/api/v1/go/unknown").status_code == 404
    with seeded.app_context():
        rows = {r.source_path: r.clicks for r in db.session.scalars(db.select(AffiliateClickDaily))}
        assert rows == {"/articles/calm": 2, "": 1}
    report = aff.get(f"{ADMIN}/affiliate-clicks").get_json()["data"]
    assert sum(r["clicks"] for r in report) == 3
    assert all("earn" not in str(r).lower() and "revenue" not in str(r).lower() for r in report)
    aff.put(f"{ADMIN}/affiliate-links/{link['id']}", {"is_active": False})
    assert client.get("/api/v1/go/calm-journal").status_code == 404
    aff.put(
        f"{ADMIN}/affiliate-links/{link['id']}",
        {"is_active": True, "expires_at": _iso(datetime.now(UTC) - timedelta(days=1))},
    )
    assert client.get("/api/v1/go/calm-journal").status_code == 404


def test_affiliate_disclosure_is_enforced_and_rendered_with_recommendations(seeded, as_role):
    aff = as_role("affiliate_manager", email="aff@example.org")
    assert aff.put(f"{ADMIN}/affiliate-disclosure", {"text": "Thanks!"}).status_code == 400
    text = (
        "Some links on this page are affiliate links. We may earn a commission at no extra "
        "cost to you."
    )
    assert aff.put(f"{ADMIN}/affiliate-disclosure", {"text": text}).status_code == 200
    link = aff.post(
        f"{ADMIN}/affiliate-links", {"name": "Journal", "target_url": "https://shop.example.com/j"}
    ).get_json()["data"]
    with seeded.app_context():
        from app.cms.sections import check_section
        from app.services.page_render import _computed

        content = {
            "heading": "Picks",
            "links": [link["id"]],
            "items": [{"note": "We use it daily"}],
        }
        _, errors, _ = check_section("affiliate_recommendations", "cards", content)
        assert not errors
        data = {**content}
        _computed(_Loader(), "affiliate_recommendations", content, data, {})
        assert data["disclosure"] == text
        assert data["links"][0]["href"] == f"/api/v1/go/{link['slug']}"
        assert (
            data["links"][0]["sponsored"] is True and data["links"][0]["note"] == "We use it daily"
        )
        _, errors, _ = check_section("affiliate_recommendations", "cards", {"links": []})
        assert any("links" in k for k in errors)


def test_commission_import_detects_duplicates_and_validates(seeded, as_role):
    fin = as_role("finance_manager", email="fin@example.org")
    aff = as_role("affiliate_manager", email="aff@example.org")
    program = aff.post(
        f"{ADMIN}/affiliate-programs", {"name": "Books", "merchant": "Bookshop", "currency": "USD"}
    ).get_json()["data"]
    csv_text = (
        "reference,date,amount,currency,status\n"
        "A-1,2026-10-01,12.50,USD,reported\n"
        "A-2,2026-10-02,3.00,USD,paid\n"
        "A-1,2026-10-01,12.50,USD,reported\n"
        "A-3,not-a-date,1.00,USD,reported\n"
        "A-4,2026-10-03,-1,USD,reported\n"
    ).encode("ascii")
    res = fin.upload(
        f"{ADMIN}/affiliate-commissions/import",
        csv_text,
        filename="c.csv",
        program_id=str(program["id"]),
    )
    assert res.status_code == 200, res.get_json()
    result = res.get_json()["data"]
    assert result["imported"] == 2 and result["duplicates"] == 1 and len(result["errors"]) == 2
    again = fin.upload(
        f"{ADMIN}/affiliate-commissions/import",
        csv_text,
        filename="c.csv",
        program_id=str(program["id"]),
    ).get_json()["data"]
    assert again["imported"] == 0 and again["duplicates"] >= 2
    rows = fin.get(f"{ADMIN}/affiliate-commissions").get_json()["data"]
    assert {r["amount_minor"] for r in rows} == {1250, 300} and {r["source"] for r in rows} == {
        "import"
    }
    manual = fin.post(
        f"{ADMIN}/affiliate-commissions",
        {
            "program_id": program["id"],
            "external_reference": "M-1",
            "occurred_on": "2026-10-05",
            "amount_minor": 500,
            "currency": "USD",
        },
    )
    assert manual.status_code == 400  # manual entries must explain their evidence


# ---- media kit and audience metrics -------------------------------------------------------


def test_media_kit_shows_only_verified_dated_measurements(seeded, as_role, client):
    pm = as_role("partnerships_manager", email="pm@example.org")
    assert client.get("/api/v1/media-kit").status_code == 404  # nothing invented before publishing
    future = (date.today() + timedelta(days=2)).isoformat()
    bad = pm.post(
        f"{ADMIN}/audience-metrics",
        {
            "metric_type": "social_followers",
            "value": 1000,
            "platform": "LinkedIn",
            "source": "LinkedIn page analytics",
            "measured_on": future,
        },
    )
    assert bad.status_code == 400
    unsourced = pm.post(
        f"{ADMIN}/audience-metrics",
        {
            "metric_type": "social_followers",
            "value": 1000,
            "platform": "LinkedIn",
            "measured_on": "2026-10-01",
        },
    )
    assert unsourced.status_code == 400
    assert (
        pm.post(
            f"{ADMIN}/audience-metrics",
            {
                "metric_type": "social_followers",
                "value": 1000,
                "platform": "LinkedIn",
                "source": "LinkedIn page analytics",
                "measured_on": "2026-10-01",
                "is_public": True,
            },
        ).status_code
        == 400
    )  # unverified
    ok = pm.post(
        f"{ADMIN}/audience-metrics",
        {
            "metric_type": "social_followers",
            "value": 1200,
            "platform": "LinkedIn",
            "source": "LinkedIn page analytics",
            "measured_on": "2026-10-01",
            "verified": True,
            "is_public": True,
        },
    )
    assert ok.status_code == 201
    pm.post(
        f"{ADMIN}/audience-metrics",
        {
            "metric_type": "website_users",
            "value": 999,
            "platform": "Website",
            "source": "Self-hosted analytics",
            "measured_on": "2026-10-01",
        },
    )
    assert (
        pm.put(
            f"{ADMIN}/media-kit",
            {
                "about": "Practical positivity.",
                "show_rate_card": True,
                "contact_cta": {"label": "Talk to us", "href": "/admin"},
            },
        ).status_code
        == 400
    )
    assert (
        pm.put(
            f"{ADMIN}/media-kit",
            {
                "about": "Practical positivity.",
                "show_rate_card": True,
                "contact_cta": {"label": "Talk to us", "href": "/partner-with-us"},
            },
        ).status_code
        == 200
    )
    assert client.get("/api/v1/media-kit").status_code == 404  # draft only
    assert pm.post(f"{ADMIN}/media-kit/publish").status_code == 200
    public = client.get("/api/v1/media-kit").get_json()["data"]
    assert public["about"] == "Practical positivity."
    assert [m["label"] for m in public["metrics"]] == ["Social media followers"]
    assert public["metrics"][0]["measured_on"] == "2026-10-01"
    assert public["metrics"][0]["source"] == "LinkedIn page analytics"
    assert "internal" not in str(public).lower()


# ---- reporting and currency ---------------------------------------------------------------


def test_reports_keep_categories_and_currencies_distinct(seeded, as_role):
    pm = as_role("partnerships_manager", email="pm@example.org")
    eic = as_role("editor_in_chief", email="eic@example.org")
    fin = as_role("finance_manager", email="fin@example.org")
    partner = _partner(pm)
    pm.post(
        f"{ADMIN}/opportunities",
        {
            "partner_id": partner["id"],
            "title": "Pipeline",
            "expected_value_minor": 900000,
            "currency": "USD",
        },
    )
    today = date.today()
    cid = pm.post(
        f"{ADMIN}/sponsorship-campaigns",
        {
            "partner_id": partner["id"],
            "name": "Contracted",
            "starts_on": (today + timedelta(days=3)).isoformat(),
            "ends_on": (today + timedelta(days=20)).isoformat(),
            "disclosure_text": "Sponsored by Calm Co.",
            "contracted_fee_minor": 5000000,
            "currency": "KES",
        },
    ).get_json()["data"]["id"]
    pm.post(f"{ADMIN}/sponsorship-campaigns/{cid}/status", {"status": "internal_review"})
    eic.post(f"{ADMIN}/sponsorship-campaigns/{cid}/status", {"status": "approved"})
    for kind, amount, verified in (
        ("invoiced", 5000000, False),
        ("received", 2000000, True),
        ("received", 1000000, False),
    ):
        res = fin.post(
            f"{ADMIN}/partnership-finance",
            {
                "kind": kind,
                "partner_id": partner["id"],
                "campaign_id": cid,
                "amount_minor": amount,
                "currency": "KES",
                "entry_date": today.isoformat(),
                "verified": verified,
            },
        )
        assert res.status_code == 201, res.get_json()
    assert (
        fin.post(
            f"{ADMIN}/partnership-finance",
            {
                "kind": "received",
                "partner_id": partner["id"],
                "amount_minor": 10,
                "currency": "XYZ",
                "entry_date": today.isoformat(),
            },
        ).status_code
        == 400
    )
    assert pm.post(f"{ADMIN}/partnership-finance", {}).status_code == 403
    report = fin.get(f"{ADMIN}/partnership-reports").get_json()["data"]
    rows = {r["currency"]: r for r in report["by_currency"]}
    assert set(rows) == {"USD", "KES"}
    assert rows["USD"]["pipeline_expected_minor"] == 900000 and rows["USD"]["contracted_minor"] == 0
    kes = rows["KES"]
    assert kes["pipeline_expected_minor"] == 0 and kes["contracted_minor"] == 5000000
    assert kes["invoiced_minor"] == 5000000 and kes["received_verified_minor"] == 2000000
    assert kes["received_unverified_minor"] == 1000000 and kes["outstanding_minor"] == 3000000
    only_usd = fin.get(f"{ADMIN}/partnership-reports?currency=USD").get_json()["data"]
    assert [r["currency"] for r in only_usd["by_currency"]] == ["USD"]
    export = fin.get(f"{ADMIN}/partnership-reports/export")
    assert export.status_code == 200 and export.mimetype == "text/csv"
    assert "pipeline_expected_minor" in export.get_data(as_text=True)
    assert pm.get(f"{ADMIN}/partnership-reports").status_code == 403
    # Money is hidden from roles without commercial rights.
    eic_view = eic.get(f"{ADMIN}/sponsorship-campaigns/{cid}").get_json()["data"]
    assert eic_view["contracted_fee_minor"] is None


# ---- CMS sections -------------------------------------------------------------------------


def test_partnership_sections_validate(seeded):
    with seeded.app_context():
        from app.cms.sections import check_section

        _, errors, _ = check_section(
            "sponsored_banner", "card", {"placement": "missing", "label": "Sponsored"}
        )
        assert any("placement" in k for k in errors)
        _, errors, _ = check_section("partnership_inquiry", "panel", {"heading": "Talk to us"})
        assert not errors
        _, errors, _ = check_section("media_kit_summary", "panel", {"heading": "Advertise"})
        assert not errors
