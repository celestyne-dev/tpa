"""Private product files: upload, versions, deactivation, scanning and admin downloads.

Version policy (explicit and predictable):
- A file's *current* version is what new buyers receive.
- Every customer with access can always download the **current** version of each
  active file (free updates), **and** the exact version that was current when
  they were granted access, for as long as that version exists.
- Files deactivated after a purchase stay available to customers who bought
  before the deactivation (at the version they bought); new buyers don't get them.
- Versions referenced by any purchase are never deleted; replacing a file adds a
  new version instead of overwriting.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...commerce.files import FileRejected, safe_display_name, validate_file
from ...extensions import db
from ...models import DownloadEvent, Entitlement, Product, ProductFile, ProductFileVersion, User
from ...storage import StorageError
from ...storage.private_files import get_private_storage
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso
from .product_admin import _require, _text


class StorageUnavailableError(APIError):
    status_code = 507
    code = "storage_unavailable"
    message = "There is not enough private storage space for this file. Contact the site owner."


def _limits() -> dict[str, Any]:
    cfg = current_app.config
    return {
        "max_bytes": cfg["PRODUCT_FILE_MAX_MB"] * 1024 * 1024,
        "max_uncompressed": cfg["PRODUCT_ZIP_MAX_UNCOMPRESSED_MB"] * 1024 * 1024,
        "max_entries": cfg["PRODUCT_ZIP_MAX_ENTRIES"],
        "max_ratio": cfg["PRODUCT_ZIP_MAX_RATIO"],
    }


def scanner_configured() -> bool:
    return bool(current_app.config.get("PRODUCT_FILES_SCAN_COMMAND"))


def version_dict(v: ProductFileVersion, usage: dict[int, int] | None = None) -> dict[str, Any]:
    return {
        "id": v.id,
        "version": v.version,
        "original_filename": v.original_filename,
        "format": v.file_format,
        "mime_type": v.mime_type,
        "size_bytes": v.size_bytes,
        "sha256": v.sha256,
        "scan_status": v.scan_status,
        "scanned_at": iso(v.scanned_at),
        "deliverable": v.deliverable,
        "details": v.details or {},
        "created_at": iso(v.created_at),
        "purchases": (usage or {}).get(v.id, 0),
    }


def _version_usage(file: ProductFile) -> dict[int, int]:
    """How many entitlements recorded each version of this file at purchase time."""
    counts: dict[int, int] = {}
    entitlements = db.session.scalars(
        select(Entitlement.purchased_versions).where(Entitlement.product_id == file.product_id)
    )
    key = str(file.id)
    for versions in entitlements:
        vid = (versions or {}).get(key)
        if isinstance(vid, int):
            counts[vid] = counts.get(vid, 0) + 1
    return counts


def file_dict(file: ProductFile) -> dict[str, Any]:
    usage = _version_usage(file)
    downloads = db.session.scalar(
        select(func.count(DownloadEvent.id)).where(
            DownloadEvent.file_version_id.in_([v.id for v in file.versions] or [0]),
            DownloadEvent.status == "served",
        )
    )
    current = file.current_version
    return {
        "id": file.id,
        "public_id": file.public_id,
        "title": file.title,
        "description": file.description,
        "position": file.position,
        "status": file.status,
        "deactivated_at": iso(file.deactivated_at),
        "current_version": version_dict(current, usage) if current else None,
        "versions": [version_dict(v, usage) for v in reversed(file.versions)],
        "downloads": downloads or 0,
    }


def get_file(product: Product, file_id: int) -> ProductFile:
    file = db.session.get(ProductFile, file_id)
    if file is None or file.product_id != product.id:
        raise NotFoundError("File not found.")
    return file


def upload(
    product: Product,
    upload_file,
    actor: User,
    *,
    title: str | None,
    description: str | None,
    file: ProductFile | None = None,
    notes: str | None = None,
) -> ProductFile:
    """Store a new private file (or a new version of an existing one)."""
    _require(actor, P.PRODUCTS_MANAGE_FILES)
    if product.is_bundle:
        raise ValidationError(
            details={"file": ["Bundles deliver their included products' files; upload there."]}
        )
    if product.status == "archived":
        raise ConflictError("Restore this product before adding files.")
    if upload_file is None or not getattr(upload_file, "filename", ""):
        raise ValidationError(details={"file": ["Choose a file to upload."]})
    errors: dict[str, Any] = {}
    if file is None:
        title = _text(
            title or Path(safe_display_name(upload_file.filename)).stem,
            "title",
            200,
            errors,
            required=True,
        )
        description = _text(description, "description", 600, errors, multiline=True)
    notes = _text(notes, "notes", 300, errors)
    if errors:
        raise ValidationError(details=errors)

    storage = get_private_storage()
    limits = _limits()
    min_free = current_app.config["PRODUCT_FILES_MIN_FREE_MB"] * 1024 * 1024
    declared = getattr(upload_file, "content_length", 0) or 0
    try:
        if storage.free_bytes() < min_free + declared:
            raise StorageUnavailableError()
        tmp, size, digest = storage.receive(upload_file.stream, limits["max_bytes"])
    except StorageError as exc:
        if str(exc) == "too_large":
            raise ValidationError(
                details={
                    "file": [
                        f"Files can be at most {current_app.config['PRODUCT_FILE_MAX_MB']} MB."
                    ]
                }
            ) from None
        raise StorageUnavailableError() from None
    except OSError:
        raise StorageUnavailableError() from None
    try:
        report = validate_file(tmp, upload_file.filename, limits)
        if storage.free_bytes() < min_free:
            raise StorageUnavailableError()
        if file is None:
            file = ProductFile(
                public_id=secrets.token_hex(8),
                product_id=product.id,
                title=title,
                description=description or "",
                position=len(product.files),
            )
            db.session.add(file)
            db.session.flush()
        number = (max((v.version for v in file.versions), default=0)) + 1
        key = f"{file.public_id}/v{number}/{secrets.token_hex(16)}{report.format.extensions[0]}"
        version = ProductFileVersion(
            file_id=file.id,
            version=number,
            storage_key=key,
            original_filename=safe_display_name(upload_file.filename),
            file_format=report.format.key,
            mime_type=report.format.mime_type,
            size_bytes=size,
            sha256=digest,
            details=report.details,
            scan_status="pending" if scanner_configured() else "not_configured",
            notes=notes or "",
            uploaded_by_id=actor.id,
        )
        db.session.add(version)
        db.session.flush()
        storage.commit(tmp, key)
    except FileRejected as exc:
        storage.discard(tmp)
        db.session.rollback()
        audit_service.record(
            "product_file.rejected",
            "product",
            product.id,
            actor=actor,
            details={"reason": str(exc)[:200]},
        )
        db.session.commit()
        raise ValidationError("The file was not accepted.", details={"file": [str(exc)]}) from None
    except BaseException:
        storage.discard(tmp)
        raise
    file.current_version_id = version.id
    file.status = "active"
    file.deactivated_at = None
    audit_service.record(
        "product_file.uploaded",
        "product",
        product.id,
        actor=actor,
        details={
            "file_id": file.id,
            "version": number,
            "format": report.format.key,
            "size_bytes": size,
            "sha256": digest,
        },
    )
    if product.status == "published":
        record_public_change("product", product.id, "product_files_changed", actor)
    return file


def update_file(
    product: Product, file: ProductFile, data: dict[str, Any], actor: User
) -> ProductFile:
    _require(actor, P.PRODUCTS_MANAGE_FILES)
    allowed = {"title", "description", "position", "status", "current_version_id"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValidationError(details={"_unknown": ["Unknown field(s)."]})
    errors: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    if "title" in data:
        changes["title"] = _text(data["title"], "title", 200, errors, required=True)
    if "description" in data:
        changes["description"] = _text(
            data["description"], "description", 600, errors, multiline=True
        )
    if "position" in data:
        if not isinstance(data["position"], int) or isinstance(data["position"], bool):
            errors["position"] = ["Must be a whole number."]
        else:
            changes["position"] = data["position"]
    if "status" in data:
        if data["status"] not in ("active", "inactive"):
            errors["status"] = ["Use active or inactive."]
        else:
            changes["status"] = data["status"]
    if "current_version_id" in data:
        version = next((v for v in file.versions if v.id == data["current_version_id"]), None)
        if version is None:
            errors["current_version_id"] = ["Choose a version of this file."]
        else:
            changes["current_version_id"] = version.id
    if errors:
        raise ValidationError(details=errors)
    for key, value in changes.items():
        setattr(file, key, value)
    if changes.get("status") == "inactive":
        file.deactivated_at = datetime.now(UTC)
    elif changes.get("status") == "active":
        file.deactivated_at = None
    audit_service.record(
        "product_file.updated",
        "product",
        product.id,
        actor=actor,
        details={"file_id": file.id, **{k: v for k, v in changes.items()}},
    )
    if product.status == "published":
        record_public_change("product", product.id, "product_files_changed", actor)
    return file


def stream_version_for_admin(product: Product, file: ProductFile, version_id: int, actor: User):
    from .downloads import file_response

    _require(actor, P.PRODUCTS_MANAGE_FILES)
    version = next((v for v in file.versions if v.id == version_id), None)
    if version is None:
        raise NotFoundError("Version not found.")
    audit_service.record(
        "product_file.admin_download",
        "product",
        product.id,
        actor=actor,
        details={"file_id": file.id, "version": version.version},
    )
    db.session.commit()
    return file_response(version, f"{product.slug}-{file.public_id}-v{version.version}")


# ---- background scanning ----------------------------------------------------------------


def scan_pending(limit: int = 10) -> dict[str, int]:
    """Run the configured malware scanner on pending versions (worker/CLI only).

    The command is a fixed JSON argv list from the deployment configuration and is
    executed without a shell. It never runs inside a web request.
    """
    raw = current_app.config.get("PRODUCT_FILES_SCAN_COMMAND") or ""
    counts = {"clean": 0, "infected": 0, "error": 0}
    if not raw:
        return counts
    try:
        argv = json.loads(raw)
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv) and argv
    except (ValueError, AssertionError):
        current_app.logger.error("PRODUCT_FILES_SCAN_COMMAND must be a JSON list of strings.")
        return counts
    storage = get_private_storage()
    pending = db.session.scalars(
        select(ProductFileVersion).where(ProductFileVersion.scan_status == "pending").limit(limit)
    ).all()
    for version in pending:
        path = str(storage.path(version.storage_key))
        command = [a.replace("{path}", path) for a in argv]
        try:
            result = subprocess.run(  # noqa: S603 - fixed argv from configuration, no shell
                command,
                capture_output=True,
                timeout=current_app.config["PRODUCT_FILES_SCAN_TIMEOUT_SECONDS"],
                check=False,
            )
            status = {0: "clean", 1: "infected"}.get(result.returncode, "error")
        except (OSError, subprocess.SubprocessError):
            status = "error"
        version.scan_status = status
        version.scanned_at = datetime.now(UTC)
        counts[status] += 1
        audit_service.record(
            "product_file.scanned",
            "product_file",
            version.file_id,
            details={"version": version.version, "result": status},
        )
        if status != "clean":
            current_app.logger.warning(
                "Product file version %s scan result: %s", version.id, status
            )
    return counts
