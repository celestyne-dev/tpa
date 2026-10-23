"""Newsletter campaigns: editing, approval, scheduling, sending, previews and reports.

Workflow: draft -> approved (newsletters.publish) -> scheduled (newsletters.schedule) or
sending (newsletters.send) -> sent. Any edit to an approved campaign withdraws the
approval. Previews and test emails never change a campaign's status and never reach its
audience: test emails go only to the signed-in staff member or to the configured test
recipients, from a separate code path.

Queueing happens in the email worker: "send" and due schedules only mark the campaign as
``sending``; the worker freezes the content (snapshot), resolves the audience once and
inserts one idempotent message per recipient.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update

from ...cms.blocks import safe_href
from ...extensions import db
from ...models import Article, Campaign, EmailMessage, EmailTemplate, Product, SubscriberEvent
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import config
from .queue import enqueue
from .render import build_email, personalise, validate_email_blocks
from .segments import get_segment, resolve

EDITABLE = ("draft", "approved")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Starter-template guidance looks like "[One small, practical step ...]".
GUIDANCE = re.compile(r"\[[A-Z][^\]]{3,}\]")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _plain(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    text = re.sub(r"[\x00-\x1f]", " ", str(value or "")).strip()
    if required and not text:
        raise ValidationError(details={field: ["This field is required."]})
    if len(text) > limit or "<" in text or ">" in text:
        raise ValidationError(details={field: [f"Plain text up to {limit} characters."]})
    return text


def _ids(value: Any, field: str, model, limit: int) -> list[int]:
    if value is None:
        return []
    if (
        not isinstance(value, list)
        or len(value) > limit
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        raise ValidationError(details={field: [f"Choose up to {limit} items."]})
    found = set(db.session.scalars(select(model.id).where(model.id.in_(value))))
    if set(value) - found:
        raise ValidationError(details={field: ["Some selected items no longer exist."]})
    return list(dict.fromkeys(value))


def _ctas(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 3:
        raise ValidationError(details={"ctas": ["Add up to three buttons."]})
    out = []
    for i, cta in enumerate(value):
        if not isinstance(cta, dict):
            raise ValidationError(details={"ctas": [f"Button {i + 1} is invalid."]})
        label = _plain(cta.get("label"), "ctas", 60, required=True)
        href = str(cta.get("href") or "").strip()
        if not safe_href(href):
            raise ValidationError(
                details={"ctas": [f"Button {i + 1}: use a site path or https link."]}
            )
        out.append({"label": label, "href": href})
    return out


def campaign_dict(c: Campaign, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": c.id,
        "public_id": c.public_id,
        "name": c.name,
        "subject": c.subject,
        "status": c.status,
        "segment": {"id": c.segment.id, "name": c.segment.name} if c.segment else None,
        "scheduled_at": iso(c.scheduled_at),
        "approved_at": iso(c.approved_at),
        "queued_at": iso(c.queued_at),
        "completed_at": iso(c.completed_at),
        "cancelled_at": iso(c.cancelled_at),
        "send_mode": c.send_mode or None,
        "eligible_count": c.eligible_count,
        "updated_at": iso(c.updated_at),
        "lock_version": c.lock_version,
    }
    if detail:
        data.update(
            {
                "preheader": c.preheader,
                "from_name": c.from_name,
                "reply_to": c.reply_to,
                "template_key": c.template_key,
                "blocks": c.blocks,
                "article_ids": c.article_ids,
                "product_ids": c.product_ids,
                "ctas": c.ctas,
                "segment_id": c.segment_id,
                "approved_by_id": c.approved_by_id,
            }
        )
    return data


def list_campaigns(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(Campaign)
    if args.get("status"):
        query = query.where(Campaign.status == args["status"])
    if args.get("q"):
        query = query.where(func.lower(Campaign.name).like(f"%{args['q'].lower()}%"))
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        query.order_by(Campaign.updated_at.desc(), Campaign.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return [campaign_dict(c) for c in rows], total


def get_campaign(campaign_id: int) -> Campaign:
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError()
    return campaign


def _apply(campaign: Campaign, data: dict[str, Any]) -> None:
    allowed = {
        "name",
        "subject",
        "preheader",
        "from_name",
        "reply_to",
        "blocks",
        "article_ids",
        "product_ids",
        "ctas",
        "segment_id",
        "lock_version",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValidationError(details={k: ["Unknown field."] for k in unknown})
    if "name" in data:
        campaign.name = _plain(data["name"], "name", 160, required=True)
    for field, limit in (("subject", 200), ("preheader", 200), ("from_name", 80)):
        if field in data:
            setattr(campaign, field, _plain(data[field], field, limit))
    if "reply_to" in data:
        reply = str(data["reply_to"] or "").strip()
        if reply and not _EMAIL.match(reply):
            raise ValidationError(details={"reply_to": ["Enter a valid email address."]})
        campaign.reply_to = reply
    if "blocks" in data:
        campaign.blocks = validate_email_blocks(data["blocks"])
    if "article_ids" in data:
        campaign.article_ids = _ids(data["article_ids"], "article_ids", Article, 6)
    if "product_ids" in data:
        campaign.product_ids = _ids(data["product_ids"], "product_ids", Product, 4)
    if "ctas" in data:
        campaign.ctas = _ctas(data["ctas"])
    if "segment_id" in data:
        campaign.segment_id = (
            get_segment(int(data["segment_id"])).id if data["segment_id"] else None
        )


def create_campaign(data: dict[str, Any], actor) -> Campaign:
    template = None
    if data.get("template_key"):
        template = db.session.scalar(
            select(EmailTemplate).where(EmailTemplate.key == data["template_key"])
        )
        if template is None:
            raise ValidationError(details={"template_key": ["Unknown template."]})
    campaign = Campaign(
        public_id=secrets.token_hex(12),
        name="Untitled campaign",
        template_key=template.key if template else "",
        subject=template.subject if template else "",
        preheader=template.preheader if template else "",
        blocks=list(template.blocks) if template else [],
        article_ids=[],
        product_ids=[],
        ctas=[],
        status="draft",
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    _apply(campaign, {k: v for k, v in data.items() if k != "template_key"})
    if not data.get("name") and template:
        campaign.name = template.name
    db.session.add(campaign)
    db.session.flush()
    audit_service.record("newsletter.created", "campaign", campaign.id, actor=actor)
    return campaign


def update_campaign(campaign: Campaign, data: dict[str, Any], actor) -> Campaign:
    if campaign.status not in EDITABLE:
        raise ConflictError("Only draft or approved campaigns can be edited.")
    lock = data.get("lock_version")
    if lock is not None and lock != campaign.lock_version:
        raise ConflictError(
            "Someone else saved this campaign. Reload to see their changes.",
            details={"code": "edit_conflict", "lock_version": campaign.lock_version},
        )
    _apply(campaign, data)
    if campaign.status == "approved":
        campaign.status = "draft"
        campaign.approved_at = None
        campaign.approved_by_id = None
    campaign.lock_version += 1
    campaign.updated_by_id = actor.id
    return campaign


def duplicate_campaign(campaign: Campaign, actor) -> Campaign:
    copy = Campaign(
        public_id=secrets.token_hex(12),
        name=f"{campaign.name} (copy)"[:160],
        subject=campaign.subject,
        preheader=campaign.preheader,
        from_name=campaign.from_name,
        reply_to=campaign.reply_to,
        template_key=campaign.template_key,
        blocks=list(campaign.blocks),
        article_ids=list(campaign.article_ids),
        product_ids=list(campaign.product_ids),
        ctas=list(campaign.ctas),
        segment_id=campaign.segment_id,
        status="draft",
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(copy)
    db.session.flush()
    audit_service.record(
        "newsletter.duplicated", "campaign", copy.id, actor=actor, details={"from": campaign.id}
    )
    return copy


def delete_campaign(campaign: Campaign, actor) -> None:
    if campaign.status not in EDITABLE:
        raise ConflictError("Sent, scheduled or sending campaigns can't be deleted.")
    audit_service.record("newsletter.deleted", "campaign", campaign.id, actor=actor)
    db.session.delete(campaign)


def _problems(campaign: Campaign) -> list[str]:
    problems = []
    if not campaign.subject:
        problems.append("Add a subject line.")
    if not campaign.blocks:
        problems.append("Add some content.")
    text = " ".join(str(v) for b in campaign.blocks for v in b.values() if isinstance(v, str))
    if GUIDANCE.search(f"{campaign.subject} {campaign.preheader} {text}"):
        problems.append("Replace the [bracketed guidance] from the template.")
    return problems


def approve(campaign: Campaign, actor) -> Campaign:
    if campaign.status != "draft":
        raise ConflictError("Only drafts can be approved.")
    problems = _problems(campaign)
    if problems:
        raise ValidationError(
            "This campaign isn't ready to approve.", details={"campaign": problems}
        )
    campaign.status = "approved"
    campaign.approved_at = _now()
    campaign.approved_by_id = actor.id
    audit_service.record("newsletter.approved", "campaign", campaign.id, actor=actor)
    return campaign


def withdraw_approval(campaign: Campaign, actor) -> Campaign:
    if campaign.status != "approved":
        raise ConflictError("This campaign is not approved.")
    campaign.status = "draft"
    campaign.approved_at = campaign.approved_by_id = None
    audit_service.record("newsletter.approval_withdrawn", "campaign", campaign.id, actor=actor)
    return campaign


def _ensure_can_send() -> str:
    mode = config.sending_mode()
    if mode == "disabled":
        raise ConflictError(
            "Email sending is disabled. A Super Admin can enable it in Email settings."
        )
    return mode


def schedule(campaign: Campaign, data: dict[str, Any], actor) -> Campaign:
    if campaign.status != "approved":
        raise ConflictError("Approve the campaign before scheduling it.")
    try:
        when = datetime.fromisoformat(str(data.get("scheduled_at") or "").replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(details={"scheduled_at": ["Use an ISO date and time."]}) from None
    when = _aware(when)
    if when < _now() + timedelta(minutes=2):
        raise ValidationError(
            details={"scheduled_at": ["Choose a time at least 2 minutes from now."]}
        )
    campaign.status = "scheduled"
    campaign.scheduled_at = when
    audit_service.record(
        "newsletter.scheduled", "campaign", campaign.id, actor=actor, details={"at": iso(when)}
    )
    return campaign


def unschedule(campaign: Campaign, actor) -> Campaign:
    if campaign.status != "scheduled":
        raise ConflictError("This campaign is not scheduled.")
    campaign.status = "approved"
    campaign.scheduled_at = None
    audit_service.record("newsletter.unscheduled", "campaign", campaign.id, actor=actor)
    return campaign


def send_now(campaign: Campaign, actor) -> Campaign:
    _ensure_can_send()
    won = db.session.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id, Campaign.status.in_(("approved", "scheduled")))
        .values(status="sending", scheduled_at=None)
    ).rowcount
    if not won:
        raise ConflictError("Only approved campaigns can be sent.")
    db.session.refresh(campaign)
    audit_service.record("newsletter.send_requested", "campaign", campaign.id, actor=actor)
    return campaign


def cancel(campaign: Campaign, actor) -> dict[str, Any]:
    if campaign.status == "scheduled":
        unschedule(campaign, actor)
        return {"cancelled_messages": 0}
    if campaign.status != "sending":
        raise ConflictError("Only scheduled or sending campaigns can be cancelled.")
    count = db.session.execute(
        update(EmailMessage)
        .where(EmailMessage.campaign_id == campaign.id, EmailMessage.status == "queued")
        .values(status="cancelled", error="Campaign cancelled.", finished_at=_now())
    ).rowcount
    campaign.status = "cancelled"
    campaign.cancelled_at = _now()
    audit_service.record(
        "newsletter.cancelled", "campaign", campaign.id, actor=actor, details={"unsent": count}
    )
    return {"cancelled_messages": count or 0}


def render_campaign(campaign: Campaign, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    data = {
        "subject": campaign.subject,
        "preheader": campaign.preheader,
        "blocks": campaign.blocks,
        "article_ids": campaign.article_ids,
        "product_ids": campaign.product_ids,
        "ctas": campaign.ctas,
    }
    if overrides:
        data["subject"] = _plain(overrides.get("subject", data["subject"]), "subject", 200)
        data["preheader"] = _plain(overrides.get("preheader", data["preheader"]), "preheader", 200)
        if "blocks" in overrides:
            data["blocks"] = validate_email_blocks(overrides["blocks"])
        if "article_ids" in overrides:
            data["article_ids"] = _ids(overrides["article_ids"], "article_ids", Article, 6)
        if "product_ids" in overrides:
            data["product_ids"] = _ids(overrides["product_ids"], "product_ids", Product, 4)
        if "ctas" in overrides:
            data["ctas"] = _ctas(overrides["ctas"])
    return build_email(**data)


def preview(campaign: Campaign, overrides: dict[str, Any] | None = None) -> dict[str, str]:
    """Rendered for the admin preview only: no queueing, no status change."""
    rendered = render_campaign(campaign, overrides)
    note = "#preview-only"
    return personalise(rendered, first_name="", unsubscribe_url=note, preferences_url=note)


def send_test(campaign: Campaign, data: dict[str, Any], actor) -> dict[str, Any]:
    """Send one test copy synchronously to the requester (or a configured test address)."""
    from .providers import OutgoingEmail, PermanentSendError, TransientSendError, get_provider

    to = str(data.get("to") or actor.email).strip().lower()
    if to != (actor.email or "").lower() and not config.is_test_recipient(to):
        raise ValidationError(
            details={"to": ["Test emails go to your own address or a configured test recipient."]}
        )
    if not config.backend_configured():
        raise ConflictError("Email delivery is not configured on the server.")
    from_name, from_email = config.from_address(campaign.from_name)
    if not from_email:
        raise ConflictError("No sender address is configured (NEWSLETTER_FROM_EMAIL).")
    rendered = personalise(
        render_campaign(campaign),
        first_name=actor.display_name.split(" ")[0] if actor.display_name else "",
        unsubscribe_url=f"{config_site()}/newsletter#test-email",
        preferences_url=f"{config_site()}/newsletter#test-email",
    )
    message = EmailMessage(
        kind="test",
        dedupe_key=f"test:{campaign.id}:{secrets.token_hex(8)}",
        to_email=to,
        campaign_id=None,  # never counted in the campaign's report
        subject=f"[TEST] {rendered['subject']}"[:200],
        send_mode="test",
        status="sending",
        attempts=1,
        attempt_started_at=_now(),
    )
    db.session.add(message)
    provider = get_provider()
    try:
        message.provider_message_id = provider.send(
            OutgoingEmail(
                to=to,
                subject=message.subject,
                html=rendered["html"],
                text=rendered["text"],
                from_name=from_name,
                from_email=from_email,
                reply_to=campaign.reply_to or config.get_settings()["email.reply_to"] or "",
            )
        )[:255]
        message.status, message.accepted_at = "accepted", _now()
    except (TransientSendError, PermanentSendError) as err:
        message.status, message.error = "failed", str(err)[:300]
    finally:
        provider.close()
        message.provider = provider.name
        message.finished_at = _now()
    audit_service.record(
        "newsletter.test_sent",
        "campaign",
        campaign.id,
        actor=actor,
        details={"status": message.status},
    )
    return {"status": message.status, "error": message.error or None, "to": to}


def config_site() -> str:
    from flask import current_app

    return current_app.config["SITE_URL"].rstrip("/")


# ---- worker side ------------------------------------------------------------------------


def start_due_scheduled() -> int:
    if config.sending_mode() == "disabled":
        return 0
    return (
        db.session.execute(
            update(Campaign)
            .where(Campaign.status == "scheduled", Campaign.scheduled_at <= _now())
            .values(status="sending")
        ).rowcount
        or 0
    )


def prepare_sending() -> int:
    """Freeze content and queue one message per eligible recipient (idempotent)."""
    prepared = 0
    for campaign in db.session.scalars(
        select(Campaign).where(Campaign.status == "sending", Campaign.queued_at.is_(None))
    ):
        if campaign.snapshot is None:
            rendered = render_campaign(campaign)
            from_name, _ = config.from_address(campaign.from_name)
            campaign.snapshot = {
                **rendered,
                "from_name": from_name,
                "reply_to": campaign.reply_to or config.get_settings()["email.reply_to"] or "",
            }
            campaign.send_mode = config.sending_mode()
        audience = resolve(campaign.segment.rules if campaign.segment else [])
        campaign.eligible_count = len(audience)
        existing = set(
            db.session.scalars(
                select(EmailMessage.subscriber_id).where(EmailMessage.campaign_id == campaign.id)
            )
        )
        for subscriber in audience:
            if subscriber.id in existing:
                continue
            message = enqueue(
                kind="campaign",
                to=subscriber.email,
                subscriber=subscriber,
                campaign=campaign,
                dedupe_key=f"campaign:{campaign.id}:{subscriber.id}",
            )
            if message is not None:
                message.send_mode = campaign.send_mode
        campaign.queued_at = _now()
        prepared += 1
        db.session.commit()
    return prepared


def finish_completed() -> int:
    done = 0
    for campaign in db.session.scalars(
        select(Campaign).where(Campaign.status == "sending", Campaign.queued_at.is_not(None))
    ):
        open_count = db.session.scalar(
            select(func.count())
            .select_from(EmailMessage)
            .where(
                EmailMessage.campaign_id == campaign.id,
                EmailMessage.status.in_(("queued", "sending")),
            )
        )
        if not open_count:
            campaign.status = "sent"
            campaign.completed_at = _now()
            done += 1
    return done


def report(campaign: Campaign) -> dict[str, Any]:
    counts = dict(
        db.session.execute(
            select(EmailMessage.status, func.count())
            .where(EmailMessage.campaign_id == campaign.id)
            .group_by(EmailMessage.status)
        ).all()
    )
    attempted = db.session.scalar(
        select(func.count())
        .select_from(EmailMessage)
        .where(EmailMessage.campaign_id == campaign.id, EmailMessage.attempts > 0)
    )
    unsubscribed = 0
    if campaign.queued_at:
        unsubscribed = sum(
            1
            for e in db.session.scalars(
                select(SubscriberEvent).where(
                    SubscriberEvent.event == "unsubscribed",
                    SubscriberEvent.created_at >= campaign.queued_at,
                )
            )
            if (e.details or {}).get("campaign") == campaign.public_id
        )
    accepted_total = sum(
        counts.get(k, 0) for k in ("accepted", "delivered", "bounced", "complained")
    )
    return {
        "status": campaign.status,
        "send_mode": campaign.send_mode or None,
        "eligible": campaign.eligible_count,
        "queued": counts.get("queued", 0) + counts.get("sending", 0),
        "attempted": attempted or 0,
        "accepted": accepted_total,
        "delivered_confirmed": counts.get("delivered", 0),
        "failed": counts.get("failed", 0),
        "bounced": counts.get("bounced", 0),
        "complained": counts.get("complained", 0),
        "unknown": counts.get("unknown", 0),
        "suppressed": counts.get("suppressed", 0),
        "skipped_test_mode": counts.get("skipped", 0),
        "cancelled": counts.get("cancelled", 0),
        "unsubscribed_from_campaign": unsubscribed,
        "opens_and_clicks": None,
        "notes": [
            "“Accepted” means the delivery provider took the message; it is not proof of delivery.",
            "Delivery, bounces and complaints are counted only from signed provider feedback.",
            "Opens and clicks are not tracked.",
        ],
    }


def messages(campaign: Campaign, args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(EmailMessage).where(EmailMessage.campaign_id == campaign.id)
    if args.get("status"):
        query = query.where(EmailMessage.status == args["status"])
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(query.order_by(EmailMessage.id).offset((page - 1) * size).limit(size))
    return [message_dict(m) for m in rows], total


def message_dict(m: EmailMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "kind": m.kind,
        "to": m.to_email,
        "status": m.status,
        "attempts": m.attempts,
        "error": m.error or None,
        "send_mode": m.send_mode,
        "created_at": iso(m.created_at),
        "accepted_at": iso(m.accepted_at),
        "delivered_at": iso(m.delivered_at),
        "bounced_at": iso(m.bounced_at),
        "finished_at": iso(m.finished_at),
    }


# ---- templates --------------------------------------------------------------------------


def template_dict(t: EmailTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "kind": t.kind,
        "description": t.description,
        "subject": t.subject,
        "preheader": t.preheader,
        "blocks": t.blocks,
        "is_starter": t.is_starter,
        "updated_at": iso(t.updated_at),
    }


def save_template(
    data: dict[str, Any], actor, template: EmailTemplate | None = None
) -> EmailTemplate:
    template = template or EmailTemplate(kind="campaign", is_starter=False)
    if template.id is None:
        key = re.sub(
            r"[^a-z0-9_]+", "_", str(data.get("key") or data.get("name") or "").lower()
        ).strip("_")[:60]
        if not key or db.session.scalar(select(EmailTemplate.id).where(EmailTemplate.key == key)):
            raise ValidationError(details={"key": ["Choose a unique key."]})
        template.key = key
    if "name" in data or template.id is None:
        template.name = _plain(data.get("name"), "name", 120, required=True)
    for field, limit in (("description", 300), ("subject", 200), ("preheader", 200)):
        if field in data:
            setattr(template, field, _plain(data[field], field, limit))
    if "blocks" in data:
        template.blocks = validate_email_blocks(data["blocks"])
    template.updated_by_id = actor.id
    db.session.add(template)
    return template
