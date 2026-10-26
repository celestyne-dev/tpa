"""Advertising inventory, indicative rate cards and bookings.

Availability is real: a booking holds its placement only while it is approved (or
paused) and inside its window. Exclusive placements accept one such booking at a time,
others up to their capacity. Overlaps with pending bookings are reported as warnings.
A placement renders publicly only for approved bookings whose window includes now.
No impressions or reach are estimated anywhere.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select

from ...cms.blocks import safe_href
from ...extensions import db
from ...models import AdPlacement, Booking, MediaAsset, RateCard, SponsorshipCampaign
from ...models.partnerships import CHANNELS, PLACEMENT_TYPES, PRICING_MODELS
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common
from .crm import get_partner

HOLDING = ("approved", "paused")
CREATIVE_FORMATS = ("image", "text", "logo", "html_free_text", "article", "newsletter_block")
BOOKING_FLOW = {
    "pending": {"approved", "cancelled"},
    "approved": {"paused", "stopped"},
    "paused": {"approved", "stopped"},
    "stopped": set(),
    "cancelled": set(),
}


# ---- placements ---------------------------------------------------------------------------


def placement_dict(p: AdPlacement) -> dict[str, Any]:
    return {
        "id": p.id,
        "key": p.key,
        "name": p.name,
        "placement_type": p.placement_type,
        "channel": p.channel,
        "dimensions": p.dimensions,
        "creative_formats": p.creative_formats,
        "exclusive": p.exclusive,
        "capacity": p.capacity,
        "pricing_model": p.pricing_model,
        "default_currency": p.default_currency,
        "impressions_measured": p.impressions_measured,
        "restrictions": p.restrictions,
        "internal_notes": p.internal_notes,
        "is_active": p.is_active,
    }


def list_placements() -> list[dict[str, Any]]:
    return [
        placement_dict(p)
        for p in db.session.scalars(select(AdPlacement).order_by(AdPlacement.name))
    ]


def get_placement(placement_id: int) -> AdPlacement:
    placement = db.session.get(AdPlacement, placement_id)
    if placement is None:
        raise NotFoundError()
    return placement


def save_placement(
    data: dict[str, Any], actor, placement: AdPlacement | None = None
) -> AdPlacement:
    creating = placement is None
    placement = placement or AdPlacement()
    if "name" in data or creating:
        placement.name = common.text(data, "name", 160, required=True)
    if "key" in data or creating:
        key = re.sub(r"[^a-z0-9_]+", "_", str(data.get("key") or placement.name).lower()).strip(
            "_"
        )[:60]
        clash = db.session.scalar(select(AdPlacement).where(AdPlacement.key == key))
        if not key or (clash is not None and clash is not placement):
            raise ValidationError(details={"key": ["Choose a unique placement key."]})
        placement.key = key
    if "placement_type" in data or creating:
        placement.placement_type = common.choice(data, "placement_type", PLACEMENT_TYPES)
    if "channel" in data or creating:
        placement.channel = common.choice(data, "channel", CHANNELS, "website")
    if "dimensions" in data:
        placement.dimensions = common.text(data, "dimensions", 60)
    if "creative_formats" in data:
        formats = data["creative_formats"] or []
        if not isinstance(formats, list) or set(formats) - set(CREATIVE_FORMATS):
            raise ValidationError(
                details={"creative_formats": [f"Use: {', '.join(CREATIVE_FORMATS)}."]}
            )
        placement.creative_formats = list(dict.fromkeys(formats))
    if "exclusive" in data:
        placement.exclusive = data["exclusive"] is True
    if "capacity" in data:
        cap = data["capacity"]
        if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 50:
            raise ValidationError(details={"capacity": ["Use a number from 1 to 50."]})
        placement.capacity = cap
    if placement.exclusive:
        placement.capacity = 1
    if "impressions_measured" in data:
        placement.impressions_measured = data["impressions_measured"] is True
    if "pricing_model" in data or creating:
        placement.pricing_model = common.choice(data, "pricing_model", PRICING_MODELS, "fixed_fee")
    if placement.pricing_model == "cpm" and not placement.impressions_measured:
        raise ValidationError(
            details={
                "pricing_model": ["CPM needs reliable impression measurement for this placement."]
            }
        )
    if "default_currency" in data or creating:
        placement.default_currency = common.currency(data, "default_currency")
    for field, limit in (("restrictions", 1000), ("internal_notes", 5000)):
        if field in data:
            setattr(placement, field, common.text(data, field, limit))
    if "is_active" in data:
        placement.is_active = data["is_active"] is not False
    db.session.add(placement)
    db.session.flush()
    audit_service.record(
        "ad_placement.saved",
        "ad_placement",
        placement.id,
        actor=actor,
        details={"fields": sorted(data)},
    )
    return placement


# ---- rate cards ---------------------------------------------------------------------------


def rate_dict(r: RateCard) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "placement_id": r.placement_id,
        "placement": r.placement.name if r.placement else None,
        "pricing_model": r.pricing_model,
        "amount_minor": r.amount_minor,
        "currency": r.currency,
        "unit_label": r.unit_label,
        "description": r.description,
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_until": r.valid_until.isoformat() if r.valid_until else None,
        "is_public": r.is_public,
        "indicative": True,
    }


def list_rates() -> list[dict[str, Any]]:
    return [rate_dict(r) for r in db.session.scalars(select(RateCard).order_by(RateCard.name))]


def save_rate(data: dict[str, Any], actor, rate: RateCard | None = None) -> RateCard:
    creating = rate is None
    rate = rate or RateCard()
    if "name" in data or creating:
        rate.name = common.text(data, "name", 160, required=True)
    if "placement_id" in data:
        rate.placement_id = (
            get_placement(int(data["placement_id"])).id if data["placement_id"] else None
        )
    if "pricing_model" in data or creating:
        rate.pricing_model = common.choice(data, "pricing_model", PRICING_MODELS)
    if "amount_minor" in data or creating:
        rate.amount_minor = common.money(data, "amount_minor", required=True)
    if "currency" in data or creating:
        rate.currency = common.currency(data)
    for field, limit in (("unit_label", 80), ("description", 600)):
        if field in data:
            setattr(rate, field, common.text(data, field, limit))
    if "valid_from" in data:
        rate.valid_from = common.parse_date(data, "valid_from")
    if "valid_until" in data:
        rate.valid_until = common.parse_date(data, "valid_until")
    if "is_public" in data:
        rate.is_public = data["is_public"] is True
    if rate.pricing_model == "cpm":
        placement = db.session.get(AdPlacement, rate.placement_id) if rate.placement_id else None
        if placement is None or not placement.impressions_measured:
            raise ValidationError(
                details={"pricing_model": ["CPM rates need a placement with measured impressions."]}
            )
    db.session.add(rate)
    db.session.flush()
    audit_service.record("rate_card.saved", "rate_card", rate.id, actor=actor)
    return rate


def public_rates(today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    rows = db.session.scalars(
        select(RateCard).where(RateCard.is_public.is_(True)).order_by(RateCard.name)
    )
    from ...commerce.currency import format_money

    return [
        {
            "name": r.name,
            "placement": r.placement.name if r.placement else None,
            "pricing_model": r.pricing_model,
            "price": format_money(r.amount_minor, r.currency),
            "unit_label": r.unit_label,
            "description": r.description,
        }
        for r in rows
        if (not r.valid_from or r.valid_from <= today)
        and (not r.valid_until or r.valid_until >= today)
    ]


# ---- bookings -----------------------------------------------------------------------------


def effective_state(b: Booking, now: datetime | None = None) -> str:
    now = now or common.now()
    starts, ends = common.aware(b.starts_at), common.aware(b.ends_at)
    if b.status == "approved":
        if now < starts:
            return "scheduled"
        return "live" if now < ends else "ended"
    if b.status == "pending" and ends <= now:
        return "expired"
    return b.status


def overlapping(placement_id: int, starts: datetime, ends: datetime, exclude: int | None = None):
    query = select(Booking).where(
        Booking.placement_id == placement_id,
        Booking.status.in_(("pending", *HOLDING)),
        Booking.starts_at < ends,
        Booking.ends_at > starts,
    )
    if exclude:
        query = query.where(Booking.id != exclude)
    return list(db.session.scalars(query))


def conflicts(placement: AdPlacement, starts: datetime, ends: datetime, exclude: int | None = None):
    others = overlapping(placement.id, starts, ends, exclude)
    holding = [b for b in others if b.status in HOLDING]
    blocking = holding if len(holding) >= placement.capacity else []
    return {
        "blocking": [
            {
                "id": b.id,
                "partner": b.partner.name,
                "starts_at": iso(b.starts_at),
                "ends_at": iso(b.ends_at),
                "status": b.status,
            }
            for b in blocking
        ],
        "warnings": [
            {
                "id": b.id,
                "partner": b.partner.name,
                "starts_at": iso(b.starts_at),
                "ends_at": iso(b.ends_at),
                "status": b.status,
            }
            for b in others
            if b.status == "pending"
        ],
    }


def booking_dict(b: Booking, user) -> dict[str, Any]:
    return {
        "id": b.id,
        "placement": {"id": b.placement.id, "name": b.placement.name, "key": b.placement.key},
        "partner": {"id": b.partner.id, "name": b.partner.name},
        "campaign_id": b.campaign_id,
        "starts_at": iso(b.starts_at),
        "ends_at": iso(b.ends_at),
        "status": b.status,
        "state": effective_state(b),
        "agreed_fee_minor": b.agreed_fee_minor if common.can_see_money(user) else None,
        "currency": b.currency,
        "headline": b.headline,
        "body": b.body,
        "image_media_id": b.image_media_id,
        "link_url": b.link_url,
        "link_label": b.link_label,
        "notes": b.notes,
        "approved_at": iso(b.approved_at),
        "allowed_statuses": sorted(BOOKING_FLOW[b.status]),
        "history": common.history("booking", b.id),
    }


def list_bookings(args: dict[str, Any], user) -> list[dict[str, Any]]:
    query = select(Booking)
    if args.get("placement_id"):
        query = query.where(Booking.placement_id == int(args["placement_id"]))
    if args.get("partner_id"):
        query = query.where(Booking.partner_id == int(args["partner_id"]))
    if args.get("status"):
        query = query.where(Booking.status == args["status"])
    if args.get("upcoming"):
        query = query.where(Booking.ends_at > common.now())
    return [
        booking_dict(b, user)
        for b in db.session.scalars(query.order_by(Booking.starts_at).limit(500))
    ]


def get_booking(booking_id: int) -> Booking:
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError()
    return booking


def save_booking(
    data: dict[str, Any], actor, booking: Booking | None = None
) -> tuple[Booking, dict]:
    creating = booking is None
    if not creating and booking.status in ("stopped", "cancelled"):
        raise ConflictError("Stopped or cancelled bookings can't be edited.")
    booking = booking or Booking(status="pending")
    if "placement_id" in data or creating:
        placement = get_placement(int(data.get("placement_id") or 0))
        if not placement.is_active:
            raise ValidationError(details={"placement_id": ["This placement is inactive."]})
        booking.placement_id = placement.id
        booking.placement = placement
    if "partner_id" in data or creating:
        booking.partner_id = get_partner(int(data.get("partner_id") or 0)).id
    if "campaign_id" in data:
        campaign = (
            db.session.get(SponsorshipCampaign, data["campaign_id"])
            if data["campaign_id"]
            else None
        )
        if data["campaign_id"] and campaign is None:
            raise ValidationError(details={"campaign_id": ["Unknown campaign."]})
        booking.campaign_id = campaign.id if campaign else None
    if "starts_at" in data or creating:
        booking.starts_at = common.parse_datetime(data, "starts_at", required=True)
    if "ends_at" in data or creating:
        booking.ends_at = common.parse_datetime(data, "ends_at", required=True)
    if common.aware(booking.ends_at) <= common.aware(booking.starts_at):
        raise ValidationError(details={"ends_at": ["The end must be after the start."]})
    if "agreed_fee_minor" in data:
        booking.agreed_fee_minor = common.money(data, "agreed_fee_minor")
    if "currency" in data or creating:
        booking.currency = common.currency(data, default=booking.placement.default_currency)
    for field, limit in (("headline", 120), ("body", 400), ("link_label", 60), ("notes", 2000)):
        if field in data:
            setattr(booking, field, common.text(data, field, limit))
    if "link_url" in data:
        url = str(data["link_url"] or "").strip()
        if url and url.startswith("/"):
            if not safe_href(url) or url.startswith(("/admin", "/api")):
                raise ValidationError(
                    details={"link_url": ["Use a public site path or https link."]}
                )
        elif url:
            url = common.safe_https_url(url, "link_url")
        booking.link_url = url
    if "image_media_id" in data:
        media_id = data["image_media_id"]
        if media_id and db.session.get(MediaAsset, media_id) is None:
            raise ValidationError(
                details={"image_media_id": ["Choose an image from the media library."]}
            )
        booking.image_media_id = media_id or None
    found = conflicts(booking.placement, booking.starts_at, booking.ends_at, booking.id)
    if found["blocking"]:
        raise ConflictError(
            "This placement is already booked for part of that period.",
            details={"conflicts": found["blocking"]},
        )
    if (
        not creating
        and booking.status == "approved"
        and set(data)
        & {"starts_at", "ends_at", "placement_id", "headline", "body", "link_url", "image_media_id"}
    ):
        booking.status = "pending"  # material changes need re-approval
        common.record_event(
            "booking",
            booking.id,
            "approval_withdrawn",
            actor,
            from_state="approved",
            to_state="pending",
        )
        from ..publication_service import record_public_change

        record_public_change("ad_booking", booking.id, "booking_approval_withdrawn", actor)
    db.session.add(booking)
    db.session.flush()
    if creating:
        common.record_event("booking", booking.id, "created", actor, to_state="pending")
    audit_service.record(
        "ad_booking.saved", "ad_booking", booking.id, actor=actor, details={"fields": sorted(data)}
    )
    return booking, found


def move_booking(booking: Booking, data: dict[str, Any], actor) -> Booking:
    target = data.get("status")
    if target not in BOOKING_FLOW.get(booking.status, set()):
        raise ConflictError(f"A booking can't move from “{booking.status}” to “{target}”.")
    if target == "approved":
        if common.aware(booking.ends_at) <= common.now():
            raise ConflictError("This booking has already ended.")
        found = conflicts(booking.placement, booking.starts_at, booking.ends_at, booking.id)
        if found["blocking"]:
            raise ConflictError(
                "Another approved booking holds this placement.",
                details={"conflicts": found["blocking"]},
            )
        if booking.placement.channel == "website" and not (
            booking.headline or booking.image_media_id
        ):
            raise ValidationError(
                details={"status": ["Add the creative (headline or image) first."]}
            )
        if booking.status == "pending":
            booking.approved_at, booking.approved_by_id = common.now(), actor.id
    previous = booking.status
    booking.status = target
    common.record_event(
        "booking", booking.id, "status_change", actor, from_state=previous, to_state=target
    )
    audit_service.record(
        "ad_booking.status_changed",
        "ad_booking",
        booking.id,
        actor=actor,
        details={"from": previous, "to": target},
    )
    from ..publication_service import record_public_change

    record_public_change("ad_booking", booking.id, "ad_booking_changed", actor)
    return booking


# ---- public rendering ---------------------------------------------------------------------


def live_creatives(
    placement_key: str, limit: int = 6, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Approved bookings for a placement whose window includes ``now`` (plus the window, so
    the browser can hide them exactly at the end)."""
    now = now or common.now()
    placement = db.session.scalar(select(AdPlacement).where(AdPlacement.key == placement_key))
    if placement is None or not placement.is_active:
        return []
    rows = db.session.scalars(
        select(Booking)
        .where(
            Booking.placement_id == placement.id,
            Booking.status == "approved",
            Booking.starts_at <= now,
            Booking.ends_at > now,
        )
        .order_by(Booking.starts_at)
        .limit(limit)
    )
    out = []
    for b in rows:
        image = b.image.as_image() if b.image else None
        logo = b.partner.logo.as_image() if b.partner.logo else None
        out.append(
            {
                "id": b.id,
                "sponsor": b.partner.name,
                "headline": b.headline,
                "body": b.body,
                "image": image,
                "logo": logo,
                "link": {
                    "href": b.link_url,
                    "label": b.link_label or "Learn more",
                    "sponsored": True,
                }
                if b.link_url
                else None,
                "starts_at": iso(b.starts_at),
                "ends_at": iso(b.ends_at),
                "label": "Sponsored",
            }
        )
    return out


