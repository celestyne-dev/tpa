"""Shared validation and history helpers for the partnership modules."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from flask import current_app

from ...auth.permissions import Permission as P
from ...auth.rbac import has_permissions
from ...commerce.currency import is_supported
from ...extensions import db
from ...models import CommercialEvent
from ...utils.errors import ValidationError

EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[A-Za-z]{2,}$")


def now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def text(data: dict, field: str, limit: int, *, required: bool = False, default: str = "") -> str:
    value = data.get(field, default)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value or "")).strip()
    if required and not value:
        raise ValidationError(details={field: ["This field is required."]})
    if len(value) > limit:
        raise ValidationError(details={field: [f"Use at most {limit} characters."]})
    if "<" in value and ">" in value:
        raise ValidationError(details={field: ["HTML is not allowed. Use plain text."]})
    return value


def choice(data: dict, field: str, choices: tuple[str, ...], default: str | None = None) -> str:
    value = data.get(field, default)
    if value not in choices:
        raise ValidationError(details={field: [f"Use one of: {', '.join(choices)}."]})
    return value


def currency(data: dict, field: str = "currency", default: str = "USD") -> str:
    code = str(data.get(field) or default).upper()
    if not is_supported(code):
        raise ValidationError(details={field: ["Unsupported currency."]})
    return code


def money(data: dict, field: str, *, required: bool = False) -> int | None:
    """Integer minor units (e.g. 125000 = 1,250.00). Never converted between currencies."""
    value = data.get(field)
    if value in (None, ""):
        if required:
            raise ValidationError(details={field: ["Enter an amount."]})
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 10**13:
        raise ValidationError(details={field: ["Use a whole, non-negative amount in minor units."]})
    return value


def parse_date(data: dict, field: str, *, required: bool = False) -> date | None:
    value = data.get(field)
    if value in (None, ""):
        if required:
            raise ValidationError(details={field: ["Choose a date."]})
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValidationError(details={field: ["Use a date like 2026-11-01."]}) from None


def parse_datetime(data: dict, field: str, *, required: bool = False) -> datetime | None:
    value = data.get(field)
    if value in (None, ""):
        if required:
            raise ValidationError(details={field: ["Choose a date and time."]})
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(details={field: ["Use an ISO date and time."]}) from None
    if parsed.tzinfo is None:
        raise ValidationError(details={field: ["Include a timezone (UTC)."]})
    return parsed


def email(data: dict, field: str, *, required: bool = False) -> str:
    value = str(data.get(field) or "").strip().lower()
    if not value and not required:
        return ""
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValidationError(details={field: ["Enter a valid email address."]})
    return value


def safe_https_url(value: Any, field: str, *, required: bool = False) -> str:
    """Validated external https URL. Rejects javascript:/data: and other schemes, embedded
    credentials, local/private hosts and this site's admin area (no open redirects)."""
    url = str(value or "").strip()
    if not url:
        if required:
            raise ValidationError(details={field: ["Enter an https:// address."]})
        return ""
    problem = None
    try:
        parts = urlsplit(url)
    except ValueError:
        parts = None
    if parts is None or parts.scheme.lower() != "https" or not parts.hostname:
        problem = "Use a full https:// address."
    elif parts.username or parts.password or "@" in parts.netloc:
        problem = "Addresses with embedded credentials are not allowed."
    elif len(url) > 1000 or any(c in url for c in "\x00\r\n\t <>\"'\\"):
        problem = "This address contains characters that are not allowed."
    else:
        host = parts.hostname.lower()
        if host == "localhost" or host.endswith(".localhost") or "." not in host:
            problem = "Use a public website address."
        else:
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    problem = "Use a public website address."
            except ValueError:
                pass
        site = urlsplit(current_app.config.get("SITE_URL", "")).hostname or ""
        if (
            not problem
            and site
            and host == site.lower()
            and parts.path.startswith(("/admin", "/api"))
        ):
            problem = "Links may not point at the admin area or API."
    if problem:
        raise ValidationError(details={field: [problem]})
    return url


def record_event(
    entity_type: str,
    entity_id: int,
    kind: str,
    actor=None,
    *,
    from_state: str = "",
    to_state: str = "",
    summary: str = "",
    occurred_on: date | None = None,
) -> None:
    db.session.add(
        CommercialEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            kind=kind,
            from_state=from_state,
            to_state=to_state,
            summary=summary[:2000],
            occurred_on=occurred_on,
            actor_id=actor.id if actor else None,
        )
    )


def history(entity_type: str, entity_id: int) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from ..serializers import iso

    rows = db.session.scalars(
        select(CommercialEvent)
        .where(CommercialEvent.entity_type == entity_type, CommercialEvent.entity_id == entity_id)
        .order_by(CommercialEvent.created_at.desc(), CommercialEvent.id.desc())
        .limit(200)
    )
    return [
        {
            "kind": e.kind,
            "from": e.from_state or None,
            "to": e.to_state or None,
            "summary": e.summary,
            "occurred_on": e.occurred_on.isoformat() if e.occurred_on else None,
            "actor_id": e.actor_id,
            "at": iso(e.created_at),
        }
        for e in rows
    ]


def can_see_money(user) -> bool:
    """Commercial values are hidden from roles that only review content."""
    return any(
        has_permissions(user, perm)
        for perm in (
            P.PARTNERSHIPS_MANAGE,
            P.PARTNERSHIP_FINANCE_VIEW,
            P.ADVERTISING_MANAGE_BOOKINGS,
            P.SPONSORSHIPS_MANAGE,
        )
    )
