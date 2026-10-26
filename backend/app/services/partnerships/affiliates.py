"""Affiliate programs, links, privacy-friendly click counts and reported commissions.

- Links redirect only to their stored, validated https destination (no open redirect:
  the request can never choose where it goes).
- Clicks are counted per link, day and source page; no IPs, cookies or identifiers.
- Commissions come only from network imports or clearly labelled manual entries.
  Clicks are never turned into earnings.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select, update

from ...auth.permissions import Permission as P
from ...auth.rbac import has_permissions
from ...commerce.currency import CURRENCIES, parse_major
from ...extensions import db
from ...models import (
    AffiliateClickDaily,
    AffiliateCommission,
    AffiliateLink,
    AffiliateProgram,
    Article,
    Product,
    SiteSetting,
)
from ...models.partnerships import AFFILIATE_ACCOUNT_STATUSES, COMMISSION_STATUSES
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common

DISCLOSURE_KEY = "affiliates.disclosure_text"
DEFAULT_DISCLOSURE = (
    "This page contains affiliate links. We may earn a commission if you purchase through "
    "them, at no additional cost to you."
)
MIN_DISCLOSURE = 40


# ---- disclosure ---------------------------------------------------------------------------


def disclosure_text() -> str:
    record = db.session.get(SiteSetting, DISCLOSURE_KEY)
    value = record.value if record is not None and isinstance(record.value, str) else ""
    return value if len(value.strip()) >= MIN_DISCLOSURE else DEFAULT_DISCLOSURE


def set_disclosure(value: Any, actor) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) < MIN_DISCLOSURE or len(text) > 400 or "<" in text:
        raise ValidationError(
            details={
                "disclosure_text": [
                    f"Write a clear plain-text disclosure ({MIN_DISCLOSURE}–400 characters)."
                ]
            }
        )
    if "commission" not in text.lower() and "affiliate" not in text.lower():
        raise ValidationError(
            details={
                "disclosure_text": [
                    "Say that these are affiliate links or that we may earn a commission."
                ]
            }
        )
    record = db.session.get(SiteSetting, DISCLOSURE_KEY) or SiteSetting(key=DISCLOSURE_KEY)
    record.value, record.updated_by_id = text, actor.id
    db.session.add(record)
    audit_service.record("affiliates.disclosure_updated", "affiliates", actor=actor)
    from ..publication_service import record_public_change

    record_public_change("settings", "affiliates", "affiliate_disclosure_changed", actor)
    return text


# ---- programs -----------------------------------------------------------------------------


def program_dict(p: AffiliateProgram, user) -> dict[str, Any]:
    private = has_permissions(user, P.AFFILIATES_MANAGE)
    return {
        "id": p.id,
        "name": p.name,
        "merchant": p.merchant,
        "network": p.network,
        "website": p.website,
        "category": p.category,
        "commission_model": p.commission_model,
        "commission_rate": p.commission_rate,
        "currency": p.currency,
        "payout_threshold_minor": p.payout_threshold_minor,
        "account_status": p.account_status,
        "account_identifier": p.account_identifier if private else None,
        "notes": p.notes if private else None,
        "terms_url": p.terms_url,
        "last_verified_on": p.last_verified_on.isoformat() if p.last_verified_on else None,
        "updated_at": iso(p.updated_at),
    }


def list_programs(user) -> list[dict[str, Any]]:
    return [
        program_dict(p, user)
        for p in db.session.scalars(select(AffiliateProgram).order_by(AffiliateProgram.name))
    ]


def get_program(program_id: int) -> AffiliateProgram:
    program = db.session.get(AffiliateProgram, program_id)
    if program is None:
        raise NotFoundError()
    return program


def save_program(
    data: dict[str, Any], actor, program: AffiliateProgram | None = None
) -> AffiliateProgram:
    creating = program is None
    program = program or AffiliateProgram(account_status="not_applied")
    if "name" in data or creating:
        program.name = common.text(data, "name", 160, required=True)
    if "merchant" in data or creating:
        program.merchant = common.text(data, "merchant", 160, required=True)
    for field, limit in (
        ("network", 120),
        ("category", 120),
        ("commission_model", 80),
        ("commission_rate", 60),
        ("account_identifier", 200),
    ):
        if field in data:
            setattr(program, field, common.text(data, field, limit))
    if "notes" in data:
        program.notes = common.text(data, "notes", 10000)
    for field in ("website", "terms_url"):
        if field in data:
            setattr(program, field, common.safe_https_url(data[field], field))
    if "currency" in data or creating:
        program.currency = common.currency(data)
    if "payout_threshold_minor" in data:
        program.payout_threshold_minor = common.money(data, "payout_threshold_minor")
    if "account_status" in data:
        program.account_status = common.choice(data, "account_status", AFFILIATE_ACCOUNT_STATUSES)
    if "last_verified_on" in data:
        program.last_verified_on = common.parse_date(data, "last_verified_on")
    db.session.add(program)
    db.session.flush()
    audit_service.record(
        "affiliate_program.saved",
        "affiliate_program",
        program.id,
        actor=actor,
        details={"fields": sorted(k for k in data if k not in ("account_identifier", "notes"))},
    )
    return program


# ---- links --------------------------------------------------------------------------------


def link_dict(link: AffiliateLink) -> dict[str, Any]:
    clicks = db.session.scalar(
        select(func.coalesce(func.sum(AffiliateClickDaily.clicks), 0)).where(
            AffiliateClickDaily.link_id == link.id
        )
    )
    return {
        "id": link.id,
        "slug": link.slug,
        "name": link.name,
        "program_id": link.program_id,
        "program": link.program.name if link.program else None,
        "merchant": link.merchant,
        "target_url": link.target_url,
        "campaign": link.campaign,
        "article_id": link.article_id,
        "product_id": link.product_id,
        "utm_source": link.utm_source,
        "utm_medium": link.utm_medium,
        "utm_campaign": link.utm_campaign,
        "disclosure_required": link.disclosure_required,
        "is_active": link.is_active,
        "expires_at": iso(link.expires_at),
        "public_url": f"/api/v1/go/{link.slug}",
        "total_clicks": int(clicks or 0),
    }


def list_links(args: dict[str, Any]) -> list[dict[str, Any]]:
    query = select(AffiliateLink)
    if args.get("program_id"):
        query = query.where(AffiliateLink.program_id == int(args["program_id"]))
    if args.get("active") in ("1", "true"):
        query = query.where(AffiliateLink.is_active.is_(True))
    return [link_dict(link) for link in db.session.scalars(query.order_by(AffiliateLink.name))]


def get_link(link_id: int) -> AffiliateLink:
    link = db.session.get(AffiliateLink, link_id)
    if link is None:
        raise NotFoundError()
    return link


def _utm(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if text and not re.fullmatch(r"[A-Za-z0-9_.\-]{1,80}", text):
        raise ValidationError(
            details={field: ["Use letters, numbers, dots, dashes or underscores."]}
        )
    return text


def save_link(data: dict[str, Any], actor, link: AffiliateLink | None = None) -> AffiliateLink:
    creating = link is None
    link = link or AffiliateLink(disclosure_required=True, is_active=True)
    if "name" in data or creating:
        link.name = common.text(data, "name", 160, required=True)
    if "slug" in data or creating:
        slug = re.sub(r"[^a-z0-9]+", "-", str(data.get("slug") or link.name).lower()).strip("-")[
            :80
        ]
        clash = db.session.scalar(select(AffiliateLink).where(AffiliateLink.slug == slug))
        if not slug or (clash is not None and clash is not link):
            raise ValidationError(details={"slug": ["Choose a unique short name."]})
        link.slug = slug
    if "target_url" in data or creating:
        link.target_url = common.safe_https_url(data.get("target_url"), "target_url", required=True)
    if "program_id" in data:
        link.program_id = get_program(int(data["program_id"])).id if data["program_id"] else None
    for field, limit in (("merchant", 160), ("campaign", 120)):
        if field in data:
            setattr(link, field, common.text(data, field, limit))
    for field in ("utm_source", "utm_medium", "utm_campaign"):
        if field in data:
            setattr(link, field, _utm(data[field], field))
    if "article_id" in data:
        if data["article_id"] and db.session.get(Article, data["article_id"]) is None:
            raise ValidationError(details={"article_id": ["Unknown article."]})
        link.article_id = data["article_id"] or None
    if "product_id" in data:
        if data["product_id"] and db.session.get(Product, data["product_id"]) is None:
            raise ValidationError(details={"product_id": ["Unknown product."]})
        link.product_id = data["product_id"] or None
    if "is_active" in data:
        link.is_active = data["is_active"] is not False
    if "expires_at" in data:
        link.expires_at = common.parse_datetime(data, "expires_at")
    # Affiliate links always carry a disclosure; it can't be switched off.
    link.disclosure_required = True
    db.session.add(link)
    db.session.flush()
    audit_service.record(
        "affiliate_link.saved",
        "affiliate_link",
        link.id,
        actor=actor,
        details={"fields": sorted(data)},
    )
    return link


def is_live(link: AffiliateLink, now: datetime | None = None) -> bool:
    now = now or common.now()
    return link.is_active and (link.expires_at is None or common.aware(link.expires_at) > now)


def destination(link: AffiliateLink) -> str:
    """Stored target plus UTM tags (re-validated on every use)."""
    url = common.safe_https_url(link.target_url, "target_url", required=True)
    extra = {
        k: v
        for k, v in (
            ("utm_source", link.utm_source),
            ("utm_medium", link.utm_medium),
            ("utm_campaign", link.utm_campaign),
        )
        if v
    }
    if not extra:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(extra)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _source_path(value: str | None) -> str:
    path = str(value or "")
    if not path.startswith("/") or path.startswith("//") or len(path) > 300:
        return ""
    return re.sub(r"[^\w/\-.]", "", path.split("?", 1)[0].split("#", 1)[0])


def follow(slug: str, source: str | None) -> str | None:
    """Count the click (aggregated) and return the destination, or None if unavailable."""
    link = (
        db.session.scalar(select(AffiliateLink).where(AffiliateLink.slug == slug))
        if len(slug) <= 80
        else None
    )
    if link is None or not is_live(link):
        return None
    try:
        url = destination(link)
    except ValidationError:
        return None
    day, path = datetime.now(UTC).date(), _source_path(source)
    updated = db.session.execute(
        update(AffiliateClickDaily)
        .where(
            AffiliateClickDaily.link_id == link.id,
            AffiliateClickDaily.day == day,
            AffiliateClickDaily.source_path == path,
        )
        .values(clicks=AffiliateClickDaily.clicks + 1)
    ).rowcount
    if not updated:
        db.session.add(AffiliateClickDaily(link_id=link.id, day=day, source_path=path, clicks=1))
    return url


def public_links(ids: list[int]) -> list[dict[str, Any]]:
    """Live links for page sections: always routed through the redirect, marked sponsored."""
    if not ids:
        return []
    rows = {
        link.id: link
        for link in db.session.scalars(select(AffiliateLink).where(AffiliateLink.id.in_(ids)))
    }
    return [
        {
            "id": link.id,
            "name": link.name,
            "merchant": link.merchant,
            "href": f"/api/v1/go/{link.slug}",
            "sponsored": True,
        }
        for i in ids
        if (link := rows.get(i)) and is_live(link)
    ]


def click_report(args: dict[str, Any]) -> list[dict[str, Any]]:
    query = (
        select(
            AffiliateClickDaily.link_id,
            AffiliateLink.name,
            AffiliateLink.campaign,
            AffiliateProgram.name,
            AffiliateClickDaily.source_path,
            AffiliateClickDaily.day,
            func.sum(AffiliateClickDaily.clicks),
        )
        .join(AffiliateLink, AffiliateLink.id == AffiliateClickDaily.link_id)
        .join(AffiliateProgram, AffiliateProgram.id == AffiliateLink.program_id, isouter=True)
        .group_by(
            AffiliateClickDaily.link_id,
            AffiliateLink.name,
            AffiliateLink.campaign,
            AffiliateProgram.name,
            AffiliateClickDaily.source_path,
            AffiliateClickDaily.day,
        )
        .order_by(AffiliateClickDaily.day.desc())
        .limit(2000)
    )
    if args.get("date_from"):
        query = query.where(AffiliateClickDaily.day >= common.parse_date(args, "date_from"))
    if args.get("date_to"):
        query = query.where(AffiliateClickDaily.day <= common.parse_date(args, "date_to"))
    return [
        {
            "link_id": r[0],
            "link": r[1],
            "campaign": r[2],
            "program": r[3],
            "source_path": r[4] or None,
            "day": r[5].isoformat(),
            "clicks": int(r[6]),
        }
        for r in db.session.execute(query).all()
    ]


# ---- commissions --------------------------------------------------------------------------


def commission_dict(c: AffiliateCommission) -> dict[str, Any]:
    return {
        "id": c.id,
        "program_id": c.program_id,
        "program": c.program.name,
        "link_id": c.link_id,
        "external_reference": c.external_reference,
        "occurred_on": c.occurred_on.isoformat(),
        "amount_minor": c.amount_minor,
        "currency": c.currency,
        "status": c.status,
        "source": c.source,
        "import_batch": c.import_batch,
        "notes": c.notes,
    }


def list_commissions(args: dict[str, Any]) -> list[dict[str, Any]]:
    query = select(AffiliateCommission)
    for key, column in (
        ("program_id", AffiliateCommission.program_id),
        ("status", AffiliateCommission.status),
        ("currency", AffiliateCommission.currency),
    ):
        if args.get(key):
            query = query.where(column == (int(args[key]) if key == "program_id" else args[key]))
    return [
        commission_dict(c)
        for c in db.session.scalars(
            query.order_by(AffiliateCommission.occurred_on.desc()).limit(1000)
        )
    ]


def add_manual_commission(data: dict[str, Any], actor) -> AffiliateCommission:
    program = get_program(int(data.get("program_id") or 0))
    reference = common.text(data, "external_reference", 160, required=True)
    if db.session.scalar(
        select(AffiliateCommission.id).where(
            AffiliateCommission.program_id == program.id,
            AffiliateCommission.external_reference == reference,
        )
    ):
        raise ConflictError("A commission with this reference already exists for this program.")
    record = AffiliateCommission(
        program_id=program.id,
        external_reference=reference,
        occurred_on=common.parse_date(data, "occurred_on", required=True),
        amount_minor=common.money(data, "amount_minor", required=True),
        currency=common.currency(data, default=program.currency),
        status=common.choice(data, "status", COMMISSION_STATUSES, "reported"),
        source="manual",
        notes=common.text(data, "notes", 600, required=True),  # explain the evidence
        entered_by_id=actor.id,
    )
    db.session.add(record)
    db.session.flush()
    audit_service.record(
        "affiliate_commission.manual", "affiliate_commission", record.id, actor=actor
    )
    return record


def update_commission_status(commission_id: int, status: Any, actor) -> AffiliateCommission:
    record = db.session.get(AffiliateCommission, commission_id)
    if record is None:
        raise NotFoundError()
    record.status = common.choice({"status": status}, "status", COMMISSION_STATUSES)
    audit_service.record(
        "affiliate_commission.status",
        "affiliate_commission",
        record.id,
        actor=actor,
        details={"status": record.status},
    )
    return record


def import_commissions(content: Any, data: dict[str, Any], actor) -> dict[str, Any]:
    """CSV columns: reference, date, amount (major units, e.g. 12.50), currency, status
    (optional), link (optional slug). Duplicates (same program + reference) are skipped."""
    program = get_program(int(data.get("program_id") or 0))
    if not isinstance(content, str) or len(content) > 2_000_000:
        raise ValidationError(details={"file": ["Upload a CSV file up to 2 MB."]})
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
    fields = {f.strip().lower() for f in reader.fieldnames or []}
    missing = {"reference", "date", "amount", "currency"} - fields
    if missing:
        raise ValidationError(
            details={"file": [f"Missing column(s): {', '.join(sorted(missing))}."]}
        )
    batch = f"import-{datetime.now(UTC):%Y%m%d%H%M%S}"
    seen: set[str] = set()
    result = {"imported": 0, "duplicates": 0, "invalid": 0, "errors": []}
    links = {link.slug: link.id for link in db.session.scalars(select(AffiliateLink))}
    for line, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        reference = row.get("reference", "")[:160]
        try:
            occurred = date.fromisoformat(row.get("date", "")[:10])
            code = row.get("currency", "").upper()
            if code not in CURRENCIES:
                raise ValueError("unsupported currency")
            amount = parse_major(row.get("amount", ""), code)
            if amount < 0 or not reference:
                raise ValueError("amount or reference")
            status = row.get("status") or "reported"
            if status not in COMMISSION_STATUSES:
                raise ValueError("status")
        except (ValueError, InvalidOperation, ValidationError) as err:
            result["invalid"] += 1
            if len(result["errors"]) < 20:
                result["errors"].append(f"Line {line}: {err}")
            continue
        if reference in seen or db.session.scalar(
            select(AffiliateCommission.id).where(
                AffiliateCommission.program_id == program.id,
                AffiliateCommission.external_reference == reference,
            )
        ):
            result["duplicates"] += 1
            continue
        seen.add(reference)
        db.session.add(
            AffiliateCommission(
                program_id=program.id,
                link_id=links.get(row.get("link", "")),
                external_reference=reference,
                occurred_on=occurred,
                amount_minor=amount,
                currency=code,
                status=status,
                source="import",
                import_batch=batch,
                entered_by_id=actor.id,
            )
        )
        result["imported"] += 1
    db.session.flush()
    audit_service.record(
        "affiliate_commissions.imported",
        "affiliate_program",
        program.id,
        actor=actor,
        details={k: v for k, v in result.items() if k != "errors"} | {"batch": batch},
    )
    return {**result, "batch": batch}


_ = Decimal  # parse_major uses Decimal; kept for clarity of the import contract
