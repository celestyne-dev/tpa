"""Partners, inquiries, the opportunity pipeline and sponsorship campaigns.

Nothing here contacts partners automatically: the only outgoing email is the internal
notification about a new inquiry (when real delivery is configured).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from flask import current_app
from sqlalchemy import func, or_, select

from ...auth.permissions import Permission as P
from ...auth.rbac import has_permissions
from ...extensions import db
from ...models import (
    MediaAsset,
    Opportunity,
    Partner,
    PartnerContact,
    PartnershipInquiry,
    SponsorshipCampaign,
    User,
)
from ...models.partnerships import (
    CAMPAIGN_STATUSES,
    INQUIRY_STATUSES,
    OPPORTUNITY_STAGES,
    PARTNER_STATUSES,
    PARTNERSHIP_TYPES,
)
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common

BUDGET_RANGES = (
    "",
    "under_1000",
    "1000_5000",
    "5000_15000",
    "15000_plus",
    "not_sure",
)
PRIVACY_NOTICE_VERSION = "2026-10"
OPPORTUNITY_FLOW = {
    "new_inquiry": {"qualification", "lost", "cancelled"},
    "qualification": {"proposal", "lost", "cancelled"},
    "proposal": {"negotiation", "approved", "lost", "cancelled"},
    "negotiation": {"proposal", "approved", "lost", "cancelled"},
    "approved": {"contracted", "lost", "cancelled"},
    "contracted": {"active", "cancelled"},
    "active": {"completed", "cancelled"},
    "completed": set(),
    "lost": {"qualification"},  # reopen
    "cancelled": set(),
}
CAMPAIGN_FLOW = {
    "draft": {"internal_review", "cancelled"},
    "internal_review": {"draft", "sponsor_review", "approved", "cancelled"},
    "sponsor_review": {"internal_review", "approved", "cancelled"},
    "approved": {"scheduled", "active", "draft", "cancelled"},
    "scheduled": {"active", "approved", "cancelled"},
    "active": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
OPEN_STAGES = ("new_inquiry", "qualification", "proposal", "negotiation", "approved")


def _require(actor, perm) -> None:
    if not has_permissions(actor, perm):
        raise ForbiddenError()


def _paged(query, args, order):
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = list(db.session.scalars(query.order_by(*order).offset((page - 1) * size).limit(size)))
    return rows, total


# ---- partners ----------------------------------------------------------------------------


def partner_dict(p: Partner, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": p.id,
        "name": p.name,
        "website": p.website,
        "industry": p.industry,
        "country": p.country,
        "partnership_type": p.partnership_type,
        "status": p.status,
        "source": p.source,
        "owner": {"id": p.owner.id, "name": p.owner.display_name} if p.owner else None,
        "logo": p.logo.as_image() if p.logo else None,
        "logo_media_id": p.logo_media_id,
        "updated_at": iso(p.updated_at),
        "created_at": iso(p.created_at),
    }
    if detail:
        data.update(
            description=p.description,
            internal_notes=p.internal_notes,
            contacts=[
                {
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                    "role": c.role,
                    "is_primary": c.is_primary,
                }
                for c in p.contacts
            ],
        )
    return data


def list_partners(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(Partner)
    if args.get("status"):
        query = query.where(Partner.status == args["status"])
    if args.get("type"):
        query = query.where(Partner.partnership_type == args["type"])
    if args.get("q"):
        needle = f"%{args['q'].lower()}%"
        query = query.where(
            or_(func.lower(Partner.name).like(needle), func.lower(Partner.industry).like(needle))
        )
    rows, total = _paged(query, args, (Partner.name,))
    return [partner_dict(p) for p in rows], total


def get_partner(partner_id: int) -> Partner:
    partner = db.session.get(Partner, partner_id)
    if partner is None:
        raise NotFoundError()
    return partner


def _owner(value) -> int | None:
    if value in (None, ""):
        return None
    user = db.session.get(User, value) if isinstance(value, int) else None
    if user is None or user.status != "active":
        raise ValidationError(details={"owner_id": ["Choose an active administrator."]})
    return user.id


def save_partner(data: dict[str, Any], actor, partner: Partner | None = None) -> Partner:
    creating = partner is None
    partner = partner or Partner()
    if "name" in data or creating:
        partner.name = common.text(data, "name", 160, required=True)
    if "website" in data:
        partner.website = common.safe_https_url(data["website"], "website")
    for field, limit in (("industry", 120), ("description", 2000), ("country", 80), ("source", 80)):
        if field in data:
            setattr(partner, field, common.text(data, field, limit))
    if "internal_notes" in data:
        partner.internal_notes = common.text(data, "internal_notes", 10000)
    if "partnership_type" in data or creating:
        partner.partnership_type = common.choice(
            data, "partnership_type", PARTNERSHIP_TYPES, "other"
        )
    if "status" in data or creating:
        partner.status = common.choice(data, "status", PARTNER_STATUSES, "prospect")
    if "owner_id" in data:
        partner.owner_id = _owner(data["owner_id"])
    if "logo_media_id" in data:
        media_id = data["logo_media_id"]
        if media_id and db.session.get(MediaAsset, media_id) is None:
            raise ValidationError(
                details={"logo_media_id": ["Choose an image from the media library."]}
            )
        partner.logo_media_id = media_id or None
    if "contacts" in data:
        contacts = data["contacts"]
        if not isinstance(contacts, list) or len(contacts) > 20:
            raise ValidationError(details={"contacts": ["Send up to 20 contacts."]})
        partner.contacts.clear()
        for item in contacts:
            if not isinstance(item, dict):
                raise ValidationError(details={"contacts": ["Each contact must be an object."]})
            partner.contacts.append(
                PartnerContact(
                    name=common.text(item, "name", 120, required=True),
                    email=common.email(item, "email"),
                    role=common.text(item, "role", 120),
                    is_primary=item.get("is_primary") is True,
                )
            )
    db.session.add(partner)
    db.session.flush()
    audit_service.record(
        "partner.created" if creating else "partner.updated",
        "partner",
        partner.id,
        actor=actor,
        details={"fields": sorted(k for k in data if k != "internal_notes")},
    )
    return partner


# ---- public inquiries ---------------------------------------------------------------------


def submit_inquiry(data: dict[str, Any], *, ip: str | None = None) -> PartnershipInquiry | None:
    """Validate and store a public inquiry. Returns None when dropped as spam (the caller
    still answers generically). Only a stored inquiry is ever reported as received."""
    from ..newsletter.tokens import ip_hash

    if str(data.get("company_fax") or "").strip():
        return None
    try:
        elapsed = int(data.get("elapsed_ms") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    if 0 < elapsed < 1500:
        return None
    if data.get("privacy_consent") is not True:
        raise ValidationError(
            details={"privacy_consent": ["Please confirm you have read the privacy notice."]}
        )
    inquiry = PartnershipInquiry(
        organization=common.text(data, "organization", 160, required=True),
        contact_name=common.text(data, "contact_name", 120, required=True),
        email=common.email(data, "email", required=True),
        website=common.safe_https_url(data.get("website"), "website"),
        collaboration_type=common.choice(data, "collaboration_type", PARTNERSHIP_TYPES),
        budget_range=common.choice(data, "budget_range", BUDGET_RANGES, ""),
        objectives=common.text(data, "objectives", 2000),
        message=common.text(data, "message", 4000, required=True),
        privacy_notice_version=PRIVACY_NOTICE_VERSION,
        ip_hash=ip_hash(ip),
        status="new",
    )
    db.session.add(inquiry)
    db.session.flush()
    return inquiry


def notify_team(inquiry: PartnershipInquiry) -> str:
    """Internal notification after the inquiry is committed. Records the honest outcome."""
    from ..mail import EmailMessage, MailDeliveryError, MailNotConfiguredError, send

    to = (
        current_app.config.get("PARTNERSHIP_NOTIFY_EMAIL")
        or current_app.config.get("PARTNERSHIPS_EMAIL")
        or ""
    ).strip()
    if not to:
        status = "no_recipient"
    else:
        try:
            status = send(
                EmailMessage(
                    to=to,
                    subject=f"New partnership inquiry: {inquiry.organization}",
                    text=(
                        f"Organisation: {inquiry.organization}\nContact: {inquiry.contact_name}"
                        f"\nType: {inquiry.collaboration_type}\n\nReview it in the admin: "
                        f"{current_app.config['ADMIN_BASE_URL']}/admin/partnership-inquiries\n"
                        "(Contact details are only shown in the admin.)"
                    ),
                )
            )
        except MailNotConfiguredError:
            status = "not_configured"
        except MailDeliveryError:
            status = "failed"
    inquiry.notification_status = status[:30]
    return status


def inquiry_dict(i: PartnershipInquiry) -> dict[str, Any]:
    return {
        "id": i.id,
        "organization": i.organization,
        "contact_name": i.contact_name,
        "email": i.email,
        "website": i.website,
        "collaboration_type": i.collaboration_type,
        "budget_range": i.budget_range,
        "objectives": i.objectives,
        "message": i.message,
        "status": i.status,
        "notification_status": i.notification_status or None,
        "privacy_notice_version": i.privacy_notice_version,
        "partner_id": i.partner_id,
        "opportunity_id": i.opportunity_id,
        "created_at": iso(i.created_at),
    }


def list_inquiries(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(PartnershipInquiry)
    if args.get("status"):
        query = query.where(PartnershipInquiry.status == args["status"])
    rows, total = _paged(query, args, (PartnershipInquiry.created_at.desc(),))
    return [inquiry_dict(i) for i in rows], total


def update_inquiry(inquiry_id: int, data: dict[str, Any], actor) -> PartnershipInquiry:
    inquiry = db.session.get(PartnershipInquiry, inquiry_id)
    if inquiry is None:
        raise NotFoundError()
    if data.get("action") == "convert":
        if inquiry.opportunity_id:
            raise ConflictError("This inquiry was already converted.")
        partner = (
            get_partner(int(data["partner_id"]))
            if data.get("partner_id")
            else save_partner(
                {
                    "name": inquiry.organization,
                    "website": inquiry.website,
                    "partnership_type": inquiry.collaboration_type,
                    "source": "website inquiry",
                    "contacts": [
                        {"name": inquiry.contact_name, "email": inquiry.email, "is_primary": True}
                    ],
                },
                actor,
            )
        )
        opportunity = save_opportunity(
            {
                "partner_id": partner.id,
                "title": f"{inquiry.organization} — {inquiry.collaboration_type.replace('_', ' ')}",
            },
            actor,
        )
        inquiry.partner_id, inquiry.opportunity_id, inquiry.status = (
            partner.id,
            opportunity.id,
            "converted",
        )
    else:
        inquiry.status = common.choice(data, "status", INQUIRY_STATUSES)
    inquiry.reviewed_at = common.now()
    audit_service.record(
        "partnership_inquiry.updated",
        "partnership_inquiry",
        inquiry.id,
        actor=actor,
        details={"status": inquiry.status},
    )
    return inquiry


# ---- opportunities ------------------------------------------------------------------------


def opportunity_dict(o: Opportunity, user, *, detail: bool = False) -> dict[str, Any]:
    show = common.can_see_money(user)
    data = {
        "id": o.id,
        "title": o.title,
        "stage": o.stage,
        "partner": {"id": o.partner.id, "name": o.partner.name},
        "owner": {"id": o.owner.id, "name": o.owner.display_name} if o.owner else None,
        "expected_value_minor": o.expected_value_minor if show else None,
        "currency": o.currency,
        "follow_up_on": o.follow_up_on.isoformat() if o.follow_up_on else None,
        "updated_at": iso(o.updated_at),
        "allowed_stages": sorted(OPPORTUNITY_FLOW[o.stage]),
    }
    if detail:
        data.update(
            internal_reference=o.internal_reference,
            proposal_reference=o.proposal_reference,
            notes=o.notes,
            lost_reason=o.lost_reason,
            history=common.history("opportunity", o.id),
            campaigns=[
                {"id": c.id, "name": c.name, "status": c.status}
                for c in db.session.scalars(
                    select(SponsorshipCampaign).where(SponsorshipCampaign.opportunity_id == o.id)
                )
            ],
        )
    return data


def list_opportunities(args: dict[str, Any], user) -> tuple[list[dict[str, Any]], int]:
    query = select(Opportunity)
    if args.get("stage"):
        query = query.where(Opportunity.stage == args["stage"])
    if args.get("partner_id"):
        query = query.where(Opportunity.partner_id == int(args["partner_id"]))
    if args.get("owner_id"):
        query = query.where(Opportunity.owner_id == int(args["owner_id"]))
    rows, total = _paged(
        query,
        args,
        (Opportunity.follow_up_on.is_(None), Opportunity.follow_up_on, Opportunity.id.desc()),
    )
    return [opportunity_dict(o, user) for o in rows], total


def get_opportunity(opportunity_id: int) -> Opportunity:
    opportunity = db.session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise NotFoundError()
    return opportunity


def save_opportunity(
    data: dict[str, Any], actor, opportunity: Opportunity | None = None
) -> Opportunity:
    creating = opportunity is None
    if creating:
        opportunity = Opportunity(
            partner_id=get_partner(int(data.get("partner_id") or 0)).id, stage="new_inquiry"
        )
    if "title" in data or creating:
        opportunity.title = common.text(data, "title", 200, required=True)
    if "owner_id" in data:
        opportunity.owner_id = _owner(data["owner_id"])
    if "expected_value_minor" in data:
        opportunity.expected_value_minor = common.money(data, "expected_value_minor")
    if "currency" in data:
        opportunity.currency = common.currency(data)
    if "follow_up_on" in data:
        opportunity.follow_up_on = common.parse_date(data, "follow_up_on")
    for field, limit in (
        ("internal_reference", 200),
        ("proposal_reference", 300),
        ("notes", 10000),
    ):
        if field in data:
            setattr(opportunity, field, common.text(data, field, limit))
    db.session.add(opportunity)
    db.session.flush()
    if creating:
        common.record_event(
            "opportunity", opportunity.id, "created", actor, to_state=opportunity.stage
        )
    audit_service.record(
        "opportunity.created" if creating else "opportunity.updated",
        "opportunity",
        opportunity.id,
        actor=actor,
        details={"fields": sorted(data)},
    )
    return opportunity


def move_opportunity(opportunity: Opportunity, data: dict[str, Any], actor) -> Opportunity:
    target = common.choice(data, "stage", OPPORTUNITY_STAGES)
    if target not in OPPORTUNITY_FLOW[opportunity.stage]:
        raise ConflictError(
            f"An opportunity can't move from “{opportunity.stage}” to “{target}”.",
            details={"allowed": sorted(OPPORTUNITY_FLOW[opportunity.stage])},
        )
    if target == "lost":
        opportunity.lost_reason = common.text(data, "reason", 300, required=True)
    previous = opportunity.stage
    opportunity.stage = target
    common.record_event(
        "opportunity",
        opportunity.id,
        "stage_change",
        actor,
        from_state=previous,
        to_state=target,
        summary=str(data.get("reason") or "")[:300],
    )
    audit_service.record(
        "opportunity.stage_changed",
        "opportunity",
        opportunity.id,
        actor=actor,
        details={"from": previous, "to": target},
    )
    return opportunity


def add_interaction(opportunity: Opportunity, data: dict[str, Any], actor) -> None:
    kind = common.choice(data, "kind", ("call", "email", "meeting", "note"), "note")
    common.record_event(
        "opportunity",
        opportunity.id,
        kind,
        actor,
        summary=common.text(data, "summary", 2000, required=True),
        occurred_on=common.parse_date(data, "occurred_on") or date.today(),
    )
    if "follow_up_on" in data:
        opportunity.follow_up_on = common.parse_date(data, "follow_up_on")


# ---- campaigns ----------------------------------------------------------------------------


def campaign_dict(c: SponsorshipCampaign, user, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "partner": {"id": c.partner.id, "name": c.partner.name},
        "opportunity_id": c.opportunity_id,
        "starts_on": c.starts_on.isoformat() if c.starts_on else None,
        "ends_on": c.ends_on.isoformat() if c.ends_on else None,
        "contracted_fee_minor": c.contracted_fee_minor if common.can_see_money(user) else None,
        "currency": c.currency,
        "disclosure_text": c.disclosure_text,
        "approved_at": iso(c.approved_at),
        "allowed_statuses": sorted(CAMPAIGN_FLOW[c.status]),
        "updated_at": iso(c.updated_at),
    }
    if detail:
        data["notes"] = c.notes
        data["history"] = common.history("campaign", c.id)
    return data


def list_campaigns(args: dict[str, Any], user) -> tuple[list[dict[str, Any]], int]:
    query = select(SponsorshipCampaign)
    if args.get("status"):
        query = query.where(SponsorshipCampaign.status == args["status"])
    if args.get("partner_id"):
        query = query.where(SponsorshipCampaign.partner_id == int(args["partner_id"]))
    rows, total = _paged(
        query, args, (SponsorshipCampaign.starts_on.desc(), SponsorshipCampaign.id.desc())
    )
    return [campaign_dict(c, user) for c in rows], total


def get_campaign(campaign_id: int) -> SponsorshipCampaign:
    campaign = db.session.get(SponsorshipCampaign, campaign_id)
    if campaign is None:
        raise NotFoundError()
    return campaign


def save_campaign(data: dict[str, Any], actor, campaign: SponsorshipCampaign | None = None):
    creating = campaign is None
    if creating:
        campaign = SponsorshipCampaign(
            partner_id=get_partner(int(data.get("partner_id") or 0)).id, status="draft"
        )
    elif campaign.status in ("completed", "cancelled"):
        raise ConflictError("Completed or cancelled campaigns can't be edited.")
    if "name" in data or creating:
        campaign.name = common.text(data, "name", 200, required=True)
    if "opportunity_id" in data:
        campaign.opportunity_id = (
            get_opportunity(int(data["opportunity_id"])).id if data["opportunity_id"] else None
        )
    if "starts_on" in data:
        campaign.starts_on = common.parse_date(data, "starts_on")
    if "ends_on" in data:
        campaign.ends_on = common.parse_date(data, "ends_on")
    if campaign.starts_on and campaign.ends_on and campaign.ends_on < campaign.starts_on:
        raise ValidationError(
            details={"ends_on": ["The end date must be on or after the start date."]}
        )
    if "contracted_fee_minor" in data:
        campaign.contracted_fee_minor = common.money(data, "contracted_fee_minor")
    if "currency" in data:
        campaign.currency = common.currency(data)
    if "disclosure_text" in data:
        campaign.disclosure_text = common.text(data, "disclosure_text", 400)
    if "notes" in data:
        campaign.notes = common.text(data, "notes", 10000)
    if not creating and campaign.status in ("approved", "scheduled") and set(data) - {"notes"}:
        # Material edits after approval need a new approval.
        common.record_event(
            "campaign",
            campaign.id,
            "approval_withdrawn",
            actor,
            from_state=campaign.status,
            to_state="draft",
        )
        campaign.status, campaign.approved_at, campaign.approved_by_id = "draft", None, None
    db.session.add(campaign)
    db.session.flush()
    if creating:
        common.record_event("campaign", campaign.id, "created", actor, to_state="draft")
    audit_service.record(
        "sponsorship_campaign.created" if creating else "sponsorship_campaign.updated",
        "sponsorship_campaign",
        campaign.id,
        actor=actor,
        details={"fields": sorted(data)},
    )
    return campaign


def move_campaign(
    campaign: SponsorshipCampaign, data: dict[str, Any], actor
) -> SponsorshipCampaign:
    target = common.choice(data, "status", CAMPAIGN_STATUSES)
    if target not in CAMPAIGN_FLOW[campaign.status]:
        raise ConflictError(
            f"A campaign can't move from “{campaign.status}” to “{target}”.",
            details={"allowed": sorted(CAMPAIGN_FLOW[campaign.status])},
        )
    today = date.today()
    if target == "approved":
        _require(actor, P.SPONSORSHIPS_APPROVE)
        problems = []
        if not campaign.starts_on or not campaign.ends_on:
            problems.append("Set the campaign start and end dates.")
        if len(campaign.disclosure_text) < 10:
            problems.append("Add the sponsorship disclosure text.")
        if problems:
            raise ValidationError(
                "This campaign isn't ready to approve.", details={"status": problems}
            )
        campaign.approved_at, campaign.approved_by_id = common.now(), actor.id
    if target == "scheduled" and not (campaign.starts_on and campaign.starts_on > today):
        raise ValidationError(
            details={"status": ["Only campaigns starting in the future can be scheduled."]}
        )
    if target == "active" and not (
        campaign.starts_on and campaign.ends_on and campaign.starts_on <= today <= campaign.ends_on
    ):
        raise ValidationError(
            details={"status": ["A campaign is active only between its start and end dates."]}
        )
    previous = campaign.status
    campaign.status = target
    if target == "draft":
        campaign.approved_at = campaign.approved_by_id = None
    common.record_event(
        "campaign", campaign.id, "status_change", actor, from_state=previous, to_state=target
    )
    audit_service.record(
        "sponsorship_campaign.status_changed",
        "sponsorship_campaign",
        campaign.id,
        actor=actor,
        details={"from": previous, "to": target},
    )
    return campaign


def user_options() -> list[dict[str, Any]]:
    users = db.session.scalars(
        select(User).where(User.status == "active").order_by(User.display_name)
    )
    return [{"id": u.id, "name": u.display_name} for u in users]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
