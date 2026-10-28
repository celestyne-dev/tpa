"""Audience analytics (Batch 11.4) from existing newsletter records only.

Definitions:
- subscribed contacts: subscribers whose status is ``subscribed`` now (double opt-in
  confirmed, not unsubscribed, bounced or complained);
- signups: subscriber records created in the range (including still-pending ones);
- new subscriptions: confirmations (``confirmed_at``) in the range;
- unsubscriptions: ``unsubscribed_at`` in the range;
- growth per period: new subscriptions − unsubscriptions. Past totals can't be rebuilt
  exactly (statuses change in place), so the running total is not reconstructed;
- sources: the recorded signup source (and lead magnet slug for lead-magnet signups);
- campaigns: campaigns completed (sent) in the range, with message outcomes as recorded.
  "Accepted" means the provider took the message; delivered, bounced and complained come
  only from signed provider feedback. Opens and clicks are not tracked (no pixels or link
  rewriting), so they are always reported as unavailable;
- lead magnets: claims created in the range per lead magnet, and confirmed subscribers
  whose recorded source is that lead magnet.

No emails, names or individual activity are returned.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import Campaign, EmailMessage, LeadMagnet, LeadMagnetClaim, Subscriber
from ...utils.errors import NotFoundError
from ..serializers import iso
from . import reports as traffic

SUB = Subscriber


def _bounds(start, end):
    lo = datetime(start.year, start.month, start.day, tzinfo=UTC)
    return lo, datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)


def _day(value: datetime):
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


CAMPAIGN_LIMIT = 50  # campaigns listed (and counted as sent) per range


def _current(statuses: dict[str, int]) -> dict[str, int]:
    return {
        "subscribed": int(statuses.get("subscribed", 0)),
        "pending": int(statuses.get("pending", 0)),
        "unsubscribed": int(statuses.get("unsubscribed", 0)),
        "bounced_or_complained": int(statuses.get("bounced", 0))
        + int(statuses.get("complained", 0)),
        "quarantined": int(statuses.get("quarantined", 0)),
    }


def _statuses() -> dict[str, int]:
    return dict(
        db.session.execute(select(SUB.status, func.count(SUB.id)).group_by(SUB.status)).all()
    )


def audience_summary(ranges: list[dict[str, Any]]) -> dict[str, Any]:
    """Current figures and per-range period counts of ``audience_report`` (same
    definitions), counted in the database instead of loading each record. Used by the
    unified overview."""

    def count(column, lo, hi) -> int:
        return db.session.scalar(select(func.count(SUB.id)).where(column >= lo, column < hi)) or 0

    periods = []
    for args in ranges:
        start, end, _g = traffic.resolve_range(args)
        lo, hi = _bounds(start, end)
        confirmed = count(SUB.confirmed_at, lo, hi)
        unsubscribed = count(SUB.unsubscribed_at, lo, hi)
        sent = (
            db.session.scalar(
                select(func.count(Campaign.id)).where(
                    Campaign.status == "sent",
                    Campaign.completed_at >= lo,
                    Campaign.completed_at < hi,
                )
            )
            or 0
        )
        periods.append(
            {
                "signups": count(SUB.created_at, lo, hi),
                "new_subscriptions": confirmed,
                "unsubscriptions": unsubscribed,
                "net_growth": confirmed - unsubscribed,
                "campaigns_sent": min(sent, CAMPAIGN_LIMIT),
            }
        )
    return {"current": _current(_statuses()), "periods": periods}


def audience_report(args: dict[str, Any]) -> dict[str, Any]:
    start, end, granularity = traffic.resolve_range(args)
    lo, hi = _bounds(start, end)
    campaign_filter = None
    if args.get("campaign"):
        campaign_filter = db.session.scalar(
            select(Campaign).where(Campaign.public_id == str(args["campaign"])[:40])
        )
        if campaign_filter is None:
            raise NotFoundError("Campaign not found.")

    statuses = _statuses()

    def times(column):
        return [
            (_day(t), src, detail)
            for t, src, detail in db.session.execute(
                select(column, SUB.source, SUB.source_detail).where(column >= lo, column < hi)
            )
        ]

    signups = times(SUB.created_at)
    confirmations = times(SUB.confirmed_at)
    unsubscribes = times(SUB.unsubscribed_at)

    buckets: dict[str, dict[str, int]] = {}
    day = start
    while day <= end:
        buckets.setdefault(
            traffic._bucket(day, granularity),
            {"signups": 0, "new_subscriptions": 0, "unsubscriptions": 0},
        )
        day += timedelta(days=1)
    for key, rows in (
        ("signups", signups),
        ("new_subscriptions", confirmations),
        ("unsubscriptions", unsubscribes),
    ):
        for d, _s, _x in rows:
            buckets[traffic._bucket(d, granularity)][key] += 1
    trend = [
        {"period": k, **v, "net_growth": v["new_subscriptions"] - v["unsubscriptions"]}
        for k, v in buckets.items()
    ]

    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for _d, src, _x in confirmations:
        by_source[src][0] += 1
    for src, n in db.session.execute(
        select(SUB.source, func.count(SUB.id))
        .where(SUB.status == "subscribed")
        .group_by(SUB.source)
    ):
        by_source[src][1] += int(n)

    # Campaigns sent in the range (or the selected campaign).
    cstmt = select(Campaign).where(Campaign.status == "sent")
    if campaign_filter is not None:
        cstmt = select(Campaign).where(Campaign.id == campaign_filter.id)
    else:
        cstmt = cstmt.where(Campaign.completed_at >= lo, Campaign.completed_at < hi)
    campaigns = db.session.scalars(
        cstmt.order_by(Campaign.completed_at.desc()).limit(CAMPAIGN_LIMIT)
    ).all()
    counts: dict[int, dict[str, int]] = defaultdict(dict)
    if campaigns:
        for cid, status, n in db.session.execute(
            select(EmailMessage.campaign_id, EmailMessage.status, func.count(EmailMessage.id))
            .where(EmailMessage.campaign_id.in_([c.id for c in campaigns]))
            .group_by(EmailMessage.campaign_id, EmailMessage.status)
        ):
            counts[cid][status] = int(n)
    campaign_rows = []
    any_feedback = False
    for c in campaigns:
        k = counts.get(c.id, {})
        delivered, bounced, complained = (
            k.get("delivered", 0),
            k.get("bounced", 0),
            k.get("complained", 0),
        )
        any_feedback = any_feedback or bool(delivered or bounced or complained)
        campaign_rows.append(
            {
                "id": c.public_id,
                "name": c.name,
                "send_mode": c.send_mode or None,
                "completed_at": iso(c.completed_at),
                "eligible": c.eligible_count,
                "accepted": sum(
                    k.get(s, 0) for s in ("accepted", "delivered", "bounced", "complained")
                ),
                "delivered_confirmed": delivered,
                "bounced": bounced,
                "complained": complained,
                "failed": k.get("failed", 0),
                "suppressed": k.get("suppressed", 0),
                "skipped_test_mode": k.get("skipped", 0),
            }
        )

    claims = db.session.execute(
        select(LeadMagnet.slug, LeadMagnet.title, func.count(LeadMagnetClaim.id))
        .join(LeadMagnet, LeadMagnet.id == LeadMagnetClaim.lead_magnet_id)
        .where(LeadMagnetClaim.created_at >= lo, LeadMagnetClaim.created_at < hi)
        .group_by(LeadMagnet.slug, LeadMagnet.title)
    ).all()
    lm_subscribers = defaultdict(int)
    for _d, src, detail in confirmations:
        if src == "lead_magnet" and detail:
            lm_subscribers[detail] += 1
    titles = {
        slug: title for slug, title in db.session.execute(select(LeadMagnet.slug, LeadMagnet.title))
    }
    lead_slugs = {slug for slug, _t, _n in claims} | set(lm_subscribers)
    claim_counts = {slug: int(n) for slug, _t, n in claims}

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "granularity": granularity},
        "has_data": bool(sum(statuses.values())),
        "current": _current(statuses),
        "period": {
            "signups": len(signups),
            "new_subscriptions": len(confirmations),
            "unsubscriptions": len(unsubscribes),
            "net_growth": len(confirmations) - len(unsubscribes),
            "campaigns_sent": len(campaign_rows) if campaign_filter is None else None,
        },
        "trend": trend,
        "sources": [
            {"source": s, "new_subscriptions": v[0], "subscribed_now": v[1]}
            for s, v in sorted(by_source.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        ],
        "campaign": {"id": campaign_filter.public_id, "name": campaign_filter.name}
        if campaign_filter
        else None,
        "campaign_options": [
            {"id": c.public_id, "name": c.name}
            for c in db.session.scalars(
                select(Campaign)
                .where(Campaign.status == "sent")
                .order_by(Campaign.completed_at.desc())
                .limit(100)
            )
        ],
        "campaigns": campaign_rows,
        "engagement": {
            "delivery_feedback_recorded": any_feedback,
            "opens": None,
            "clicks": None,
            "explanation": "Opens and clicks are not tracked (no tracking pixels or link "
            "redirects). Delivered, bounced and complained counts exist only where the email "
            "provider sent signed feedback; otherwise only 'accepted by the provider' is known.",
        },
        "lead_magnets": [
            {
                "slug": slug,
                "title": titles.get(slug, slug),
                "claims": claim_counts.get(slug, 0),
                "confirmed_subscribers": lm_subscribers.get(slug, 0),
            }
            for slug in sorted(lead_slugs, key=lambda s: (-claim_counts.get(s, 0), s))
        ],
        "definitions": {
            "subscribed": "Contacts whose status is subscribed now (confirmed, not unsubscribed, "
            "bounced or complained).",
            "signups": "Subscriber records created in the range, including unconfirmed ones.",
            "new_subscriptions": "Confirmations (double opt-in) in the range.",
            "unsubscriptions": "Unsubscribes recorded in the range.",
            "growth": "New subscriptions − unsubscriptions. Earlier totals can't be rebuilt "
            "exactly, so no historical running total is shown.",
            "campaigns": "Campaigns finished sending in the range; outcomes as recorded per "
            "message. 'Accepted' isn't proof of delivery.",
            "lead_magnets": "Claims made in the range, and confirmed subscribers whose signup "
            "source is that lead magnet.",
        },
    }
