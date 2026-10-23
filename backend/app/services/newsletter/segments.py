"""Segments: validated rules over appropriately collected data, always ANDed with consent.

Every audience starts from marketable subscribers only (subscribed, confirmed, not
suppressed). Rules can then narrow it by signup source, preferences, explicit interests,
tags, confirmation/consent dates, legitimate engagement (confirming, updating preferences,
claiming resources: no open or click tracking) and purchased products. Purchase targeting
never adds anyone: it only narrows the already-consenting audience.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...extensions import db
from ...models import (
    Customer,
    EmailSuppression,
    Entitlement,
    Subscriber,
    SubscriberSegment,
    SubscriberTag,
)
from ...models.newsletter import SIGNUP_SOURCES
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ..serializers import iso
from . import config, tokens

FIELDS = {
    "source": ("in", "not_in"),
    "preference": ("has", "not_has"),
    "interest": ("has", "not_has"),
    "tag": ("has", "not_has"),
    "confirmed": ("after", "before"),
    "consent": ("after", "before"),
    "engaged": ("within_days", "not_within_days"),
    "purchased_product": ("has", "not_has"),
}
MAX_RULES = 12


def _date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError(
            details={"rules": [f"{label}: use a date like 2026-10-01."]}
        ) from None


def validate_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValidationError(details={"rules": [f"Send up to {MAX_RULES} rules."]})
    clean = []
    for i, rule in enumerate(rules):
        label = f"Rule {i + 1}"
        if not isinstance(rule, dict) or set(rule) - {"field", "op", "value"}:
            raise ValidationError(details={"rules": [f"{label} is invalid."]})
        field, op, value = rule.get("field"), rule.get("op"), rule.get("value")
        if field not in FIELDS or op not in FIELDS[field]:
            raise ValidationError(details={"rules": [f"{label}: unknown field or operator."]})
        if field == "source":
            if not isinstance(value, list) or not value or set(value) - set(SIGNUP_SOURCES):
                raise ValidationError(details={"rules": [f"{label}: choose signup sources."]})
        elif field == "preference":
            if value not in config.PREFERENCES:
                raise ValidationError(details={"rules": [f"{label}: unknown preference."]})
        elif field in ("interest", "tag"):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9-]{1,60}", value):
                raise ValidationError(details={"rules": [f"{label}: use a slug."]})
            if field == "tag" and not db.session.scalar(
                select(SubscriberTag.id).where(SubscriberTag.slug == value)
            ):
                raise ValidationError(details={"rules": [f"{label}: unknown tag."]})
        elif field in ("confirmed", "consent"):
            value = _date(value, label).isoformat()
        elif field == "engaged":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 3650:
                raise ValidationError(details={"rules": [f"{label}: days between 1 and 3650."]})
        elif field == "purchased_product" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise ValidationError(details={"rules": [f"{label}: choose a product."]})
        clean.append({"field": field, "op": op, "value": value})
    return clean


def _suppressed_hashes() -> set[str]:
    return set(db.session.scalars(select(EmailSuppression.email_hash)))


def _start(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def resolve(rules: list[dict[str, Any]], *, required_preference: str = "") -> list[Subscriber]:
    """Marketable subscribers matching every rule, in id order."""
    query = select(Subscriber).where(
        Subscriber.status == "subscribed", Subscriber.confirmed_at.is_not(None)
    )
    python_rules = []
    for rule in rules:
        field, op, value = rule["field"], rule["op"], rule["value"]
        if field == "source":
            cond = Subscriber.source.in_(value)
            query = query.where(cond if op == "in" else ~cond)
        elif field == "tag":
            cond = Subscriber.tags.any(SubscriberTag.slug == value)
            query = query.where(cond if op == "has" else ~cond)
        elif field in ("confirmed", "consent"):
            column = Subscriber.confirmed_at if field == "confirmed" else Subscriber.consent_at
            boundary = _start(value)
            query = query.where(column >= boundary if op == "after" else column < boundary)
        elif field == "purchased_product":
            buyers = (
                select(func.lower(Customer.email))
                .join(Entitlement, Entitlement.customer_id == Customer.id)
                .where(Entitlement.product_id == value, Entitlement.status == "active")
            )
            cond = Subscriber.email.in_(buyers)
            query = query.where(cond if op == "has" else ~cond)
        else:
            python_rules.append(rule)
    suppressed = _suppressed_hashes()
    now = datetime.now(UTC)
    out = []
    for subscriber in db.session.scalars(query.order_by(Subscriber.id)):
        if tokens.email_hash(subscriber.email) in suppressed:
            continue
        prefs = set(subscriber.preferences or [])
        if required_preference and required_preference not in prefs:
            continue
        keep = True
        for rule in python_rules:
            field, op, value = rule["field"], rule["op"], rule["value"]
            if field == "preference":
                hit = value in prefs
            elif field == "interest":
                hit = value in (subscriber.interests or [])
            else:  # engaged
                engaged = _aware(subscriber.last_engaged_at or subscriber.confirmed_at)
                hit = engaged is not None and now - engaged <= timedelta(days=value)
            if hit != (op in ("has", "within_days")):
                keep = False
                break
        if keep:
            out.append(subscriber)
    return out


def resolve_ids(rules: list[dict[str, Any]]) -> list[int]:
    return [s.id for s in resolve(rules)]


def matches(subscriber: Subscriber, rules: list[dict[str, Any]]) -> bool:
    return subscriber.id in {s.id for s in resolve(rules)} if rules else subscriber.is_marketable


def segment_dict(segment: SubscriberSegment, *, with_count: bool = True) -> dict[str, Any]:
    return {
        "id": segment.id,
        "slug": segment.slug,
        "name": segment.name,
        "description": segment.description,
        "rules": segment.rules,
        "count": len(resolve(segment.rules)) if with_count else None,
        "updated_at": iso(segment.updated_at),
    }


def list_segments() -> list[dict[str, Any]]:
    return [
        segment_dict(s)
        for s in db.session.scalars(select(SubscriberSegment).order_by(SubscriberSegment.name))
    ]


def get_segment(segment_id: int) -> SubscriberSegment:
    segment = db.session.get(SubscriberSegment, segment_id)
    if segment is None:
        raise NotFoundError()
    return segment


def save_segment(data: dict[str, Any], actor, segment: SubscriberSegment | None = None):
    name = str(data.get("name") or (segment.name if segment else "")).strip()
    if not name or len(name) > 120 or any(c in name for c in "<>"):
        raise ValidationError(details={"name": ["A plain-text name up to 120 characters."]})
    slug = re.sub(r"[^a-z0-9]+", "-", str(data.get("slug") or name).lower()).strip("-")[:60]
    clash = db.session.scalar(select(SubscriberSegment).where(SubscriberSegment.slug == slug))
    if clash is not None and clash is not segment:
        raise ConflictError("A segment with this name already exists.")
    segment = segment or SubscriberSegment(created_by_id=actor.id)
    segment.name, segment.slug = name, slug
    segment.description = str(data.get("description") or segment.description or "")[:300]
    if "rules" in data or not segment.rules:
        segment.rules = validate_rules(data.get("rules") or [])
    db.session.add(segment)
    return segment


def delete_segment(segment: SubscriberSegment) -> None:
    from ...models import Campaign, EmailAutomation

    used = db.session.scalar(
        select(func.count()).select_from(Campaign).where(Campaign.segment_id == segment.id)
    ) or db.session.scalar(
        select(func.count())
        .select_from(EmailAutomation)
        .where(EmailAutomation.segment_id == segment.id)
    )
    if used:
        raise ConflictError("This segment is used by a campaign or automation.")
    db.session.delete(segment)