def next_boundary(after: datetime) -> datetime | None:
    """Next start/end of an approved booking (the scheduler queues a rebuild then)."""
    starts = db.session.scalar(
        select(func.min(Booking.starts_at)).where(
            Booking.status == "approved", Booking.starts_at > after
        )
    )
    ends = db.session.scalar(
        select(func.min(Booking.ends_at)).where(
            Booking.status == "approved", Booking.ends_at > after
        )
    )
    candidates = [common.aware(v) for v in (starts, ends) if v is not None]
    return min(candidates) if candidates else None


def utilization(
    date_from: date, date_to: date, placement_id: int | None = None
) -> list[dict[str, Any]]:
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    span_days = (end - start).total_seconds() / 86400
    query = select(AdPlacement).where(AdPlacement.is_active.is_(True))
    if placement_id:
        query = query.where(AdPlacement.id == placement_id)
    out = []
    for p in db.session.scalars(query.order_by(AdPlacement.name)):
        booked = 0.0
        for b in db.session.scalars(
            select(Booking).where(
                Booking.placement_id == p.id,
                Booking.status.in_(("approved", "paused", "stopped")),
                Booking.starts_at < end,
                Booking.ends_at > start,
            )
        ):
            lo, hi = max(common.aware(b.starts_at), start), min(common.aware(b.ends_at), end)
            booked += max(0.0, (hi - lo).total_seconds() / 86400)
        capacity_days = span_days * p.capacity
        out.append(
            {
                "placement": p.name,
                "key": p.key,
                "booked_days": round(booked, 1),
                "capacity_days": round(capacity_days, 1),
                "utilization_percent": round(100 * booked / capacity_days, 1)
                if capacity_days
                else 0,
            }
        )
    return out
