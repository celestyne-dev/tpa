"""Media metadata (read-only listing in Batch 02; uploads arrive in Batch 03)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from ...extensions import db
from ...models import MediaAsset
from ...utils.errors import ValidationError
from ..serializers import media_dict

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    "application/pdf",
}
MAX_SIZE_BYTES = 20 * 1024 * 1024
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")


def validate_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Validate media metadata before a record is created (used by importers/uploads)."""
    errors: dict[str, list[str]] = {}
    filename = str(data.get("filename", ""))
    if not _SAFE_FILENAME.match(filename) or ".." in filename:
        errors["filename"] = ["Use a simple file name (letters, numbers, dots, dashes)."]
    mime = data.get("mime_type")
    if mime not in ALLOWED_MIME_TYPES:
        errors["mime_type"] = ["This file type is not allowed."]
    size = data.get("size_bytes", 0)
    if not isinstance(size, int) or size < 0 or size > MAX_SIZE_BYTES:
        errors["size_bytes"] = ["Files must be at most 20 MB."]
    if mime and str(mime).startswith("image/") and not str(data.get("alt_text", "")).strip():
        errors["alt_text"] = ["Images need descriptive alt text."]
    if data.get("visibility", "public") not in ("public", "private"):
        errors["visibility"] = ["Visibility must be public or private."]
    for dim in ("width", "height"):
        value = data.get(dim)
        if value is not None and (not isinstance(value, int) or not 0 < value <= 20000):
            errors[dim] = ["Must be a positive whole number."]
    if errors:
        raise ValidationError("The media metadata is invalid.", details=errors)
    return data


def list_media(images_only: bool = True) -> list[dict[str, Any]]:
    stmt = select(MediaAsset).order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
    if images_only:
        stmt = stmt.where(MediaAsset.mime_type.like("image/%"))
    return [media_dict(m) for m in db.session.scalars(stmt)]
