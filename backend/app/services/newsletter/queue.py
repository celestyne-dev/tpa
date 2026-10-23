"""The email outbox: queueing, claiming, sending, retries and provider feedback.

Run by ``flask newsletter worker`` (its own process, separate from site builds); never by
web requests in a loop.

Guarantees:
- **Idempotency.** Every message has a unique ``dedupe_key`` (e.g. campaign + subscriber),
  so re-queueing a campaign or re-running an automation cannot create duplicates.
- **Claims.** A worker claims a message with a conditional UPDATE (queued -> sending), so
  two workers never send the same message.
- **Safe restart.** A claimed message whose worker died *before* the send started goes
  back to the queue. One whose send had started but was never recorded is marked
  ``unknown`` and is **not** retried automatically, because the provider may already have
  accepted it (better a visible gap than a duplicate email).
- **Retries.** Transient failures back off exponentially up to NEWSLETTER_MAX_ATTEMPTS.
- **Rate limit.** At most NEWSLETTER_SEND_RATE_PER_MINUTE attempts in any 60 seconds,
  counted in the database (safe with several workers).
- **Suppression and consent** are re-checked immediately before every send.
- **Honest statuses.** A provider hand-off is ``accepted``; ``delivered``, ``bounced``
  and ``complained`` come only from signed provider feedback.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select, update

from ...extensions import db
from ...models import Campaign, EmailMessage, Subscriber
from . import config, tokens
from .providers import OutgoingEmail, PermanentSendError, TransientSendError, get_provider
from .render import personalise

MARKETING_KINDS = ("campaign", "automation")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def enqueue(
    *,
    kind: str,
    to: str,
    dedupe_key: str,
    subscriber: Subscriber | None = None,
    campaign: Campaign | None = None,
    enrollment_id: int | None = None,
    subject: str = "",
    html: str = "",
    text: str = "",
) -> EmailMessage | None:
    """Queue a message once. Returns None when the dedupe key already exists."""
    exists = db.session.scalar(select(EmailMessage.id).where(EmailMessage.dedupe_key == dedupe_key))
    if exists:
        return None
    message = EmailMessage(
        kind=kind,
        dedupe_key=dedupe_key[:160],
        to_email=to,
        subscriber_id=subscriber.id if subscriber else None,
        campaign_id=campaign.id if campaign else None,
        enrollment_id=enrollment_id,
        subject=subject[:200],
        html=html,
        text=text,
        send_mode=config.sending_mode(),
        status="queued",
        next_attempt_at=_now(),
    )
    db.session.add(message)
    return message


def recover_stale() -> dict[str, int]:
    minutes = current_app.config["NEWSLETTER_STALE_CLAIM_MINUTES"]
    cutoff = _now() - timedelta(minutes=minutes)
    requeued = db.session.execute(
        update(EmailMessage)
        .where(
            EmailMessage.status == "sending",
            EmailMessage.claimed_at < cutoff,
            EmailMessage.attempt_started_at.is_(None),
        )
        .values(status="queued", claimed_at=None, claimed_by="")
    ).rowcount
    unknown = db.session.execute(
        update(EmailMessage)
        .where(
            EmailMessage.status == "sending",
            EmailMessage.claimed_at < cutoff,
            EmailMessage.attempt_started_at.is_not(None),
        )
        .values(
            status="unknown",
            finished_at=_now(),
            error="The worker stopped while sending; not retried automatically to avoid "
            "a duplicate. Retry it manually if needed.",
        )
    ).rowcount
    db.session.commit()
    return {"requeued": requeued or 0, "unknown": unknown or 0}


def _recent_attempts() -> int:
    since = _now() - timedelta(seconds=60)
    return (
        db.session.scalar(
            select(func.count())
            .select_from(EmailMessage)
            .where(EmailMessage.attempt_started_at >= since)
        )
        or 0
    )


def claim(limit: int, worker: str) -> list[EmailMessage]:
    ids = list(
        db.session.scalars(
            select(EmailMessage.id)
            .where(EmailMessage.status == "queued", EmailMessage.next_attempt_at <= _now())
            .order_by(EmailMessage.next_attempt_at, EmailMessage.id)
            .limit(limit)
        )
    )
    claimed = []
    for message_id in ids:
        won = db.session.execute(
            update(EmailMessage)
            .where(EmailMessage.id == message_id, EmailMessage.status == "queued")
            .values(status="sending", claimed_at=_now(), claimed_by=worker, attempt_started_at=None)
        ).rowcount
        if won:
            claimed.append(message_id)
    db.session.commit()
    if not claimed:
        return []
    return list(db.session.scalars(select(EmailMessage).where(EmailMessage.id.in_(claimed))))


def _finish(message: EmailMessage, status: str, error: str = "") -> None:
    message.status = status
    message.error = error[:300]
    message.finished_at = _now()
    message.claimed_at = None


def _blocked_reason(message: EmailMessage) -> str | None:
    """Re-check consent and suppression right before sending."""
    from .subscribers import suppression_for

    suppression = suppression_for(message.to_email)
    subscriber = (
        db.session.get(Subscriber, message.subscriber_id) if message.subscriber_id else None
    )
    if message.kind in MARKETING_KINDS:
        if subscriber is None or not subscriber.is_marketable:
            return "Recipient is no longer subscribed."
        if suppression is not None:
            return f"Address is suppressed ({suppression.reason})."
    elif message.kind == "confirmation":
        if subscriber is None or subscriber.status != "pending":
            return "Confirmation no longer needed."
        if suppression is not None and suppression.reason not in ("unsubscribed", "erased"):
            return f"Address is suppressed ({suppression.reason})."
    elif suppression is not None and suppression.reason in ("bounced", "complained", "manual"):
        return f"Address is suppressed ({suppression.reason})."
    return None


def _build(message: EmailMessage) -> OutgoingEmail:
    from .subscribers import manage_url, one_click_url

    subscriber = (
        db.session.get(Subscriber, message.subscriber_id) if message.subscriber_id else None
    )
    from_name, from_email = config.from_address()
    reply_to = config.get_settings()["email.reply_to"] or ""
    headers: dict[str, str] = {}
    if message.kind == "campaign":
        campaign = db.session.get(Campaign, message.campaign_id)
        snapshot = campaign.snapshot or {}
        rendered = {k: snapshot[k] for k in ("subject", "html", "text")}
        from_name = snapshot.get("from_name") or from_name
        reply_to = snapshot.get("reply_to") or reply_to
        campaign_id = campaign.public_id
    else:
        rendered = {"subject": message.subject, "html": message.html, "text": message.text}
        campaign_id = ""
    if message.kind in MARKETING_KINDS and subscriber is not None:
        one_click = one_click_url(subscriber, campaign_id)
        rendered = personalise(
            rendered,
            first_name=subscriber.first_name,
            unsubscribe_url=manage_url(subscriber, "unsubscribe"),
            preferences_url=manage_url(subscriber),
        )
        domain = from_email.rsplit("@", 1)[-1] if "@" in from_email else "localhost"
        headers = {
            "List-Unsubscribe": f"<{one_click}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "List-Id": f"The Positive Reset <positive-reset.{domain}>",
        }
    else:
        rendered = personalise(rendered, first_name=subscriber.first_name if subscriber else "")
    return OutgoingEmail(
        to=message.to_email,
        subject=rendered["subject"],
        html=rendered["html"],
        text=rendered["text"],
        from_name=from_name,
        from_email=from_email,
        reply_to=reply_to,
        headers=headers,
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(60 * (2 ** max(0, attempts - 1)), 6 * 3600))


def deliver(message: EmailMessage, provider, mode: str) -> str:
    """Send one claimed message. Commits the outcome. Returns the new status."""
    reason = _blocked_reason(message)
    if reason:
        _finish(message, "suppressed", reason)
        db.session.commit()
        return message.status
    if mode == "test" and not config.is_test_recipient(message.to_email):
        _finish(message, "skipped", "Test mode: only test recipients receive email.")
        db.session.commit()
        return message.status
    if not config.from_address()[1]:
        message.status, message.claimed_at = "queued", None
        message.next_attempt_at = _now() + timedelta(minutes=10)
        message.error = "No sender address configured (NEWSLETTER_FROM_EMAIL)."
        db.session.commit()
        return message.status
    outgoing = _build(message)
    # Recorded before the provider call: if the worker dies now, the message becomes
    # "unknown" instead of being sent twice.
    message.attempts += 1
    message.attempt_started_at = _now()
    message.provider = provider.name
    db.session.commit()
    try:
        message_id = provider.send(outgoing)
    except TransientSendError as err:
        if message.attempts >= current_app.config["NEWSLETTER_MAX_ATTEMPTS"]:
            _finish(message, "failed", f"Gave up after {message.attempts} attempts: {err}")
        else:
            message.status = "queued"
            message.claimed_at = None
            message.attempt_started_at = None
            message.error = str(err)[:300]
            message.next_attempt_at = _now() + _backoff(message.attempts)
    except PermanentSendError as err:
        if err.bounce:
            from .subscribers import mark_bounced

            message.bounced_at = _now()
            _finish(message, "bounced", str(err))
            mark_bounced(message.to_email, detail=str(err))
        else:
            _finish(message, "failed", str(err))
    else:
        message.provider_message_id = (message_id or "")[:255]
        message.accepted_at = _now()
        _finish(message, "accepted")
    db.session.commit()
    return message.status


def run_once(worker: str | None = None) -> dict[str, Any]:
    """One worker pass: recover stale claims, then send what the rate limit allows."""
    worker = worker or worker_id()
    result: dict[str, Any] = {"sent": 0, "statuses": {}}
    result.update(recover_stale())
    mode = config.sending_mode()
    if mode == "disabled":
        result["paused"] = "Sending mode is disabled."
        return result
    budget = current_app.config["NEWSLETTER_SEND_RATE_PER_MINUTE"] - _recent_attempts()
    limit = min(current_app.config["NEWSLETTER_BATCH_SIZE"], max(0, budget))
    if limit <= 0:
        result["paused"] = "Rate limit reached for this minute."
        return result
    messages = claim(limit, worker)
    if not messages:
        return result
    provider = get_provider()
    try:
        for message in messages:
            try:
                status = deliver(message, provider, mode)
            except TransientSendError as err:  # e.g. connection failure in provider.open()
                db.session.rollback()
                message = db.session.get(EmailMessage, message.id)
                message.status, message.claimed_at, message.attempt_started_at = (
                    "queued",
                    None,
                    None,
                )
                message.error = str(err)[:300]
                message.next_attempt_at = _now() + timedelta(minutes=5)
                db.session.commit()
                status = "queued"
            result["statuses"][status] = result["statuses"].get(status, 0) + 1
            result["sent"] += 1
    finally:
        provider.close()
    return result


def retry_message(message: EmailMessage) -> None:
    if message.status not in ("unknown", "failed"):
        from ...utils.errors import ConflictError

        raise ConflictError("Only failed or unknown messages can be retried.")
    message.status = "queued"
    message.error = ""
    message.next_attempt_at = _now()
    message.claimed_at = None
    message.attempt_started_at = None
    message.finished_at = None


# ---- provider feedback ------------------------------------------------------------------


def process_feedback(events: list[dict[str, Any]]) -> dict[str, int]:
    """Apply normalised provider events: {type: delivered|bounced|complained,
    message_id?: str, email?: str, bounce_type?: hard|soft, detail?: str}."""
    from .subscribers import mark_bounced

    counts = {"delivered": 0, "bounced": 0, "complained": 0, "ignored": 0}
    for item in events[:500]:
        if not isinstance(item, dict):
            counts["ignored"] += 1
            continue
        kind = item.get("type")
        message = None
        if item.get("message_id"):
            message = db.session.scalar(
                select(EmailMessage).where(
                    EmailMessage.provider_message_id == str(item["message_id"]).strip("<>")[:255]
                )
            )
        email = tokens.normalise_email(
            str(item.get("email") or (message.to_email if message else ""))
        )
        detail = str(item.get("detail") or "")[:200]
        if kind == "delivered" and message is not None:
            if message.status in ("accepted", "sending"):
                message.status = "delivered"
            message.delivered_at = _now()
            counts["delivered"] += 1
        elif kind == "bounced" and email:
            hard = item.get("bounce_type", "hard") != "soft"
            if message is not None:
                message.bounced_at = _now()
                if hard:
                    message.status = "bounced"
                message.error = (f"{'Hard' if hard else 'Soft'} bounce. {detail}")[:300]
            if hard:
                mark_bounced(email, detail=detail)
            counts["bounced"] += 1
        elif kind == "complained" and email:
            if message is not None:
                message.complained_at = _now()
                message.status = "complained"
            mark_bounced(email, complaint=True, detail=detail)
            counts["complained"] += 1
        else:
            counts["ignored"] += 1
    return counts
