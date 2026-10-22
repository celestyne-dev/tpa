"""Branding: logos, favicon set and approved style presets for the public site."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageOps

from ..extensions import db
from ..models import MediaAsset
from ..storage import get_storage, public_url
from ..utils.errors import ValidationError

FAVICON_FIELD = "branding.favicon_media_id"
# name -> pixel size (favicon.ico bundles 16, 32 and 48).
FAVICON_PNGS = {
    "icon-32.png": 32,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def _prefix(asset: MediaAsset) -> str:
    return f"branding/favicon-{asset.public_id}-v{asset.version}"


def _source_bytes(asset: MediaAsset) -> bytes:
    storage = get_storage()
    if asset.original_key and storage.exists(asset.original_key, public=False):
        return storage.read(asset.original_key, public=False)
    variants = [v for v in asset.current_variants() if v.format in ("png", "jpeg", "webp")]
    if not variants:
        raise ValueError("no source")
    largest = max(variants, key=lambda v: v.width)
    return storage.read(largest.storage_key, public=True)


def generate_favicons(asset_id: int) -> dict[str, str]:
    """Create favicon.ico and app icons from a media library image (idempotent)."""
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or not asset.is_managed:
        raise ValidationError(
            details={FAVICON_FIELD: ["Choose an image uploaded to the media library."]}
        )
    if (asset.width or 0) < 180 or (asset.height or 0) < 180:
        raise ValidationError(
            details={FAVICON_FIELD: ["Use an image of at least 180×180 pixels (512×512 is ideal)."]}
        )
    storage = get_storage()
    prefix = _prefix(asset)
    if storage.exists(f"{prefix}/icon-512.png", public=True):
        return favicon_urls(asset)
    try:
        with Image.open(io.BytesIO(_source_bytes(asset))) as img:
            img = ImageOps.exif_transpose(img).convert("RGBA")
            side = min(img.size)
            square = ImageOps.fit(
                img,
                (side, side),
                Image.Resampling.LANCZOS,
                centering=(asset.focal_x, asset.focal_y),
            )
    except Exception:  # unreadable source: report a clear field error
        raise ValidationError(
            details={FAVICON_FIELD: ["This image could not be converted into a favicon."]}
        ) from None
    for name, size in FAVICON_PNGS.items():
        buf = io.BytesIO()
        square.resize((size, size), Image.Resampling.LANCZOS).save(buf, "PNG", optimize=True)
        storage.save(f"{prefix}/{name}", buf.getvalue(), public=True)
    buf = io.BytesIO()
    square.resize((48, 48), Image.Resampling.LANCZOS).save(
        buf, "ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )
    storage.save(f"{prefix}/favicon.ico", buf.getvalue(), public=True)
    return favicon_urls(asset)


def favicon_urls(asset: MediaAsset) -> dict[str, str]:
    prefix = _prefix(asset)
    return {
        "ico": public_url(f"{prefix}/favicon.ico"),
        "png32": public_url(f"{prefix}/icon-32.png"),
        "apple": public_url(f"{prefix}/apple-touch-icon.png"),
        "png192": public_url(f"{prefix}/icon-192.png"),
        "png512": public_url(f"{prefix}/icon-512.png"),
    }


def _asset(asset_id: Any) -> MediaAsset | None:
    if not isinstance(asset_id, int):
        return None
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or asset.visibility != "public" or asset.status == "archived":
        return None
    return asset


def _logo(asset_id: Any) -> dict[str, Any] | None:
    asset = _asset(asset_id)
    return asset.as_image() if asset else None


def public_branding(values: dict[str, Any]) -> dict[str, Any]:
    favicon = None
    asset = _asset(values.get(FAVICON_FIELD))
    if (
        asset is not None
        and asset.is_managed
        and get_storage().exists(f"{_prefix(asset)}/icon-512.png", public=True)
    ):
        favicon = favicon_urls(asset)
    social = _asset(values.get("branding.social_image_media_id"))
    logo = _logo(values.get("branding.logo_media_id"))
    return {
        "logo_url": values.get("branding.logo_url"),
        "logo": logo,
        "logo_alt": _logo(values.get("branding.logo_alt_media_id")) or logo,
        "show_wordmark": values.get("branding.show_wordmark", True) is not False,
        "wordmark_subline": values.get("branding.wordmark_subline") or "",
        "favicon": favicon,
        "social_image": social.as_image("social") if social else None,
        "palette": values.get("branding.palette") or "classic",
        "typography": values.get("branding.typography") or "classic",
        "button_shape": values.get("branding.button_shape") or "pill",
        "image_style": values.get("branding.image_style") or "rounded",
    }
