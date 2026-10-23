"""The one subscriber service behind every signup form, preference page and admin action.

Rules this module enforces:
- Consent is explicit and recorded (time, wording, version, hashed IP, source). It is
  never inferred from a customer account or a purchase.
- Double opt-in: new and returning subscribers are ``pending`` until they click the
  confirmation link; only ``subscribed`` + confirmed subscribers receive marketing.
- Public responses never reveal whether an address is subscribed (no enumeration).
- Unsubscribing is immediate, audited and adds the address to the suppression list;
  bounces and complaints suppress permanently.
- Imported contacts are ``quarantined`` (never mailed) unless consent evidence is attested.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, or_, select

from ...extensions import db
from ...models import (
    EmailMessage,
    EmailSuppression,
    Subscriber,
    SubscriberEvent,
    SubscriberTag,
)
from ...models.newsletter import SIGNUP_SOURCES, SUBSCRIBER_STATUSES
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import config, tokens

EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[A-Za-z]{2,}$")
CONFIRM_RESEND_MINUTES = 10
NOTICE_INTERVAL_HOURS = 24
# Suppression reasons a fresh, double opt-in signup may lift (the person chose to return).
LIFTABLE = ("unsubscribed", "erased")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def clean_email(value: Any, field: str = "email") -> str:
    email = tokens.normalise_email(str(value or ""))
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError(details={field: ["Enter a valid email address."]})
    return email


def _clean_name(value: Any) -> str:
    name = re.sub(r"[\x00-\x1f<>]", "", str(value or "")).strip()
    if len(name) > 80:
        raise ValidationError(details={"first_name": ["Use at most 80 characters."]})
    return name


def clean_preferences(value: Any) -> list[str]:
    if value is None:
        return list(config.DEFAULT_PREFERENCES)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError(details={"preferences": ["Choose from the listed options."]})
    unknown = [v for v in value if v not in config.PREFERENCES]
    if unknown:
        raise ValidationError(details={"preferences": ["Choose from the listed options."]})
    return list(dict.fromkeys(value))


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'•' * max(1, min(len(local) - 1, 6))}@{domain}"


def event(subscriber: Subscriber, name: str, actor=None, **details) -> None:
    db.session.add(
        SubscriberEvent(
            subscriber_id=subscriber.id,
            event=name,
            details=details,
            actor_id=actor.id if actor else None,
        )
    )


# ---- suppression ------------------------------------------------------------------------


def suppression_for(email: str) -> EmailSuppression | None:
    return db.session.scalar(
        select(EmailSuppression).where(EmailSuppression.email_hash == tokens.email_hash(email))
    )


def suppress(email: str, reason: str, *, source: str = "", note: str = "", actor=None) -> None:
    record = suppression_for(email)
    if record is None:
        db.session.add(
            EmailSuppression(
                email_hash=tokens.email_hash(email),
                reason=reason,
                source=source[:60],
                note=note[:300],
                created_by_id=actor.id if actor else None,
            )
        )
    elif record.reason in LIFTABLE and reason not in LIFTABLE:
        # A bounce or complaint is stronger than an earlier unsubscribe.
        record.reason, record.source, record.note = reason, source[:60], note[:300]


def lift_suppression(email: str) -> None:
    record = suppression_for(email)
    if record is not None and record.reason in LIFTABLE:
        db.session.delete(record)


def cancel_pending_mail(
    subscriber: Subscriber, kinds: tuple[str, ...] = ("campaign", "automation")
):
    db.session.execute(
        EmailMessage.__table__.update()
        .where(
            EmailMessage.subscriber_id == subscriber.id,
            EmailMessage.status == "queued",
            EmailMessage.kind.in_(kinds),
        )
        .values(status="cancelled", error="Recipient unsubscribed.", finished_at=_now())
    )


def _exit_enrollments(subscriber: Subscriber, reason: str) -> None:
    from ...models import EmailAutomationEnrollment

    db.session.execute(
        EmailAutomationEnrollment.__table__.update()
        .where(
            EmailAutomationEnrollment.subscriber_id == subscriber.id,
            EmailAutomationEnrollment.status == "active",
        )
        .values(status="exited", exit_reason=reason, finished_at=_now())
    )


# ---- links and transactional mail -------------------------------------------------------


def manage_url(subscriber: Subscriber, page: str = "preferences") -> str:
    return f"{config_site()}/newsletter/{page}#token={tokens.manage_token(subscriber)}"


def one_click_url(subscriber: Subscriber, campaign_public_id: str = "") -> str:
    extra = f"&c={campaign_public_id}" if campaign_public_id else ""
    return (
        f"{config_site()}/api/v1/newsletter/unsubscribe/one-click"
        f"?token={tokens.manage_token(subscriber)}{extra}"
    )


def config_site() -> str:
    return current_app.config["SITE_URL"].rstrip("/")


def _queue_transactional(subscriber: Subscriber, kind: str, rendered: dict[str, str]) -> None:
    from .queue import enqueue

    enqueue(
        kind=kind,
        to=subscriber.email,
        subscriber=subscriber,
        subject=rendered["subject"],
        html=rendered["html"],
        text=rendered["text"],
        dedupe_key=f"{kind}:{subscriber.id}:{secrets.token_hex(8)}",
    )


def send_confirmation(subscriber: Subscriber) -> None:
    from .render import simple_email

    link = f"{config_site()}/newsletter/confirm#token={tokens.confirm_token(subscriber)}"
    hours = current_app.config["NEWSLETTER_CONFIRM_TTL_HOURS"]
    rendered = simple_email(
        f"Please confirm your subscription to {config.NEWSLETTER_NAME}",
        [
            f"Hello {subscriber.first_name or 'there'},",
            f"Someone (hopefully you) asked to receive {config.NEWSLETTER_NAME} at this address. "
            "Please confirm with the button below. Nothing will be sent until you do.",
            f"This link works for {hours} hours. If you didn't ask for this, simply ignore this "
            "email and you won't hear from us again.",
        ],
        ("Confirm my subscription", link),
        reason="You are receiving this one-time message because this address was entered in "
        "a Think Positive Always signup form.",
    )
    _queue_transactional(subscriber, "confirmation", rendered)
    subscriber.confirmation_sent_at = _now()


def _send_already_subscribed_notice(subscriber: Subscriber) -> None:
    from .render import simple_email

    rendered = simple_email(
        f"You're already subscribed to {config.NEWSLETTER_NAME}",
        [
            f"Hello {subscriber.first_name or 'there'},",
            "Someone entered this address in a signup form, but you're already on the list, so "
            "nothing has changed. You can update what you receive below.",
        ],
        ("Manage my preferences", manage_url(subscriber)),
        reason="You are receiving this one-time notice because this address was entered in a "
        "Think Positive Always signup form.",
    )
    _queue_transactional(subscriber, "notice", rendered)
    subscriber.notice_sent_at = _now()


# ---- public signup ----------------------------------------------------------------------


def _recent(value: datetime | None, delta: timedelta) -> bool:
    value = _aware(value)
    return value is not None and _now() - value < delta


def subscribe(
    data: dict[str, Any], *, ip: str | None = None, source_default: str = "other"
) -> Subscriber | None:
    """Public signup. Always ends in the same public response; returns the subscriber (or
    None when the request was dropped as spam or suppressed) for internal callers."""
    if not config.signup_open():
        raise ConflictError("Newsletter sign-ups are not open yet.")
    # Spam protection: a hidden field people never fill, and a minimum fill time.
    if str(data.get("website") or "").strip():
        return None
    try:
        elapsed = int(data.get("elapsed_ms") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    if 0 < elapsed < 1200:
        return None
    email = clean_email(data.get("email"))
    if data.get("consent") is not True:
        raise ValidationError(
            details={"consent": ["Please tick the box to agree to receive emails."]}
        )
    settings = config.get_settings()
    shown_version = data.get("consent_version")
    if shown_version is not None and shown_version != settings["email.consent_version"]:
        raise ConflictError(
            "Our consent wording has just been updated. Please review it and try again.",
            details={"code": "consent_changed"},
        )
    source = data.get("source") or source_default
    if source not in SIGNUP_SOURCES or source in ("import", "admin"):
        source = "other"
    first_name = _clean_name(data.get("first_name"))
    preferences = clean_preferences(data.get("preferences"))
    source_detail = re.sub(r"[^\w/\-.:]", "", str(data.get("source_detail") or ""))[:200]

    suppression = suppression_for(email)
    if suppression is not None and suppression.reason not in LIFTABLE:
        return None  # bounced / complained / blocked: never mailed again
    subscriber = db.session.scalar(select(Subscriber).where(Subscriber.email == email))
    consent = {
        "consent_at": _now(),
        "consent_text": settings["email.consent_text"],
        "consent_version": settings["email.consent_version"],
        "consent_ip_hash": tokens.ip_hash(ip),
    }
    if subscriber is None:
        subscriber = Subscriber(
            public_id=secrets.token_hex(12),
            email=email,
            first_name=first_name,
            status="pending",
            source=source,
            source_detail=source_detail,
            preferences=preferences,
            interests=[],
            **consent,
        )
        db.session.add(subscriber)
        db.session.flush()
        event(subscriber, "signup", source=source, detail=source_detail)
        send_confirmation(subscriber)
        return subscriber
    if subscriber.status in ("bounced", "complained"):
        return None
    if subscriber.status == "subscribed":
        if not _recent(subscriber.notice_sent_at, timedelta(hours=NOTICE_INTERVAL_HOURS)):
            _send_already_subscribed_notice(subscriber)
        return subscriber
    # pending, unsubscribed or quarantined: record fresh consent and ask to confirm again.
    was = subscriber.status
    for key, value in consent.items():
        setattr(subscriber, key, value)
    subscriber.status = "pending"
    subscriber.source, subscriber.source_detail = source, source_detail
    if first_name:
        subscriber.first_name = first_name
    subscriber.preferences = preferences
    event(subscriber, "resubscribe_requested" if was == "unsubscribed" else "signup", source=source)
    if not _recent(subscriber.confirmation_sent_at, timedelta(minutes=CONFIRM_RESEND_MINUTES)):
        send_confirmation(subscriber)
    return subscriber


def _by_public_id(public_id: str) -> Subscriber | None:
    return db.session.scalar(select(Subscriber).where(Subscriber.public_id == public_id))


def confirm(token: str) -> Subscriber:
    parsed = tokens.parse_confirm_token(token)
    subscriber = _by_public_id(parsed[0]) if parsed else None
    if subscriber is None or subscriber.token_version != parsed[1]:
        raise ValidationError(
            "This confirmation link is invalid or has expired. Please sign up again.",
            details={"code": "link_invalid"},
        )
    if subscriber.status == "subscribed":
        return subscriber  # idempotent
    if subscriber.status != "pending":
        raise ValidationError(
            "This confirmation link is no longer valid. Please sign up again.",
            details={"code": "link_invalid"},
        )
    suppression = suppression_for(subscriber.email)
    if suppression is not None and suppression.reason not in LIFTABLE:
        raise ValidationError(
            "This address can't be subscribed. Please contact us.", details={"code": "blocked"}
        )
    lift_suppression(subscriber.email)
    subscriber.status = "subscribed"
    subscriber.confirmed_at = _now()
    subscriber.unsubscribed_at = None
    subscriber.unsubscribe_reason = ""
    subscriber.last_engaged_at = _now()
    event(subscriber, "confirmed", consent_version=subscriber.consent_version)
    db.session.flush()
    from . import automations

    automations.on_confirmed(subscriber)
    return subscriber


def from_manage_token(token: str) -> Subscriber:
    parsed = tokens.parse_manage_token(token)
    subscriber = _by_public_id(parsed[0]) if parsed else None
    if subscriber is None or subscriber.token_version != parsed[1]:
        raise NotFoundError("This link is invalid or no longer works.")
    return subscriber


def unsubscribe(
    subscriber: Subscriber, *, reason: str = "", via: str = "link", campaign: str = "", actor=None
) -> Subscriber:
    if subscriber.status in ("unsubscribed", "bounced", "complained"):
        return subscriber
    previous = subscriber.status
    subscriber.status = "unsubscribed"
    subscriber.unsubscribed_at = _now()
    subscriber.unsubscribe_reason = re.sub(r"[\x00-\x1f<>]", "", reason or "")[:300]
    suppress(subscriber.email, "unsubscribed", source=via, actor=actor)
    cancel_pending_mail(subscriber)
    _exit_enrollments(subscriber, "unsubscribed")
    event(
        subscriber,
        "unsubscribed",
        actor=actor,
        via=via,
        previous=previous,
        campaign=campaign,
        reason=subscriber.unsubscribe_reason,
    )
    if actor is not None:
        audit_service.record(
            "subscriber.unsubscribed",
            "subscriber",
            subscriber.id,
            actor=actor,
            details={"via": via},
        )
    return subscriber


def preferences_view(subscriber: Subscriber) -> dict[str, Any]:
    return {
        "email": mask_email(subscriber.email),
        "first_name": subscriber.first_name,
        "status": "subscribed"
        if subscriber.status == "subscribed"
        else "pending"
        if subscriber.status == "pending"
        else "unsubscribed",
        "preferences": subscriber.preferences or [],
        "options": [{"key": k, "label": v} for k, v in config.PREFERENCES.items()],
    }


def update_preferences(subscriber: Subscriber, data: dict[str, Any]) -> Subscriber:
    if subscriber.status not in ("subscribed", "pending"):
        raise ConflictError("You are unsubscribed. Sign up again to receive emails.")
    prefs = clean_preferences(data.get("preferences"))
    if not prefs:
        raise ValidationError(
            details={"preferences": ["Choose at least one, or unsubscribe instead."]}
        )
    subscriber.preferences = prefs
    if "first_name" in data:
        subscriber.first_name = _clean_name(data.get("first_name"))
    subscriber.last_engaged_at = _now()
    event(subscriber, "preferences_updated", preferences=prefs)
    return subscriber


def erase(subscriber: Subscriber, *, actor=None, via: str = "self") -> None:
    """Delete personal data. The hashed address stays suppressed so it is never mailed;
    delivery records keep only an anonymised address."""
    suppress(subscriber.email, "erased", source=via, actor=actor)
    db.session.execute(
        EmailMessage.__table__.update()
        .where(EmailMessage.subscriber_id == subscriber.id)
        .values(
            to_email="erased@invalid",
            html="",
            text="",
            status=func.coalesce(func.nullif(EmailMessage.status, "queued"), "cancelled"),
        )
    )
    audit_service.record(
        "subscriber.erased", "subscriber", subscriber.id, actor=actor, details={"via": via}
    )
    db.session.delete(subscriber)


# ---- feedback (bounces and complaints) --------------------------------------------------


def mark_bounced(email: str, *, complaint: bool = False, detail: str = "") -> None:
    reason = "complained" if complaint else "bounced"
    suppress(email, reason, source="provider_feedback", note=detail)
    subscriber = db.session.scalar(select(Subscriber).where(Subscriber.email == email))
    if subscriber is not None and subscriber.status != reason:
        subscriber.status = reason
        cancel_pending_mail(subscriber, ("campaign", "automation", "notice"))
        _exit_enrollments(subscriber, reason)
        event(subscriber, reason, detail=detail[:200])


# ---- admin ------------------------------------------------------------------------------


def subscriber_dict(s: Subscriber, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": s.id,
        "email": s.email,
        "first_name": s.first_name,
        "status": s.status,
        "marketable": s.is_marketable,
        "source": s.source,
        "preferences": s.preferences or [],
        "tags": [{"slug": t.slug, "name": t.name} for t in s.tags],
        "consent_at": iso(s.consent_at),
        "confirmed_at": iso(s.confirmed_at),
        "unsubscribed_at": iso(s.unsubscribed_at),
        "created_at": iso(s.created_at),
        "last_engaged_at": iso(s.last_engaged_at),
    }
    if detail:
        data["consent"] = {
            "at": iso(s.consent_at),
            "text": s.consent_text,
            "version": s.consent_version,
            "ip_hash_recorded": bool(s.consent_ip_hash),
            "source": s.source,
            "source_detail": s.source_detail,
            "confirmation_sent_at": iso(s.confirmation_sent_at),
            "confirmed_at": iso(s.confirmed_at),
        }
        data["interests"] = s.interests or []
        data["unsubscribe_reason"] = s.unsubscribe_reason
        data["import_batch"] = s.import_batch
        data["suppressed"] = r.reason if (r := suppression_for(s.email)) else None
        events = db.session.scalars(
            select(SubscriberEvent)
            .where(SubscriberEvent.subscriber_id == s.id)
            .order_by(SubscriberEvent.created_at.desc(), SubscriberEvent.id.desc())
            .limit(100)
        )
        data["activity"] = [
            {"event": e.event, "details": e.details, "at": iso(e.created_at)} for e in events
        ]
        rows = db.session.execute(
            select(EmailMessage.status, func.count())
            .where(EmailMessage.subscriber_id == s.id)
            .group_by(EmailMessage.status)
        ).all()
        data["messages"] = dict(rows)
    return data


def _filtered(args: dict[str, Any]):
    query = select(Subscriber)
    if args.get("status"):
        if args["status"] not in SUBSCRIBER_STATUSES:
            raise ValidationError(details={"status": ["Unknown status."]})
        query = query.where(Subscriber.status == args["status"])
    if args.get("source"):
        query = query.where(Subscriber.source == args["source"])
    if args.get("tag"):
        query = query.where(Subscriber.tags.any(SubscriberTag.slug == args["tag"]))
    if args.get("q"):
        needle = f"%{args['q'].strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Subscriber.email).like(needle),
                func.lower(Subscriber.first_name).like(needle),
            )
        )
    if args.get("segment_id"):
        from .segments import get_segment, resolve_ids

        ids = resolve_ids(get_segment(int(args["segment_id"])).rules)
        query = query.where(Subscriber.id.in_(ids or [-1]))
    return query


def list_subscribers(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    query = _filtered(args)
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        query.order_by(Subscriber.created_at.desc(), Subscriber.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    counts = dict(
        db.session.execute(
            select(Subscriber.status, func.count()).group_by(Subscriber.status)
        ).all()
    )
    return [subscriber_dict(s) for s in rows], total, counts


def get_subscriber(subscriber_id: int) -> Subscriber:
    subscriber = db.session.get(Subscriber, subscriber_id)
    if subscriber is None:
        raise NotFoundError()
    return subscriber


def set_tags(subscriber: Subscriber, slugs: list[str], actor) -> Subscriber:
    if not isinstance(slugs, list) or not all(isinstance(s, str) for s in slugs):
        raise ValidationError(details={"tags": ["Send a list of tag slugs."]})
    tags = list(db.session.scalars(select(SubscriberTag).where(SubscriberTag.slug.in_(slugs))))
    missing = set(slugs) - {t.slug for t in tags}
    if missing:
        raise ValidationError(details={"tags": [f"Unknown tag(s): {', '.join(sorted(missing))}."]})
    before = sorted(t.slug for t in subscriber.tags)
    subscriber.tags = tags
    event(subscriber, "tags_changed", actor=actor, before=before, after=sorted(slugs))
    return subscriber


def bulk_tag(ids: list[int], slug: str, add: bool, actor) -> int:
    tag = db.session.scalar(select(SubscriberTag).where(SubscriberTag.slug == slug))
    if tag is None:
        raise ValidationError(details={"tag": ["Unknown tag."]})
    if not isinstance(ids, list) or len(ids) > 1000:
        raise ValidationError(details={"ids": ["Send up to 1000 subscriber ids."]})
    count = 0
    for subscriber in db.session.scalars(select(Subscriber).where(Subscriber.id.in_(ids))):
        has = tag in subscriber.tags
        if add and not has:
            subscriber.tags.append(tag)
            count += 1
        elif not add and has:
            subscriber.tags.remove(tag)
            count += 1
    audit_service.record(
        "subscribers.bulk_tag",
        "subscriber_tag",
        tag.id,
        actor=actor,
        details={"count": count, "add": add},
    )
    return count


def tag_dict(t: SubscriberTag) -> dict[str, Any]:
    count = db.session.scalar(
        select(func.count())
        .select_from(Subscriber)
        .where(Subscriber.tags.any(SubscriberTag.id == t.id))
    )
    return {
        "id": t.id,
        "slug": t.slug,
        "name": t.name,
        "description": t.description,
        "count": count,
    }


def save_tag(data: dict[str, Any], tag: SubscriberTag | None = None) -> SubscriberTag:
    name = str(data.get("name") or (tag.name if tag else "")).strip()
    if not name or len(name) > 80 or any(c in name for c in "<>"):
        raise ValidationError(details={"name": ["A plain-text name up to 80 characters."]})
    slug = re.sub(r"[^a-z0-9]+", "-", str(data.get("slug") or name).lower()).strip("-")[:60]
    if not slug:
        raise ValidationError(details={"slug": ["Enter a slug."]})
    clash = db.session.scalar(select(SubscriberTag).where(SubscriberTag.slug == slug))
    if clash is not None and clash is not tag:
        raise ConflictError("A tag with this slug already exists.")
    tag = tag or SubscriberTag()
    tag.name, tag.slug = name, slug
    tag.description = str(data.get("description") or tag.description or "")[:300]
    db.session.add(tag)
    return tag


def admin_action(subscriber: Subscriber, action: str, data: dict[str, Any], actor) -> None:
    if action == "unsubscribe":
        unsubscribe(
            subscriber,
            reason=str(data.get("reason") or "Removed by staff"),
            via="admin",
            actor=actor,
        )
    elif action == "resend-confirmation":
        if subscriber.status not in ("pending", "quarantined"):
            raise ConflictError("Only pending or quarantined subscribers can be asked to confirm.")
        if not config.signup_open() and config.sending_mode() == "disabled":
            raise ConflictError("Email sending is disabled.")
        if _recent(subscriber.confirmation_sent_at, timedelta(minutes=CONFIRM_RESEND_MINUTES)):
            raise ConflictError("A confirmation email was sent a few minutes ago.")
        if subscriber.status == "quarantined":
            # Asking an imported contact to opt in; they stay unmarketable until they click.
            subscriber.status = "pending"
        send_confirmation(subscriber)
        event(subscriber, "confirmation_resent", actor=actor)
        audit_service.record(
            "subscriber.confirmation_resent", "subscriber", subscriber.id, actor=actor
        )
    elif action == "erase":
        erase(subscriber, actor=actor, via="admin")
    else:
        raise NotFoundError()


# ---- import / export --------------------------------------------------------------------

EXPORT_COLUMNS = [
    "email",
    "first_name",
    "status",
    "source",
    "preferences",
    "tags",
    "consent_at",
    "consent_version",
    "consent_text",
    "confirmed_at",
    "unsubscribed_at",
    "created_at",
]


def export_csv(args: dict[str, Any], actor) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    count = 0
    for s in db.session.scalars(_filtered(args).order_by(Subscriber.id)):
        row = subscriber_dict(s)
        values = [
            s.email,
            s.first_name,
            s.status,
            s.source,
            " ".join(row["preferences"]),
            " ".join(t["slug"] for t in row["tags"]),
            row["consent_at"] or "",
            s.consent_version,
            s.consent_text,
            row["confirmed_at"] or "",
            row["unsubscribed_at"] or "",
            row["created_at"] or "",
        ]
        # Neutralise spreadsheet formulas.
        writer.writerow(["'" + v if v[:1] in "=+-@" else v for v in map(str, values)])
        count += 1
    audit_service.record(
        "subscribers.exported",
        "subscriber",
        actor=actor,
        details={
            "count": count,
            "filters": {k: v for k, v in args.items() if k not in ("page", "page_size")},
        },
    )
    return buffer.getvalue()


def import_csv(content: str, options: dict[str, Any], actor) -> dict[str, Any]:
    """Import contacts. Rows become ``quarantined`` (never mailed) unless the importer
    attests to recorded double opt-in consent AND the row carries a consent date."""
    if not isinstance(content, str) or len(content) > 5_000_000:
        raise ValidationError(details={"file": ["Upload a CSV file up to 5 MB."]})
    attested = options.get("consent_attested") is True
    attestation_note = str(options.get("consent_source") or "").strip()[:300]
    if attested and not attestation_note:
        raise ValidationError(
            details={"consent_source": ["Describe where and how these contacts gave consent."]}
        )
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
    if not reader.fieldnames or "email" not in [f.strip().lower() for f in reader.fieldnames]:
        raise ValidationError(details={"file": ["The CSV needs an “email” column."]})
    batch = f"import-{_now():%Y%m%d%H%M%S}"
    tag_slug = str(options.get("tag") or "").strip()
    tag = None
    if tag_slug:
        tag = db.session.scalar(select(SubscriberTag).where(SubscriberTag.slug == tag_slug))
        if tag is None:
            raise ValidationError(details={"tag": ["Unknown tag."]})
    result = {
        "created": 0,
        "existing": 0,
        "suppressed": 0,
        "invalid": 0,
        "subscribed": 0,
        "quarantined": 0,
    }
    seen: set[str] = set()
    for index, raw in enumerate(reader):
        if index >= 20000:
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            email = clean_email(row.get("email"))
        except ValidationError:
            result["invalid"] += 1
            continue
        if email in seen:
            continue
        seen.add(email)
        if suppression_for(email) is not None:
            result["suppressed"] += 1
            continue
        if db.session.scalar(select(Subscriber.id).where(Subscriber.email == email)):
            result["existing"] += 1  # never overwrite an existing consent record
            continue
        consent_at = None
        if row.get("consent_at"):
            try:
                consent_at = datetime.fromisoformat(row["consent_at"].replace("Z", "+00:00"))
                consent_at = _aware(consent_at)
            except ValueError:
                consent_at = None
        marketable = attested and consent_at is not None and consent_at <= _now()
        try:
            name = _clean_name(row.get("first_name"))
        except ValidationError:
            name = ""
        subscriber = Subscriber(
            public_id=secrets.token_hex(12),
            email=email,
            first_name=name,
            status="subscribed" if marketable else "quarantined",
            source="import",
            source_detail=batch,
            import_batch=batch,
            preferences=list(config.DEFAULT_PREFERENCES),
            interests=[],
            consent_at=consent_at if marketable else None,
            consent_text=(row.get("consent_text") or attestation_note)[:1000] if marketable else "",
            consent_version=f"import:{batch}" if marketable else "",
            confirmed_at=consent_at if marketable else None,
            last_engaged_at=consent_at if marketable else None,
        )
        if tag is not None:
            subscriber.tags = [tag]
        db.session.add(subscriber)
        db.session.flush()
        event(
            subscriber,
            "imported",
            actor=actor,
            batch=batch,
            attested=marketable,
            consent_source=attestation_note if marketable else "",
        )
        result["created"] += 1
        result["subscribed" if marketable else "quarantined"] += 1
    audit_service.record(
        "subscribers.imported",
        "subscriber",
        actor=actor,
        details={**result, "batch": batch, "attested": attested},
    )
    return {**result, "batch": batch}


def list_suppressions(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(EmailSuppression)
    if args.get("reason"):
        query = query.where(EmailSuppression.reason == args["reason"])
    if args.get("q"):
        query = query.where(EmailSuppression.email_hash == tokens.email_hash(args["q"]))
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    page, size = args.get("page", 1), args.get("page_size", 25)
    rows = db.session.scalars(
        query.order_by(EmailSuppression.created_at.desc()).offset((page - 1) * size).limit(size)
    )
    return [
        {
            "id": r.id,
            "reason": r.reason,
            "source": r.source,
            "note": r.note,
            "email_hash": r.email_hash[:12] + "…",
            "created_at": iso(r.created_at),
        }
        for r in rows
    ], total


def add_suppression(data: dict[str, Any], actor) -> None:
    email = clean_email(data.get("email"))
    suppress(email, "manual", source="admin", note=str(data.get("note") or ""), actor=actor)
    subscriber = db.session.scalar(select(Subscriber).where(Subscriber.email == email))
    if subscriber is not None and subscriber.status in ("subscribed", "pending"):
        unsubscribe(subscriber, reason="Suppressed by staff", via="admin", actor=actor)
    audit_service.record("email.suppression_added", "email", actor=actor)


def remove_suppression(suppression_id: int, actor) -> None:
    record = db.session.get(EmailSuppression, suppression_id)
    if record is None:
        raise NotFoundError()
    if record.reason != "manual":
        raise ConflictError(
            "Only manual blocks can be removed. Unsubscribes, bounces, complaints and erasures "
            "are lifted only by the person signing up again and confirming."
        )
    db.session.delete(record)
    audit_service.record("email.suppression_removed", "email", suppression_id, actor=actor)
