"""Premium file library: every protected resource file across all resources, in one place.

The Media Library's "Premium files" view reads this. Files still belong to a resource
(a product); uploading, replacing (a new version) and archiving (deactivating) use the
existing product file endpoints. Deletion is deliberately narrow:

- a version can be deleted only if it isn't the current one, no purchase recorded it
  (``Entitlement.purchased_versions``), and it was never authorised or downloaded (the
  download log keeps pointing at it);
- a whole file can be deleted only if none of its versions is protected that way and no
  purchase ever included the file. Otherwise it can be archived (deactivated): buyers keep
  access to what they bought, new buyers don't get it.

Storage keys and paths are never returned.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import (
    DownloadEvent,
    DownloadGrant,
    Entitlement,
    Product,
    ProductFile,
    User,
)
from ...storage.private_files import category_for, get_private_storage
from ...utils.errors import ConflictError, NotFoundError
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso
from .product_admin import _require

SORTS = ("newest", "title", "size", "downloads")


def _purchased_version_ids(product_id: int) -> tuple[set[int], set[str]]:
    """(version ids recorded by purchases, file ids that any purchase included)."""
    versions: set[int] = set()
    files: set[str] = set()
    for recorded in db.session.scalars(
        select(Entitlement.purchased_versions).where(Entitlement.product_id == product_id)
    ):
        for file_id, version_id in (recorded or {}).items():
            files.add(str(file_id))
            if isinstance(version_id, int):
                versions.add(version_id)
    return versions, files


def _referenced(version_ids: list[int]) -> set[int]:
    if not version_ids:
        return set()
    granted = set(
        db.session.scalars(
            select(DownloadGrant.file_version_id).where(
                DownloadGrant.file_version_id.in_(version_ids)
            )
        )
    )
    logged = set(
        db.session.scalars(
            select(DownloadEvent.file_version_id).where(
                DownloadEvent.file_version_id.in_(version_ids)
            )
        )
    )
    return granted | logged


def _protection(file: ProductFile) -> dict[int, str]:
    """Why each version can't be deleted (missing: deletable)."""
    purchased, _ = _purchased_version_ids(file.product_id)
    used = _referenced([v.id for v in file.versions])
    reasons: dict[int, str] = {}
    for v in file.versions:
        if v.id == file.current_version_id:
            reasons[v.id] = "This is the current version buyers receive."
        elif v.id in purchased:
            reasons[v.id] = "Buyers received this version; it is kept for them."
        elif v.id in used:
            reasons[v.id] = "This version was downloaded; it is kept for the download log."
    return reasons


def _file_entry(file: ProductFile, downloads: dict[int, tuple[int, Any]]) -> dict[str, Any]:
    product: Product = file.product
    current = file.current_version
    served = sum(downloads.get(v.id, (0, None))[0] for v in file.versions)
    last = max((d[1] for v in file.versions if (d := downloads.get(v.id)) and d[1]), default=None)
    return {
        "id": file.id,
        "public_id": file.public_id,
        "title": file.title,
        "description": file.description,
        "status": file.status,
        "category": category_for(product.product_type),
        "product": {
            "id": product.id,
            "title": product.title,
            "type": product.product_type,
            "status": product.status,
            "pricing_model": product.pricing_model,
        },
        "current_version": {
            "version": current.version,
            "format": current.file_format,
            "mime_type": current.mime_type,
            "size_bytes": current.size_bytes,
            "original_filename": current.original_filename,
            "scan_status": current.scan_status,
            "uploaded_at": iso(current.created_at),
        }
        if current
        else None,
        "versions": len(file.versions),
        "total_bytes": sum(v.size_bytes for v in file.versions),
        "downloads": served,
        "last_download_at": iso(last),
        "updated_at": iso(file.updated_at),
    }


