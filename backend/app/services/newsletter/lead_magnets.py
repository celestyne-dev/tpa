"""Lead magnets: free resources delivered by secure, expiring email links.

A lead magnet wraps a published **free product** with real private files (Batch 05), so
nothing is invented and files are streamed through the existing private download path.

- Claiming needs only an email address. Newsletter opt-in is a separate, unticked choice
  unless the lead magnet is explicitly configured as "subscription required", in which
  case its notice is shown next to the form and consent is recorded like any signup.
- The delivery link (``/resources/access#token=…``) proves control of the address. Only a
  hash of the token is stored; it expires and can carry a download limit.
- Each download goes through a short-lived signed URL, never a storage path.
- Signed-in customers can instead add the same free product to their library.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select, update

from ...extensions import db
from ...models import LeadMagnet, LeadMagnetClaim, Product, ProductFileVersion
from ...models.newsletter import LEAD_MAGNET_OPTINS, LEAD_MAGNET_STATUSES
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import config, subscribers
from .queue import enqueue
from .render import simple_email

MAX_CLAIMS_PER_DAY = 3
DOWNLOAD_URL_TTL = 300


class LinkExpired(APIError):
    status_code = 410
    code = "link_expired"
    message = "This download link has expired. Request a new one below."


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _catalogue():
    from ..commerce import catalogue

    return catalogue


def resource_state(magnet: LeadMagnet) -> dict[str, Any]:
    product = magnet.product
    catalogue = _catalogue()
    state = catalogue.readiness(product) if product else {"purchasable": False}
    files = catalogue.deliverable_files(product) if product and not product.is_bundle else []
    problems = []
    if product is None or product.pricing_model != "free":
        problems.append("Choose a free product.")
    if product is not None and product.is_bundle:
        problems.append("Bundles can't be lead magnets; choose a single free product.")
    if not files:
        problems.append("The product has no deliverable files.")
    if not state.get("purchasable"):
        problems.append("The product must be published and available.")
    return {"ready": not problems, "problems": problems, "files": files}


def magnet_dict(m: LeadMagnet, *, admin: bool = False) -> dict[str, Any]:
    state = resource_state(m)
    data = {
        "slug": m.slug,
        "title": m.title,
        "description": m.description,
        "newsletter_optin": m.newsletter_optin,
        "optin_notice": m.optin_notice,
        "available": m.status == "active" and state["ready"],
        "formats": sorted(
            {f.current_version.file_format.upper() for f in state["files"] if f.current_version}
        ),
        "product_slug": m.product.published_slug if m.product else None,
    }
    if admin:
        claims = db.session.scalar(
            select(func.count())
            .select_from(LeadMagnetClaim)
            .where(LeadMagnetClaim.lead_magnet_id == m.id)
        )
        data.update(
            {
                "id": m.id,
                "status": m.status,
                "product_id": m.product_id,
                "product_title": m.product.title if m.product else None,
                "link_ttl_hours": m.link_ttl_hours,
                "max_downloads": m.max_downloads,
                "problems": state["problems"],
                "claims": claims,
                "updated_at": iso(m.updated_at),
            }
        )
    return data


def public_info(slug: str | None) -> dict[str, Any] | None:
    if not slug:
        return None
    magnet = db.session.scalar(select(LeadMagnet).where(LeadMagnet.slug == slug))
    if magnet is None or magnet.status != "active":
        return None
    data = magnet_dict(magnet)
    return data if data["available"] else None


def options() -> list[dict[str, Any]]:
    return [
        {"value": m.slug, "label": m.title}
        for m in db.session.scalars(select(LeadMagnet).where(LeadMagnet.status != "archived"))
    ]


# ---- public claim -----------------------------------------------------------------------


def claim(slug: str, data: dict[str, Any], *, ip: str | None = None) -> None:
    magnet = db.session.scalar(select(LeadMagnet).where(LeadMagnet.slug == slug))
    if magnet is None or magnet.status != "active" or not resource_state(magnet)["ready"]:
        raise NotFoundError("This resource isn't available right now.")
    if config.sending_mode() == "disabled" or not config.backend_configured():
        raise ConflictError("Email delivery isn't available right now. Please try again later.")
    if str(data.get("website") or "").strip():
        return
    try:
        elapsed = int(data.get("elapsed_ms") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    if 0 < elapsed < 1200:
        return
    email = subscribers.clean_email(data.get("email"))
    wants_newsletter = data.get("newsletter_consent") is True
    if magnet.newsletter_optin == "required" and not wants_newsletter:
        raise ValidationError(
            details={
                "newsletter_consent": [
                    "This resource is offered to newsletter subscribers. "
                    "Tick the box to subscribe, or leave it."
                ]
            }
        )
    suppression = subscribers.suppression_for(email)
    if suppression is not None and suppression.reason in ("bounced", "complained", "manual"):
        return
    recent = db.session.scalar(
        select(func.count())
        .select_from(LeadMagnetClaim)
        .where(
            LeadMagnetClaim.lead_magnet_id == magnet.id,
            LeadMagnetClaim.email == email,
            LeadMagnetClaim.created_at >= _now() - timedelta(days=1),
        )
    )
    if recent and recent >= MAX_CLAIMS_PER_DAY:
        return  # same public response; avoids using the form to flood an inbox
    subscriber = None
    if wants_newsletter and config.signup_open():
        subscriber = subscribers.subscribe(
            {
                "email": email,
                "first_name": data.get("first_name"),
                "consent": True,
                "consent_version": data.get("consent_version"),
                "source": "lead_magnet",
                "source_detail": magnet.slug,
                "preferences": data.get("preferences"),
            },
            ip=ip,
        )
    token = secrets.token_urlsafe(32)
    ttl = magnet.link_ttl_hours or current_app.config["LEAD_MAGNET_LINK_TTL_HOURS"]
    record = LeadMagnetClaim(
        lead_magnet_id=magnet.id,
        email=email,
        subscriber_id=subscriber.id if subscriber else None,
        token_hash=_hash(token),
        expires_at=_now() + timedelta(hours=ttl),
        max_downloads=magnet.max_downloads or current_app.config["LEAD_MAGNET_MAX_DOWNLOADS"],
    )
    db.session.add(record)
    db.session.flush()
    link = f"{current_app.config['SITE_URL'].rstrip('/')}/resources/access#token={token}"
    rendered = simple_email(
        f"Your free resource: {magnet.title}",
        [
            "Hello,",
            f"Here is the link to download “{magnet.title}”, as you requested.",
            f"The link works for {ttl} hours. If it expires, you can request a new one on the "
            "same page.",
            "If you didn't request this, you can ignore this email.",
        ],
        ("Download your resource", link),
        reason="You are receiving this one-time message because this address was used to "
        "request a free resource from Think Positive Always.",
    )
    enqueue(
        kind="lead_magnet",
        to=email,
        subscriber=subscriber,
        dedupe_key=f"lead_magnet:{record.id}",
        **rendered,
    )
    if subscriber is not None and subscriber.is_marketable:
        subscriber.last_engaged_at = _now()
        from .automations import on_lead_magnet_claimed

        on_lead_magnet_claimed(subscriber, magnet.slug)


def _valid_claim(token: str) -> LeadMagnetClaim:
    record = (
        db.session.scalar(
            select(LeadMagnetClaim).where(LeadMagnetClaim.token_hash == _hash(token or ""))
        )
        if token and len(token) <= 100
        else None
    )
    if record is None:
        raise NotFoundError("This link is invalid.")
    if record.revoked_at or _aware(record.expires_at) < _now():
        raise LinkExpired(details={"slug": record.lead_magnet.slug})
    if record.max_downloads and record.download_count >= record.max_downloads:
        raise LinkExpired(
            "This link has reached its download limit. Request a new one below.",
            details={"slug": record.lead_magnet.slug},
        )
    return record


def access(token: str) -> dict[str, Any]:
    record = _valid_claim(token)
    magnet = record.lead_magnet
    files = resource_state(magnet)["files"]
    return {
        "lead_magnet": {
            "slug": magnet.slug,
            "title": magnet.title,
            "description": magnet.description,
        },
        "files": [
            {
                "id": f.public_id,
                "title": f.title,
                "description": f.description,
                "format": f.current_version.file_format.upper(),
                "size_bytes": f.current_version.size_bytes,
            }
            for f in files
            if f.current_version
        ],
        "expires_at": iso(record.expires_at),
        "downloads_remaining": (record.max_downloads - record.download_count)
        if record.max_downloads
        else None,
    }


def _sign(payload: str) -> str:
    key = hashlib.sha256(f"tpa-lead-magnet:{current_app.config['SECRET_KEY']}".encode()).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:40]


def authorize_download(token: str, file_public_id: str) -> dict[str, Any]:
    record = _valid_claim(token)
    files = {
        f.public_id: f for f in resource_state(record.lead_magnet)["files"] if f.current_version
    }
    target = files.get(str(file_public_id or ""))
    if target is None:
        raise NotFoundError("File not found.")
    won = db.session.execute(
        update(LeadMagnetClaim)
        .where(
            LeadMagnetClaim.id == record.id,
            (LeadMagnetClaim.max_downloads.is_(None))
            | (LeadMagnetClaim.download_count < LeadMagnetClaim.max_downloads),
        )
        .values(download_count=LeadMagnetClaim.download_count + 1, last_download_at=_now())
    ).rowcount
    if not won:
        raise LinkExpired(details={"slug": record.lead_magnet.slug})
    payload = f"{record.id}.{target.current_version_id}.{int(time.time()) + DOWNLOAD_URL_TTL}"
    return {
        "url": f"/api/v1/lead-magnets/download/{payload}.{_sign(payload)}",
        "expires_in": DOWNLOAD_URL_TTL,
    }


def serve(signed: str):
    from ..commerce.downloads import file_response

    parts = (signed or "").split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts[:3]):
        raise NotFoundError()
    claim_id, version_id, expires, sig = parts
    if not hmac.compare_digest(_sign(f"{claim_id}.{version_id}.{expires}"), sig):
        raise NotFoundError()
    if int(expires) < time.time():
        raise LinkExpired("This download link has expired. Open your email link again.")
    record = db.session.get(LeadMagnetClaim, int(claim_id))
    version = db.session.get(ProductFileVersion, int(version_id))
    if record is None or version is None or record.revoked_at:
        raise NotFoundError()
    return file_response(version, record.lead_magnet.slug)


# ---- admin ------------------------------------------------------------------------------


def list_magnets() -> list[dict[str, Any]]:
    return [
        magnet_dict(m, admin=True)
        for m in db.session.scalars(select(LeadMagnet).order_by(LeadMagnet.updated_at.desc()))
    ]


def get_magnet(magnet_id: int) -> LeadMagnet:
    magnet = db.session.get(LeadMagnet, magnet_id)
    if magnet is None:
        raise NotFoundError()
    return magnet


def save_magnet(data: dict[str, Any], actor, magnet: LeadMagnet | None = None) -> LeadMagnet:
    creating = magnet is None
    magnet = magnet or LeadMagnet(status="draft", newsletter_optin="optional")
    allowed = {
        "title",
        "slug",
        "description",
        "product_id",
        "status",
        "newsletter_optin",
        "optin_notice",
        "link_ttl_hours",
        "max_downloads",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValidationError(details={k: ["Unknown field."] for k in unknown})
    if "title" in data or creating:
        title = str(data.get("title") or "").strip()
        if not title or len(title) > 160 or any(c in title for c in "<>"):
            raise ValidationError(details={"title": ["A plain-text title up to 160 characters."]})
        magnet.title = title
    if "slug" in data or creating:
        slug = re.sub(r"[^a-z0-9]+", "-", str(data.get("slug") or magnet.title).lower()).strip("-")[
            :120
        ]
        clash = db.session.scalar(select(LeadMagnet).where(LeadMagnet.slug == slug))
        if not slug or (clash is not None and clash is not magnet):
            raise ValidationError(details={"slug": ["Choose a unique slug."]})
        magnet.slug = slug
    if "description" in data:
        magnet.description = str(data["description"] or "")[:600]
    if "product_id" in data or creating:
        product = db.session.get(Product, data.get("product_id") or 0)
        if product is None or product.pricing_model != "free":
            raise ValidationError(
                details={"product_id": ["Choose a free product with real files."]}
            )
        magnet.product_id = product.id
        magnet.product = product
    if "newsletter_optin" in data:
        if data["newsletter_optin"] not in LEAD_MAGNET_OPTINS:
            raise ValidationError(details={"newsletter_optin": ["Unknown option."]})
        magnet.newsletter_optin = data["newsletter_optin"]
    if "optin_notice" in data:
        magnet.optin_notice = str(data["optin_notice"] or "").strip()[:600]
    for field, low, high in (("link_ttl_hours", 1, 24 * 30), ("max_downloads", 1, 100)):
        if field in data:
            value = data[field]
            if value is not None and (not isinstance(value, int) or not low <= value <= high):
                raise ValidationError(
                    details={field: [f"Use a number from {low} to {high}, or empty."]}
                )
            setattr(magnet, field, value)
    if magnet.newsletter_optin == "required" and len(magnet.optin_notice) < 20:
        raise ValidationError(
            details={
                "optin_notice": [
                    "Explain clearly, next to the form, that this resource is offered in exchange "
                    "for subscribing (and that people can unsubscribe at any time)."
                ]
            }
        )
    if "status" in data:
        if data["status"] not in LEAD_MAGNET_STATUSES:
            raise ValidationError(details={"status": ["Unknown status."]})
        if data["status"] == "active":
            state = resource_state(magnet)
            if not state["ready"]:
                raise ValidationError(
                    "This lead magnet isn't ready.", details={"status": state["problems"]}
                )
        if magnet.status != data["status"] and magnet.id is not None:
            from ..publication_service import record_public_change

            record_public_change("lead_magnet", magnet.id, "lead_magnet_status", actor)
        magnet.status = data["status"]
    magnet.updated_by_id = actor.id
    db.session.add(magnet)
    db.session.flush()
    audit_service.record(
        "lead_magnet.saved", "lead_magnet", magnet.id, actor=actor, details={"fields": sorted(data)}
    )
    return magnet


def delete_magnet(magnet: LeadMagnet, actor) -> None:
    if db.session.scalar(
        select(func.count())
        .select_from(LeadMagnetClaim)
        .where(LeadMagnetClaim.lead_magnet_id == magnet.id)
    ):
        raise ConflictError("This resource has been claimed; archive it instead.")
    audit_service.record("lead_magnet.deleted", "lead_magnet", magnet.id, actor=actor)
    db.session.delete(magnet)
