"""Lightweight email automations: trigger -> audience -> ordered steps with delays.

- Triggers: subscription confirmed, lead magnet claimed, article published, product
  published, and inactivity (re-engagement).
- Enrolment is unique per (automation, subscriber, context), so nobody receives the
  same sequence twice for the same trigger; step messages are deduplicated as well.
- Only marketable subscribers are enrolled; product announcements additionally require
  the "products" preference (independent marketing consent).
- Exit conditions are checked before every step: unsubscribed/suppressed, an exit tag,
  or (re-engagement) any new engagement.
- Publishing an article or product only records a trigger event in the same transaction;
  the email worker expands it later, outside web requests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import (
    EmailAutomation,
    EmailAutomationEnrollment,
    EmailAutomationEvent,
    EmailAutomationStep,
    EmailMessage,
    Subscriber,
)
from ...models.newsletter import AUTOMATION_STATUSES, AUTOMATION_TRIGGERS
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import config
from .queue import enqueue
from .render import build_email, validate_email_blocks
from .segments import get_segment, resolve

TRIGGER_LABELS = {
    "subscription_confirmed": "A subscriber confirms their subscription",
    "lead_magnet_claimed": "A subscriber claims a free resource",
    "article_published": "An article is published for the first time",
    "product_published": "A product is published for the first time",
    "inactive": "A subscriber has not engaged for a number of days",
}
MAX_STEPS = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _active(trigger: str) -> list[EmailAutomation]:
    return list(
        db.session.scalars(
            select(EmailAutomation).where(
                EmailAutomation.trigger == trigger, EmailAutomation.status == "active"
            )
        )
    )


def _eligible(automation: EmailAutomation, subscriber: Subscriber) -> bool:
    if not subscriber.is_marketable:
        return False
    pref = automation.required_preference
    if pref and pref not in (subscriber.preferences or []):
        return False
    from .subscribers import suppression_for

    if suppression_for(subscriber.email) is not None:
        return False
    if automation.segment_id:
        rules = get_segment(automation.segment_id).rules
        return subscriber.id in {s.id for s in resolve(rules)}
    return True


def enroll(
    automation: EmailAutomation,
    subscriber: Subscriber,
    context_key: str = "",
    context: dict[str, Any] | None = None,
    *,
    check: bool = True,
) -> EmailAutomationEnrollment | None:
    if not automation.steps or (check and not _eligible(automation, subscriber)):
        return None
    exists = db.session.scalar(
        select(EmailAutomationEnrollment.id).where(
            EmailAutomationEnrollment.automation_id == automation.id,
            EmailAutomationEnrollment.subscriber_id == subscriber.id,
            EmailAutomationEnrollment.context_key == context_key,
        )
    )
    if exists:
        return None
    first = automation.steps[0]
    enrollment = EmailAutomationEnrollment(
        automation_id=automation.id,
        subscriber_id=subscriber.id,
        context_key=context_key[:120],
        context=context or {},
        status="active",
        next_position=first.position,
        next_run_at=_now() + timedelta(minutes=first.delay_minutes),
    )
    db.session.add(enrollment)
    return enrollment


def on_confirmed(subscriber: Subscriber) -> None:
    """Called inside the confirmation request: enrols only this subscriber (no sending)."""
    for automation in _active("subscription_confirmed"):
        enroll(automation, subscriber, "confirmed")
    if subscriber.source == "lead_magnet" and subscriber.source_detail:
        on_lead_magnet_claimed(subscriber, subscriber.source_detail)


def on_lead_magnet_claimed(subscriber: Subscriber, slug: str) -> None:
    for automation in _active("lead_magnet_claimed"):
        wanted = (automation.settings or {}).get("lead_magnet")
        if wanted and wanted != slug:
            continue
        enroll(automation, subscriber, f"lead_magnet:{slug}", {"lead_magnet": slug})


def record_event(trigger: str, context_key: str, context: dict[str, Any]) -> None:
    """Record a content trigger once (e.g. first publication of an article)."""
    exists = db.session.scalar(
        select(EmailAutomationEvent.id).where(
            EmailAutomationEvent.trigger == trigger, EmailAutomationEvent.context_key == context_key
        )
    )
    if not exists:
        db.session.add(
            EmailAutomationEvent(trigger=trigger, context_key=context_key, context=context)
        )


# ---- worker side ------------------------------------------------------------------------


def process_events(limit: int = 20) -> int:
    processed = 0
    for event in db.session.scalars(
        select(EmailAutomationEvent)
        .where(EmailAutomationEvent.status == "pending")
        .order_by(EmailAutomationEvent.id)
        .limit(limit)
    ):
        automations = _active(event.trigger)
        enrolled = 0
        for automation in automations:
            rules = get_segment(automation.segment_id).rules if automation.segment_id else []
            for subscriber in resolve(rules, required_preference=automation.required_preference):
                if enroll(automation, subscriber, event.context_key, event.context, check=False):
                    enrolled += 1
        event.status = "processed" if automations else "skipped"
        event.enrolled_count = enrolled
        event.processed_at = _now()
        processed += 1
        db.session.commit()
    return processed


def process_inactive(limit: int = 500) -> int:
    enrolled = 0
    for automation in _active("inactive"):
        days = int((automation.settings or {}).get("inactive_days") or 180)
        cutoff = _now() - timedelta(days=days)
        rules = get_segment(automation.segment_id).rules if automation.segment_id else []
        for subscriber in resolve(rules, required_preference=automation.required_preference):
            engaged = _aware(subscriber.last_engaged_at or subscriber.confirmed_at)
            if engaged is None or engaged > cutoff:
                continue
            key = f"inactive:{engaged.date().isoformat()}"
            if enroll(automation, subscriber, key, {"since": engaged.isoformat()}, check=False):
                enrolled += 1
                if enrolled >= limit:
                    break
    db.session.commit()
    return enrolled


def _exit_reason(enrollment: EmailAutomationEnrollment) -> str | None:
    subscriber, automation = enrollment.subscriber, enrollment.automation
    if not subscriber.is_marketable:
        return "no_longer_subscribed"
    from .subscribers import suppression_for

    if suppression_for(subscriber.email) is not None:
        return "suppressed"
    pref = automation.required_preference
    if pref and pref not in (subscriber.preferences or []):
        return "preference_removed"
    exit_tag = (automation.settings or {}).get("exit_tag")
    if exit_tag and any(t.slug == exit_tag for t in subscriber.tags):
        return "exit_tag"
    if automation.trigger == "inactive":
        engaged = _aware(subscriber.last_engaged_at)
        if engaged is not None and engaged > _aware(enrollment.enrolled_at):
            return "engaged"
    return None


def _render_step(
    step: EmailAutomationStep, enrollment: EmailAutomationEnrollment
) -> dict[str, str]:
    context = enrollment.context or {}
    return build_email(
        subject=step.subject,
        preheader=step.preheader,
        blocks=step.blocks,
        article_ids=[context["article_id"]] if context.get("article_id") else [],
        product_ids=[context["product_id"]] if context.get("product_id") else [],
    )


def process_due(limit: int = 200) -> int:
    queued = 0
    for enrollment in db.session.scalars(
        select(EmailAutomationEnrollment)
        .where(
            EmailAutomationEnrollment.status == "active",
            EmailAutomationEnrollment.next_run_at <= _now(),
        )
        .order_by(EmailAutomationEnrollment.next_run_at)
        .limit(limit)
    ):
        automation = enrollment.automation
        if automation.status != "active":
            continue  # paused or back in draft: resume later
        reason = _exit_reason(enrollment)
        if reason:
            enrollment.status, enrollment.exit_reason = "exited", reason
            enrollment.finished_at = _now()
            continue
        steps = {s.position: s for s in automation.steps}
        step = steps.get(enrollment.next_position)
        if step is None:
            enrollment.status, enrollment.finished_at = "completed", _now()
            continue
        rendered = _render_step(step, enrollment)
        if enqueue(
            kind="automation",
            to=enrollment.subscriber.email,
            subscriber=enrollment.subscriber,
            enrollment_id=enrollment.id,
            dedupe_key=f"automation:{enrollment.id}:{step.position}",
            **rendered,
        ):
            queued += 1
        later = sorted(p for p in steps if p > step.position)
        if later:
            enrollment.next_position = later[0]
            enrollment.next_run_at = _now() + timedelta(minutes=steps[later[0]].delay_minutes)
        else:
            enrollment.status, enrollment.finished_at = "completed", _now()
            enrollment.next_run_at = None
    db.session.commit()
    return queued


# ---- admin ------------------------------------------------------------------------------


def step_dict(s: EmailAutomationStep) -> dict[str, Any]:
    return {
        "id": s.id,
        "position": s.position,
        "delay_minutes": s.delay_minutes,
        "subject": s.subject,
        "preheader": s.preheader,
        "blocks": s.blocks,
    }


def automation_dict(a: EmailAutomation, *, detail: bool = False) -> dict[str, Any]:
    counts = dict(
        db.session.execute(
            select(EmailAutomationEnrollment.status, func.count())
            .where(EmailAutomationEnrollment.automation_id == a.id)
            .group_by(EmailAutomationEnrollment.status)
        ).all()
    )
    data = {
        "id": a.id,
        "key": a.key,
        "name": a.name,
        "description": a.description,
        "trigger": a.trigger,
        "trigger_label": TRIGGER_LABELS.get(a.trigger, a.trigger),
        "status": a.status,
        "segment_id": a.segment_id,
        "required_preference": a.required_preference,
        "settings": a.settings or {},
        "step_count": len(a.steps),
        "enrollments": counts,
        "updated_at": iso(a.updated_at),
    }
    if detail:
        data["steps"] = [step_dict(s) for s in a.steps]
        message_counts = dict(
            db.session.execute(
                select(EmailMessage.status, func.count())
                .join(
                    EmailAutomationEnrollment,
                    EmailMessage.enrollment_id == EmailAutomationEnrollment.id,
                )
                .where(EmailAutomationEnrollment.automation_id == a.id)
                .group_by(EmailMessage.status)
            ).all()
        )
        data["messages"] = message_counts
        recent = db.session.scalars(
            select(EmailAutomationEnrollment)
            .where(EmailAutomationEnrollment.automation_id == a.id)
            .order_by(EmailAutomationEnrollment.enrolled_at.desc())
            .limit(25)
        )
        data["recent_enrollments"] = [
            {
                "id": e.id,
                "subscriber_id": e.subscriber_id,
                "email": e.subscriber.email,
                "status": e.status,
                "next_position": e.next_position,
                "next_run_at": iso(e.next_run_at),
                "enrolled_at": iso(e.enrolled_at),
                "exit_reason": e.exit_reason or None,
            }
            for e in recent
        ]
    return data


def list_automations() -> list[dict[str, Any]]:
    return [
        automation_dict(a)
        for a in db.session.scalars(select(EmailAutomation).order_by(EmailAutomation.id))
    ]


def get_automation(automation_id: int) -> EmailAutomation:
    automation = db.session.get(EmailAutomation, automation_id)
    if automation is None:
        raise NotFoundError()
    return automation


def update_automation(automation: EmailAutomation, data: dict[str, Any], actor) -> EmailAutomation:
    allowed = {"name", "description", "status", "segment_id", "required_preference", "settings"}
    unknown = set(data) - allowed
    if unknown:
        raise ValidationError(details={k: ["Unknown field."] for k in unknown})
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name or len(name) > 120 or any(c in name for c in "<>"):
            raise ValidationError(details={"name": ["A plain-text name up to 120 characters."]})
        automation.name = name
    if "description" in data:
        automation.description = str(data["description"] or "")[:400]
    if "segment_id" in data:
        automation.segment_id = (
            get_segment(int(data["segment_id"])).id if data["segment_id"] else None
        )
    if "required_preference" in data:
        pref = data["required_preference"] or ""
        if pref and pref not in config.PREFERENCES:
            raise ValidationError(details={"required_preference": ["Unknown preference."]})
        if automation.trigger == "product_published" and pref != "products":
            raise ValidationError(
                details={
                    "required_preference": [
                        "Product announcements go only to subscribers who chose product news."
                    ]
                }
            )
        automation.required_preference = pref
    if "settings" in data:
        settings = data["settings"] or {}
        if not isinstance(settings, dict) or set(settings) - {
            "inactive_days",
            "exit_tag",
            "lead_magnet",
        }:
            raise ValidationError(details={"settings": ["Unknown setting."]})
        days = settings.get("inactive_days")
        if days is not None and (not isinstance(days, int) or not 30 <= days <= 1095):
            raise ValidationError(details={"settings": ["Inactive days must be 30–1095."]})
        automation.settings = settings
    if "status" in data:
        status = data["status"]
        if status not in AUTOMATION_STATUSES:
            raise ValidationError(details={"status": ["Unknown status."]})
        if status == "active":
            if not automation.steps:
                raise ValidationError(details={"status": ["Add at least one email first."]})
            from .campaigns import GUIDANCE

            for step in automation.steps:
                text = " ".join(
                    str(v) for b in step.blocks for v in b.values() if isinstance(v, str)
                )
                if GUIDANCE.search(f"{step.subject} {step.preheader} {text}"):
                    raise ValidationError(
                        details={
                            "status": [
                                f"Replace the [bracketed guidance] in email {step.position}."
                            ]
                        }
                    )
        automation.status = status
    automation.updated_by_id = actor.id
    audit_service.record(
        "email_automation.updated",
        "email_automation",
        automation.id,
        actor=actor,
        details={"fields": sorted(data)},
    )
    return automation


def replace_steps(automation: EmailAutomation, steps: Any, actor) -> EmailAutomation:
    if automation.status == "active":
        raise ConflictError("Pause the automation before changing its emails.")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValidationError(details={"steps": [f"Add between 1 and {MAX_STEPS} emails."]})
    clean = []
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValidationError(details={"steps": [f"Email {i} is invalid."]})
        delay = step.get("delay_minutes", 0)
        if not isinstance(delay, int) or isinstance(delay, bool) or not 0 <= delay <= 60 * 24 * 90:
            raise ValidationError(details={"steps": [f"Email {i}: delay must be 0–90 days."]})
        subject = str(step.get("subject") or "").strip()
        if not subject or len(subject) > 200 or "<" in subject:
            raise ValidationError(details={"steps": [f"Email {i}: add a plain-text subject."]})
        clean.append(
            EmailAutomationStep(
                position=i,
                delay_minutes=delay,
                subject=subject,
                preheader=str(step.get("preheader") or "")[:200],
                blocks=validate_email_blocks(step.get("blocks") or []),
            )
        )
    automation.steps.clear()
    db.session.flush()
    automation.steps.extend(clean)
    automation.updated_by_id = actor.id
    audit_service.record(
        "email_automation.steps_replaced", "email_automation", automation.id, actor=actor
    )
    return automation


def triggers() -> list[dict[str, str]]:
    return [{"key": k, "label": TRIGGER_LABELS[k]} for k in AUTOMATION_TRIGGERS]