def list_files(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(ProductFile).join(Product, Product.id == ProductFile.product_id)
    if args.get("status") in ("active", "inactive"):
        stmt = stmt.where(ProductFile.status == args["status"])
    if args.get("product_id"):
        stmt = stmt.where(ProductFile.product_id == int(args["product_id"]))
    if args.get("q"):
        like = f"%{str(args['q']).strip().lower()[:100]}%"
        stmt = stmt.where(
            func.lower(ProductFile.title).like(like) | func.lower(Product.title).like(like)
        )
    files = list(db.session.scalars(stmt))
    version_ids = [v.id for f in files for v in f.versions]
    downloads = {
        vid: (count, last)
        for vid, count, last in db.session.execute(
            select(
                DownloadEvent.file_version_id,
                func.count(DownloadEvent.id),
                func.max(DownloadEvent.created_at),
            )
            .where(
                DownloadEvent.file_version_id.in_(version_ids or [0]),
                DownloadEvent.status == "served",
            )
            .group_by(DownloadEvent.file_version_id)
        ).all()
    }
    items = [_file_entry(f, downloads) for f in files]
    if args.get("format"):
        items = [
            i
            for i in items
            if i["current_version"] and i["current_version"]["format"] == args["format"]
        ]
    if args.get("category"):
        items = [i for i in items if i["category"] == args["category"]]
    sort = args.get("sort") if args.get("sort") in SORTS else "newest"
    if sort == "title":
        items.sort(key=lambda i: i["title"].lower())
    elif sort == "size":
        items.sort(key=lambda i: i["total_bytes"], reverse=True)
    elif sort == "downloads":
        items.sort(key=lambda i: i["downloads"], reverse=True)
    else:
        items.sort(key=lambda i: i["updated_at"] or "", reverse=True)
    summary = {
        "files": len(items),
        "total_bytes": sum(i["total_bytes"] for i in items),
        "formats": sorted({i["current_version"]["format"] for i in items if i["current_version"]}),
        "by_category": {},
    }
    for item in items:
        summary["by_category"][item["category"]] = (
            summary["by_category"].get(item["category"], 0) + 1
        )
    return items, summary


def file_detail(file: ProductFile) -> dict[str, Any]:
    from .product_files import file_dict

    reasons = _protection(file)
    data = file_dict(file)
    for version in data["versions"]:
        version["delete_blocked_reason"] = reasons.get(version["id"])
        version["deletable"] = version["id"] not in reasons
    data["product"] = {"id": file.product.id, "title": file.product.title}
    data["deletable"] = _file_deletable(file, reasons) is None
    data["delete_blocked_reason"] = _file_deletable(file, reasons)
    return data


def _file_deletable(file: ProductFile, reasons: dict[int, str]) -> str | None:
    _, purchased_files = _purchased_version_ids(file.product_id)
    if str(file.id) in purchased_files:
        return "Buyers received this file. Archive it instead: they keep access."
    if _referenced([v.id for v in file.versions]):
        return "This file was downloaded. Archive it instead so the download log stays intact."
    return None


def get_file(file_id: int) -> ProductFile:
    file = db.session.get(ProductFile, file_id)
    if file is None:
        raise NotFoundError("File not found.")
    return file


def delete_version(file: ProductFile, version_id: int, actor: User) -> str:
    """Delete an unused version. Returns the storage key to remove after commit."""
    _require(actor, P.PRODUCTS_MANAGE_FILES)
    version = next((v for v in file.versions if v.id == version_id), None)
    if version is None:
        raise NotFoundError("Version not found.")
    reason = _protection(file).get(version.id)
    if reason:
        raise ConflictError(reason)
    key = version.storage_key
    db.session.delete(version)
    audit_service.record(
        "product_file.version_deleted",
        "product",
        file.product_id,
        actor=actor,
        details={"file_id": file.id, "version": version.version, "sha256": version.sha256},
    )
    return key


def delete_file(file: ProductFile, actor: User) -> list[str]:
    """Delete a file that was never sold or downloaded. Returns storage keys to remove."""
    _require(actor, P.PRODUCTS_MANAGE_FILES)
    reason = _file_deletable(file, _protection(file))
    if reason:
        raise ConflictError(reason)
    product = file.product
    keys = [v.storage_key for v in file.versions]
    file.current_version_id = None
    db.session.flush()
    for version in list(file.versions):
        db.session.delete(version)
    db.session.flush()
    db.session.delete(file)
    audit_service.record(
        "product_file.deleted",
        "product",
        product.id,
        actor=actor,
        details={"file_id": file.id, "title": file.title, "versions": len(keys)},
    )
    if product.status == "published":
        record_public_change("product", product.id, "product_files_changed", actor)
    return keys


def remove_stored(keys: list[str]) -> None:
    """Remove files from private storage after the database change is committed."""
    storage = get_private_storage()
    for key in keys:
        try:
            storage.delete(key)
        except OSError:
            continue  # reported later as an orphan by the storage health check
