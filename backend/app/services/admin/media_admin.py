"""Media library: uploads, optimisation, metadata, replacement and safe removal."""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, or_, select

from ...extensions import db
from ...media import processing
from ...models import Article, Author, MediaAsset, MediaVariant, Topic, User
from ...storage import get_storage, public_url
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import is_https_url, plain_text_problem
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso, media_dict

SORTS = {
    "newest": (MediaAsset.created_at.desc(), MediaAsset.id.desc()),
    "oldest": (MediaAsset.created_at.asc(), MediaAsset.id.asc()),
    "filename": (func.lower(MediaAsset.filename).asc(), MediaAsset.id.asc()),
    "size": (MediaAsset.size_bytes.desc(), MediaAsset.id.desc()),
}


def _now() -> datetime:
    return datetime.now(UTC)


# ---- usage --------------------------------------------------------------------------


def _block_media_ids(blocks: Iterable[Any]) -> set[int]:
    ids: set[int] = set()
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("media_id"), int):
            ids.add(block["media_id"])
        for item in block.get("items") or []:
            if isinstance(item, dict) and isinstance(item.get("media_id"), int):
                ids.add(item["media_id"])
    return ids


def _deep_media_ids(value: Any) -> set[int]:
    """Any ``media_id``/``*_image_id`` integer inside JSON (page sections, future blocks)."""
    found: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key in ("media", "media_id") or key.endswith("image_id")) and isinstance(item, int):
                found.add(item)
            else:
                found |= _deep_media_ids(item)
    elif isinstance(value, list):
        for item in value:
            found |= _deep_media_ids(item)
    return found


def usage_index() -> dict[int, list[dict[str, Any]]]:
    """Where every asset is used: {asset_id: [{type, id, label, field, public}]}."""
    index: dict[int, list[dict[str, Any]]] = {}

    def add(asset_id, ref):
        if asset_id:
            index.setdefault(asset_id, []).append(ref)

    for article in db.session.scalars(select(Article)):
        public = article.status == "published"
        base = {
            "type": "article",
            "id": article.id,
            "label": article.title,
            "status": article.status,
        }
        add(article.featured_image_id, {**base, "field": "featured image", "public": public})
        add(article.social_image_id, {**base, "field": "social image", "public": public})
        for asset_id in _block_media_ids(article.body):
            add(asset_id, {**base, "field": "content", "public": public})
        pending = article.pending_changes or {}
        pending_ids = _block_media_ids(pending.get("body")) | {
            pending.get(k) for k in ("featured_image_id", "social_image_id")
        }
        for asset_id in pending_ids - {None}:
            add(asset_id, {**base, "field": "unpublished changes", "public": False})
    for author in db.session.scalars(select(Author).where(Author.profile_image_id.is_not(None))):
        add(
            author.profile_image_id,
            {
                "type": "author",
                "id": author.id,
                "label": author.display_name,
                "field": "portrait",
                "public": author.status == "active",
            },
        )
    for topic in db.session.scalars(select(Topic).where(Topic.featured_image_id.is_not(None))):
        add(
            topic.featured_image_id,
            {
                "type": "topic",
                "id": topic.id,
                "label": topic.name,
                "field": "featured image",
                "public": topic.status == "active",
            },
        )
    from ...cms.settings_registry import MEDIA_SETTINGS
    from ...models import Page, ReusableSection, SiteSetting

    for page in db.session.scalars(select(Page)):
        base = {"type": "page", "id": page.id, "label": page.title}
        add(page.social_image_id, {**base, "field": "social image (draft)", "public": False})
        for section in page.sections:
            for asset_id in _deep_media_ids(section.content):
                add(
                    asset_id,
                    {
                        **base,
                        "type": "page_section",
                        "id": section.id,
                        "label": f"{page.title}: {section.name or section.key}",
                        "field": "section (draft)",
                        "public": False,
                    },
                )
        snapshot = page.published_snapshot if page.status == "published" else None
        if snapshot:
            add(
                (snapshot.get("page") or {}).get("social_image_id"),
                {**base, "field": "social image", "public": True},
            )
            for section in snapshot.get("sections", []):
                for asset_id in _deep_media_ids(section.get("content")):
                    add(asset_id, {**base, "field": "live section", "public": True})
    for shared in db.session.scalars(select(ReusableSection)):
        for asset_id in _deep_media_ids(shared.content):
            add(
                asset_id,
                {
                    "type": "reusable_section",
                    "id": shared.id,
                    "label": shared.name,
                    "field": "shared section",
                    "public": True,
                },
            )
    for setting in db.session.scalars(
        select(SiteSetting).where(SiteSetting.key.in_(MEDIA_SETTINGS))
    ):
        if isinstance(setting.value, int):
            add(
                setting.value,
                {
                    "type": "setting",
                    "id": setting.key,
                    "label": "Branding & settings",
                    "field": setting.key,
                    "public": True,
                },
            )
    from ...models import Product, ProductCollection

    for product in db.session.scalars(select(Product)):
        base = {"type": "product", "id": product.id, "label": product.title}
        for field, asset_id in (
            ("cover (draft)", product.cover_media_id),
            ("social image (draft)", product.social_image_id),
        ):
            add(asset_id, {**base, "field": field, "public": False})
        for asset_id in product.gallery or []:
            add(asset_id, {**base, "field": "gallery (draft)", "public": False})
        snapshot = product.published_snapshot if product.status == "published" else None
        if snapshot:
            for field, asset_id in (
                ("cover", snapshot.get("cover_media_id")),
                ("social image", snapshot.get("social_image_id")),
            ):
                add(asset_id, {**base, "field": field, "public": True})
            for asset_id in snapshot.get("gallery") or []:
                add(asset_id, {**base, "field": "gallery", "public": True})
    for collection in db.session.scalars(
        select(ProductCollection).where(ProductCollection.cover_media_id.is_not(None))
    ):
        add(
            collection.cover_media_id,
            {
                "type": "product_collection",
                "id": collection.id,
                "label": collection.name,
                "field": "collection cover",
                "public": collection.is_active,
            },
        )
    return index


