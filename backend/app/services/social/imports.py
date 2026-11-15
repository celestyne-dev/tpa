"""Importing the connected Instagram account's own images into the Media Library.

Only media listed by the account's own ``/me/media`` (and re-checked by id at import time)
can be imported, and the administrator must confirm the image is the account's own and
suitable for TPA. The file is downloaded once (https, Meta CDN hosts only, no redirects,
size and type checked) and processed like any upload, so published pages are served from
TPA's own storage, never from Instagram's expiring CDN addresses. The caption, permalink
and account are kept as the image's caption, source and credit.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from flask import current_app
from sqlalchemy import select

from ...extensions import db
from ...models import MediaAsset, SocialImport, User
from ...utils.errors import ConflictError, ValidationError
from .. import audit_service
from ..admin import media_admin
from ..serializers import iso
from . import accounts, http, instagram
from .http import SocialError

SUPPORTED = ("IMAGE",)


def _account_token():
    try:
        return accounts.access_token("instagram")
    except SocialError as exc:
        db.session.commit()
        raise ValidationError(exc.message, details={"setup": ["reconnect"]}) from None


def _imported() -> dict[str, SocialImport]:
    rows = db.session.scalars(select(SocialImport).where(SocialImport.platform == "instagram"))
    return {row.external_id: row for row in rows}


def list_media(after: str | None) -> dict[str, Any]:
    account, token = _account_token()
    try:
        page = instagram.media(token, after=after)
    except SocialError as exc:
        accounts.mark_failure("instagram", exc)
        db.session.commit()
        raise ValidationError(exc.message) from None
    imported = _imported()
    items = []
    for item in page["items"]:
        media_id = str(item.get("id") or "")
        if not media_id:
            continue
        media_type = str(item.get("media_type") or "")
        row = imported.get(media_id)
        items.append(
            {
                "id": media_id,
                "media_type": media_type,
                "supported": media_type in SUPPORTED,
                # Preview only (Instagram CDN, expires): never stored or used on public pages.
                "preview_url": item.get("media_url") if media_type in SUPPORTED else None,
                "caption": item.get("caption") or "",
                "permalink": item.get("permalink"),
                "timestamp": item.get("timestamp"),
                "username": item.get("username") or account.username,
                "imported": row is not None,
                "media_asset_id": row.media_asset_id if row else None,
            }
        )
    return {"items": items, "after": page["after"], "username": account.username}


def _first_line(text: str, limit: int) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_markup(text: str) -> str:
    """Captions are kept as plain text: no control characters, no tag-like markup."""
    return _CONTROL.sub("", text).replace("<", "‹").replace(">", "›")


def import_media(data: dict[str, Any], user: User) -> tuple[MediaAsset, bool]:
    media_id = str(data.get("external_id") or "").strip()
    if not media_id.isdigit() or len(media_id) > 40:
        raise ValidationError(details={"external_id": ["Choose an Instagram post."]})
    if data.get("ownership_confirmed") is not True:
        raise ValidationError(
            "Confirm the image is your account's own and suitable for TPA before importing.",
            details={"ownership_confirmed": ["Required."]},
        )
    alt_text = str(data.get("alt_text") or "").strip()
    if not alt_text:
        raise ValidationError(details={"alt_text": ["Describe the image for screen readers."]})
    existing = db.session.scalar(
        select(SocialImport).where(
            SocialImport.platform == "instagram", SocialImport.external_id == media_id
        )
    )
    if existing is not None:
        raise ConflictError(
            "This Instagram image has already been imported.",
            details={"media_asset_id": existing.media_asset_id},
        )
    account, token = _account_token()
    try:
        item = instagram.media_item(token, media_id)
    except SocialError as exc:
        raise ValidationError(
            f"The post could not be loaded from Instagram: {exc.message}"
        ) from None
    # Ownership: the media must belong to the connected account.
    if str(item.get("id") or "") != media_id or (
        item.get("username") and account.username and item["username"] != account.username
    ):
        raise ValidationError("Only the connected account's own posts can be imported.")
    if item.get("media_type") not in SUPPORTED:
        raise ValidationError("Only single-image posts can be imported (not videos or albums).")
    try:
        content, _ = http.download_image(
            str(item.get("media_url") or ""), current_app.config["SOCIAL_IMPORT_MAX_BYTES"]
        )
    except SocialError as exc:
        raise ValidationError(f"The image could not be imported: {exc.message}") from None
    caption = _strip_markup((item.get("caption") or "").strip())
    username = item.get("username") or account.username or ""
    permalink = item.get("permalink")
    if not (isinstance(permalink, str) and permalink.startswith("https://www.instagram.com/")):
        permalink = None
    meta = {
        "alt_text": alt_text[:300],
        "title": _first_line(caption, 200) or f"Instagram post {media_id}",
        "caption": caption[:500],
        "credit": f"@{username} on Instagram"[:200] if username else "Instagram",
        "source_url": permalink,
        "category": data.get("category") or "general",
        "filename": f"instagram-{username or 'post'}-{media_id}",
    }
    written = media_admin.Written()
    try:
        asset, created = media_admin.upload(
            content, f"instagram-{media_id}.jpg", meta, user, written
        )
        taken = None
        try:
            taken = datetime.fromisoformat(str(item.get("timestamp")).replace("+0000", "+00:00"))
        except ValueError:
            taken = None
        db.session.add(
            SocialImport(
                platform="instagram",
                external_id=media_id,
                media_asset_id=asset.id,
                permalink=permalink,
                caption=caption or None,
                username=username or None,
                taken_at=taken,
                ownership_confirmed=True,
                imported_by_id=user.id,
            )
        )
        db.session.flush()
        audit_service.record(
            "social.instagram_imported", "media", asset.id, actor=user,
            details={"external_id": media_id, "permalink": permalink, "duplicate": not created},
        )  # fmt: skip
        db.session.commit()
    except Exception:
        db.session.rollback()
        written.cleanup()
        raise
    return asset, created


def import_dict(row: SocialImport) -> dict[str, Any]:
    return {
        "external_id": row.external_id,
        "media_asset_id": row.media_asset_id,
        "permalink": row.permalink,
        "username": row.username,
        "imported_at": iso(row.imported_at),
    }