def usages_for(asset: MediaAsset) -> list[dict[str, Any]]:
    return usage_index().get(asset.id, [])


# ---- serialisation ------------------------------------------------------------------


def asset_summary(asset: MediaAsset, usage: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = media_dict(asset)
    thumb = next(
        (v for v in asset.current_variants("responsive") if v.format == "webp" and v.width >= 320),
        None,
    ) or next(iter(asset.current_variants("responsive")), None)
    data.update(
        title=asset.title,
        caption=asset.caption,
        credit=asset.credit,
        source_url=asset.source_url,
        status=asset.status,
        managed=asset.is_managed,
        thumbnail_url=public_url(thumb.storage_key) if thumb else asset.public_url,
        focal_point={"x": asset.focal_x, "y": asset.focal_y},
        updated_at=iso(asset.updated_at),
        usage_count=len(usage) if usage is not None else None,
        missing_alt=asset.mime_type.startswith("image/") and not asset.alt_text.strip(),
    )
    return data


def asset_detail(asset: MediaAsset) -> dict[str, Any]:
    usage = usages_for(asset)
    variants = asset.current_variants()
    return {
        **asset_summary(asset, usage),
        "version": asset.version,
        "has_alpha": asset.has_alpha,
        "original": {
            "filename": asset.original_filename,
            "mime_type": asset.original_mime,
            "size_bytes": asset.original_size,
            "retained": bool(asset.original_key),
        },
        "variants": [
            {
                "preset": v.preset,
                "format": v.format,
                "width": v.width,
                "height": v.height,
                "size_bytes": v.size_bytes,
                "url": public_url(v.storage_key),
            }
            for v in variants
        ],
        "variants_size_bytes": sum(v.size_bytes for v in variants),
        "image": asset.as_image(),
        "usage": usage,
        "uploaded_by": asset_uploader(asset),
    }


def asset_uploader(asset: MediaAsset) -> dict[str, Any] | None:
    if not asset.uploaded_by_id:
        return None
    user = db.session.get(User, asset.uploaded_by_id)
    return {"id": user.id, "display_name": user.display_name} if user else None


def list_media(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(MediaAsset).where(MediaAsset.visibility == "public")
    status = args.get("status") or "active"
    if status != "all":
        stmt = stmt.where(MediaAsset.status == status)
    if args.get("q"):
        like = f"%{args['q'].strip()}%"
        stmt = stmt.where(
            or_(
                MediaAsset.filename.ilike(like),
                MediaAsset.title.ilike(like),
                MediaAsset.alt_text.ilike(like),
                MediaAsset.caption.ilike(like),
            )
        )
    if args.get("type"):
        stmt = stmt.where(MediaAsset.mime_type == args["type"])
    else:
        stmt = stmt.where(MediaAsset.mime_type.like("image/%"))
    if args.get("uploaded_from"):
        stmt = stmt.where(MediaAsset.created_at >= args["uploaded_from"])
    if args.get("uploaded_to"):
        stmt = stmt.where(MediaAsset.created_at < args["uploaded_to"] + timedelta(days=1))
    index = usage_index()
    if args.get("usage") == "used":
        stmt = stmt.where(MediaAsset.id.in_(list(index) or [0]))
    elif args.get("usage") == "unused":
        stmt = stmt.where(MediaAsset.id.not_in(list(index) or [0]))
    elif args.get("usage") == "missing_alt":
        stmt = stmt.where(func.trim(MediaAsset.alt_text) == "")
    stmt = stmt.order_by(*SORTS.get(args.get("sort") or "newest", SORTS["newest"]))
    page, size = args.get("page", 1), args.get("page_size", 30)
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.session.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    pages = max(1, -(-total // size))
    return [asset_summary(a, index.get(a.id, [])) for a in items], {
        "page": page,
        "page_size": size,
        "total": total,
        "total_pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def storage_stats() -> dict[str, Any]:
    managed = select(MediaAsset).where(MediaAsset.public_id.is_not(None))
    originals = db.session.scalar(
        select(func.coalesce(func.sum(MediaAsset.original_size), 0)).where(
            MediaAsset.original_key.is_not(None)
        )
    )
    current = db.session.scalar(
        select(func.coalesce(func.sum(MediaVariant.size_bytes), 0)).where(
            MediaVariant.superseded_at.is_(None)
        )
    )
    superseded = db.session.scalar(
        select(func.coalesce(func.sum(MediaVariant.size_bytes), 0)).where(
            MediaVariant.superseded_at.is_not(None)
        )
    )
    return {
        "assets": db.session.scalar(select(func.count()).select_from(managed.subquery())) or 0,
        "originals_bytes": int(originals or 0),
        "variants_bytes": int(current or 0),
        "superseded_bytes": int(superseded or 0),
        "retention": current_app.config["MEDIA_RETENTION"],
        "max_upload_mb": current_app.config["MEDIA_MAX_UPLOAD_MB"],
        "avif_enabled": bool(current_app.config["MEDIA_ENABLE_AVIF"])
        and "AVIF" in processing.SUPPORTED_FORMATS,
        "accepted_types": sorted(set(processing.SUPPORTED_FORMATS.values())),
        "presets": [
            {
                "name": p.name,
                "label": p.label,
                "aspect": p.aspect,
                "mode": p.mode,
                "max_width": p.max_width,
                "target_kb": list(p.target_kb),
                "sizes": p.sizes,
            }
            for p in processing.PRESETS.values()
        ],
    }


# ---- metadata validation ----------------------------------------------------------------


_TEXT_LIMITS = {"alt_text": 300, "title": 200, "caption": 500, "credit": 200}


def clean_metadata(data: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    clean: dict[str, Any] = {}
    for field, limit in _TEXT_LIMITS.items():
        if field not in data:
            continue
        value = (data.get(field) or "").strip()
        if len(value) > limit:
            errors[field] = [f"At most {limit} characters."]
        elif problem := plain_text_problem(value):
            errors[field] = [problem]
        clean[field] = value
    if "source_url" in data:
        value = (data.get("source_url") or "").strip() or None
        if value and not is_https_url(value):
            errors["source_url"] = ["Use a full https:// address."]
        clean["source_url"] = value
    if "filename" in data:
        slug = processing.slugify(data.get("filename") or "")
        clean["filename"] = slug
    for axis in ("focal_x", "focal_y"):
        if axis in data:
            value = data[axis]
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                errors[axis] = ["Use a value between 0 and 1."]
            else:
                clean[axis] = round(float(value), 4)
    if errors:
        raise ValidationError("Some media details are invalid.", details=errors)
    return clean


# ---- processing + storage ------------------------------------------------------------


class Written:
    """Tracks files written during a request so they can be removed on failure."""

    def __init__(self):
        self.keys: list[tuple[str, bool]] = []

    def save(self, key: str, data: bytes, public: bool) -> None:
        get_storage().save(key, data, public=public)
        self.keys.append((key, public))

    def cleanup(self) -> None:
        storage = get_storage()
        for key, public in reversed(self.keys):
            try:
                storage.delete(key, public=public)
            except Exception:  # pragma: no cover - best effort
                current_app.logger.warning("Could not remove %s after a failed upload", key)
        self.keys.clear()


def _limits() -> dict[str, int]:
    cfg = current_app.config
    return {
        "max_bytes": cfg["MEDIA_MAX_UPLOAD_MB"] * 1024 * 1024,
        "max_pixels": cfg["MEDIA_MAX_PIXELS"],
        "max_dimension": cfg["MEDIA_MAX_DIMENSION"],
    }


def _process(data: bytes, focal: tuple[float, float]) -> processing.ProcessedImage:
    cfg = current_app.config
    try:
        return processing.process(
            data,
            **_limits(),
            focal=focal,
            avif=bool(cfg["MEDIA_ENABLE_AVIF"]),
            keep_master=cfg["MEDIA_RETENTION"] == "master",
        )
    except processing.ImageRejected as exc:
        raise ValidationError(str(exc), details={"file": [str(exc)]}) from None


def _store_version(
    asset: MediaAsset,
    result: processing.ProcessedImage,
    source: bytes,
    written: Written,
    source_ext: str,
) -> None:
    """Write a processed version's files and variant rows; supersede older variants."""
    slug = processing.slugify(asset.filename)
    prefix = f"{asset.public_id}/v{asset.version}"
    now = _now()
    for old in asset.current_variants():
        old.superseded_at = now
    rows = []
    for f in result.files:
        name = f"{slug}-{f.width}" if f.preset == "responsive" else f"{slug}-{f.preset}-{f.width}"
        key = f"{prefix}/{name}.{processing.EXT[f.format]}"
        written.save(key, f.data, public=True)
        rows.append(
            MediaVariant(
                version=asset.version,
                preset=f.preset,
                format=f.format,
                width=f.width,
                height=f.height,
                size_bytes=len(f.data),
                storage_key=key,
            )
        )
    asset.variants.extend(rows)
    # Retained source (private). In "master" mode the metadata-free master replaces it.
    retention = current_app.config["MEDIA_RETENTION"]
    if retention == "master" and result.master:
        ext = "png" if result.master[:4] == b"\x89PNG" else "webp"
        key = f"originals/{asset.public_id}/v{asset.version}-master.{ext}"
        written.save(key, result.master, public=False)
        asset.original_key, asset.original_size = key, len(result.master)
    else:
        key = f"originals/{asset.public_id}/v{asset.version}.{source_ext}"
        written.save(key, source, public=False)
        asset.original_key, asset.original_size = key, len(source)
    responsive = [r for r in rows if r.preset == "responsive"]
    fallback = [r for r in responsive if r.format in ("jpeg", "png")] or responsive
    main = max(fallback, key=lambda r: (r.width <= 1280, r.width))
    asset.storage_key = main.storage_key
    asset.mime_type = processing.MIME[main.format]
    asset.size_bytes = sum(r.size_bytes for r in rows)
    asset.width, asset.height = result.width, result.height
    asset.has_alpha = result.has_alpha
    asset.dominant_color = result.dominant_color
    asset.original_mime = result.source_mime


_SOURCE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}


def upload(
    data: bytes, filename: str, meta: dict[str, Any], actor: User, written: Written
) -> tuple[MediaAsset, bool]:
    """Create an asset from an upload. Returns (asset, created). Identical files are reused."""
    checksum = hashlib.sha256(data).hexdigest()
    existing = db.session.scalar(
        select(MediaAsset).where(MediaAsset.checksum == checksum, MediaAsset.status == "active")
    )
    if existing is not None:
        return existing, False
    clean = clean_metadata(meta)
    result = _process(data, (0.5, 0.5))
    asset = MediaAsset(
        public_id=secrets.token_hex(8),
        filename=clean.get("filename") or processing.slugify(filename or clean.get("title", "")),
        original_filename=(filename or "")[:255] or None,
        alt_text=clean.get("alt_text", ""),
        title=clean.get("title") or "",
        caption=clean.get("caption", ""),
        credit=clean.get("credit", ""),
        source_url=clean.get("source_url"),
        visibility="public",
        status="active",
        checksum=checksum,
        version=1,
        uploaded_by_id=actor.id,
        mime_type="image/webp",
        storage_key="pending",
    )
    db.session.add(asset)
    _store_version(asset, result, data, written, _SOURCE_EXT[result.source_mime])
    db.session.flush()
    audit_service.record(
        "media.uploaded",
        "media",
        asset.id,
        actor=actor,
        details={
            "filename": asset.filename,
            "source_bytes": len(data),
            "variants": len(asset.current_variants()),
            "variants_bytes": asset.size_bytes,
        },
    )
    return asset, True


def _is_public(asset: MediaAsset) -> bool:
    return any(ref["public"] for ref in usages_for(asset))


def update_metadata(asset: MediaAsset, data: dict[str, Any], actor: User, written: Written):
    clean = clean_metadata(data)
    changes: dict[str, Any] = {}
    for field, value in clean.items():
        if field in ("focal_x", "focal_y"):
            continue
        if getattr(asset, field) != value:
            changes[field] = {"from": getattr(asset, field), "to": value}
            setattr(asset, field, value)
    focal = (clean.get("focal_x", asset.focal_x), clean.get("focal_y", asset.focal_y))
    if (focal[0], focal[1]) != (asset.focal_x, asset.focal_y):
        if not asset.is_managed or not asset.original_key:
            raise ConflictError("The focal point can only be set on uploaded images.")
        changes["focal_point"] = {"from": [asset.focal_x, asset.focal_y], "to": list(focal)}
        asset.focal_x, asset.focal_y = focal
        # Crops change, so regenerate a new version from the retained source.
        source = get_storage().read(asset.original_key, public=False)
        result = _process(source, focal)
        asset.version += 1
        _store_version(asset, result, source, written, asset.original_key.rsplit(".", 1)[-1])
    if changes:
        audit_service.record("media.updated", "media", asset.id, actor=actor, details=changes)
        if _is_public(asset):
            record_public_change("media", asset.id, "media_updated", actor)
    return asset


def replace(asset: MediaAsset, data: bytes, filename: str, actor: User, written: Written):
    if not asset.is_managed:
        raise ConflictError("Built-in images cannot be replaced. Upload a new image instead.")
    if asset.status != "active":
        raise ConflictError("Restore the image before replacing it.")
    checksum = hashlib.sha256(data).hexdigest()
    if checksum == asset.checksum:
        return asset, False
    result = _process(data, (asset.focal_x, asset.focal_y))
    asset.version += 1
    asset.checksum = checksum
    asset.original_filename = (filename or "")[:255] or asset.original_filename
    _store_version(asset, result, data, written, _SOURCE_EXT[result.source_mime])
    db.session.flush()
    audit_service.record(
        "media.replaced",
        "media",
        asset.id,
        actor=actor,
        details={"version": asset.version, "variants_bytes": asset.size_bytes},
    )
    if _is_public(asset):
        record_public_change("media", asset.id, "media_replaced", actor)
    return asset, True


def archive(asset: MediaAsset, actor: User) -> MediaAsset:
    """Hide from pickers. Files keep being served, so existing content never breaks."""
    if asset.status == "archived":
        raise ConflictError("The image is already archived.")
    asset.status = "archived"
    asset.archived_at = _now()
    audit_service.record("media.archived", "media", asset.id, actor=actor)
    return asset


def restore(asset: MediaAsset, actor: User) -> MediaAsset:
    if asset.status != "archived":
        raise ConflictError("Only archived images can be restored.")
    asset.status = "active"
    asset.archived_at = None
    audit_service.record("media.restored", "media", asset.id, actor=actor)
    return asset


def delete(asset: MediaAsset, actor: User) -> list[tuple[str, bool]]:
    """Delete an unused asset. Returns storage keys to remove after the commit."""
    usage = usages_for(asset)
    if usage:
        raise ConflictError(
            f"This image is used in {len(usage)} place(s). Remove it from that content "
            "first, or archive it instead.",
            details={"usage": usage},
        )
    if not asset.is_managed:
        raise ConflictError("Built-in images are part of the website code and cannot be deleted.")
    keys = [(v.storage_key, True) for v in asset.variants]
    if asset.original_key:
        keys.append((asset.original_key, False))
    audit_service.record(
        "media.deleted",
        "media",
        asset.id,
        actor=actor,
        details={"filename": asset.filename, "title": asset.title},
    )
    db.session.delete(asset)
    return keys


def remove_files(keys: list[tuple[str, bool]]) -> None:
    storage = get_storage()
    for key, public in keys:
        try:
            storage.delete(key, public=public)
        except Exception:  # pragma: no cover
            current_app.logger.warning("Could not delete media file %s", key)


def prune_superseded(days: int | None = None) -> dict[str, int]:
    """Delete files of variants superseded more than ``days`` ago (default from config)."""
    days = current_app.config["MEDIA_SUPERSEDED_RETENTION_DAYS"] if days is None else days
    cutoff = _now() - timedelta(days=days)
    old = db.session.scalars(
        select(MediaVariant).where(
            MediaVariant.superseded_at.is_not(None), MediaVariant.superseded_at <= cutoff
        )
    ).all()
    freed = 0
    for variant in old:
        get_storage().delete(variant.storage_key, public=True)
        freed += variant.size_bytes
        db.session.delete(variant)
    return {"variants_removed": len(old), "bytes_freed": freed}


def get_asset(asset_id: int) -> MediaAsset:
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or asset.visibility != "public":
        raise NotFoundError("Image not found.")
    return asset


def media_ref_problems(refs: dict[str, int]) -> dict[str, str]:
    """{field: asset id} -> {field: problem} for images that cannot be used publicly."""
    ids = {i for i in refs.values() if i}
    found = {a.id: a for a in db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))}
    problems = {}
    for field, asset_id in refs.items():
        asset = found.get(asset_id)
        if asset is None:
            problems[field] = "This image no longer exists."
        elif asset.visibility != "public" or not asset.mime_type.startswith("image/"):
            problems[field] = "This file cannot be used on the website."
        elif asset.status == "archived":
            problems[field] = "This image is archived. Restore it or choose another image."
    return problems


def validate_media_refs(ids: Iterable[int], *, allow_archived: set[int] | None = None) -> None:
    """Content may only reference existing public images (archived ones only if kept)."""
    ids = {i for i in ids if i}
    if not ids:
        return
    found = {a.id: a for a in db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    bad = [
        i
        for i, a in found.items()
        if a.visibility != "public"
        or not a.mime_type.startswith("image/")
        or (a.status == "archived" and i not in (allow_archived or set()))
    ]
    if missing or bad:
        raise ValidationError(
            "Some images cannot be used.",
            details={"media": [f"Image {i} is missing or unavailable." for i in missing + bad]},
        )


# ---- built-in (legacy) assets ---------------------------------------------------------

_LEGACY_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}


def validate_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Validate metadata for built-in static images shipped with the frontend (seed data).

    These files are part of the code base (trusted), so SVG is allowed here only;
    uploaded SVG is rejected by the processing pipeline.
    """
    errors: dict[str, list[str]] = {}
    filename = str(data.get("filename", ""))
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$", filename) or ".." in filename:
        errors["filename"] = ["Use a simple file name (letters, numbers, dots, dashes)."]
    if data.get("mime_type") not in _LEGACY_MIME_TYPES:
        errors["mime_type"] = ["This file type is not allowed."]
    if not str(data.get("alt_text", "")).strip():
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


def generate_preset(name: str, asset_ids: list[int] | None) -> int:
    """Add files for an on-demand preset to existing versions (no version bump)."""
    preset = processing.PRESETS.get(name)
    if preset is None or preset.mode != "cropped":
        raise ValidationError(f"Unknown cropped preset '{name}'.")
    stmt = select(MediaAsset).where(
        MediaAsset.public_id.is_not(None),
        MediaAsset.original_key.is_not(None),
        MediaAsset.status == "active",
    )
    if asset_ids:
        stmt = stmt.where(MediaAsset.id.in_(asset_ids))
    count = 0
    for asset in db.session.scalars(stmt):
        if asset.current_variants(name):
            continue  # already generated for this version
        source = get_storage().read(asset.original_key, public=False)
        result = processing.process(
            source,
            **_limits(),
            focal=(asset.focal_x, asset.focal_y),
            presets=(name,),
            avif=bool(current_app.config["MEDIA_ENABLE_AVIF"]),
        )
        slug = processing.slugify(asset.filename)
        for f in result.files:
            ext = processing.EXT[f.format]
            key = f"{asset.public_id}/v{asset.version}/{slug}-{name}-{f.width}.{ext}"
            get_storage().save(key, f.data, public=True)
            asset.variants.append(
                MediaVariant(
                    version=asset.version,
                    preset=name,
                    format=f.format,
                    width=f.width,
                    height=f.height,
                    size_bytes=len(f.data),
                    storage_key=key,
                )
            )
        count += 1
    return count


def verify_files() -> list[str]:
    storage = get_storage()
    missing = []
    for variant in db.session.scalars(
        select(MediaVariant).where(MediaVariant.superseded_at.is_(None))
    ):
        if not storage.exists(variant.storage_key, public=True):
            missing.append(variant.storage_key)
    return missing
