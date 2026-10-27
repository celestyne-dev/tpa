"""Storage health for the VPS: disk space, permissions, integrity, temp files, backups.

Used by /admin/storage and ``flask storage check``. Everything here is read-only
except ``cleanup_temp``. Storage keys and absolute paths of private files are
never returned to the browser beyond the configured root directories, which
administrators set themselves.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import func, select

from ..config import storage_layout_problems
from ..extensions import db
from ..models import AuditLog, MediaAsset, MediaVariant, ProductFile, ProductFileVersion
from ..storage import get_storage
from ..storage.private_files import get_private_storage
from .serializers import iso

UPLOAD_ERROR_ACTIONS = (
    "media.rejected",
    "media.storage_failed",
    "product_file.rejected",
    "product_file.storage_failed",
)
LEVELS = {"ok": 0, "info": 1, "warning": 2, "critical": 3}


def _now() -> datetime:
    return datetime.now(UTC)


def _disk(path: Path) -> dict[str, Any] | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return None
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_percent": round(usage.free * 100 / usage.total, 1) if usage.total else 0.0,
    }


def _mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def _writable(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def _area(key: str, label: str, path: Path, purpose: str, *, private: bool) -> dict[str, Any]:
    mode = _mode(path)
    return {
        "key": key,
        "label": label,
        "path": str(path),
        "purpose": purpose,
        "private": private,
        "exists": path.is_dir(),
        "writable": _writable(path),
        "mode": f"{mode:04o}" if mode is not None else None,
        "disk": _disk(path),
    }


def _backup_status() -> dict[str, Any]:
    path = current_app.config.get("BACKUP_STATUS_FILE") or ""
    if not path:
        return {"configured": False}
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {"configured": True, "found": False}
    except (OSError, ValueError):
        return {"configured": True, "found": True, "readable": False}
    finished = data.get("finished_at")
    age_hours = None
    if finished:
        try:
            age_hours = round(
                (_now() - datetime.fromisoformat(finished.replace("Z", "+00:00"))).total_seconds()
                / 3600,
                1,
            )
        except ValueError:
            age_hours = None
    return {
        "configured": True,
        "found": True,
        "readable": True,
        "ok": data.get("status") == "ok",
        "finished_at": finished,
        "age_hours": age_hours,
        "size_bytes": data.get("size_bytes"),
        "offsite": data.get("offsite"),
        "verified": data.get("verified"),
        "message": str(data.get("message", ""))[:300],
    }


def _integrity(private) -> dict[str, Any]:
    versions = db.session.execute(
        select(ProductFileVersion.id, ProductFileVersion.storage_key, ProductFile.status).join(
            ProductFile, ProductFile.id == ProductFileVersion.file_id
        )
    ).all()
    known = {key for _, key, _ in versions}
    missing_premium = [vid for vid, key, _ in versions if not private.exists(key)]
    orphans = sum(1 for key in private.iter_keys() if key not in known)
    media = get_storage()
    missing_media = 0
    if hasattr(media, "exists"):
        for key in db.session.scalars(
            select(MediaVariant.storage_key).where(MediaVariant.superseded_at.is_(None))
        ):
            if not media.exists(key, public=True):
                missing_media += 1
    return {
        "premium_versions": len(versions),
        "missing_premium_versions": missing_premium[:50],
        "missing_premium_count": len(missing_premium),
        "orphan_premium_files": orphans,
        "missing_media_variants": missing_media,
    }


def _tracked() -> dict[str, int]:
    def total(stmt) -> int:
        return int(db.session.scalar(stmt) or 0)

    return {
        "media_variants_bytes": total(
            select(func.coalesce(func.sum(MediaVariant.size_bytes), 0)).where(
                MediaVariant.superseded_at.is_(None)
            )
        ),
        "media_superseded_bytes": total(
            select(func.coalesce(func.sum(MediaVariant.size_bytes), 0)).where(
                MediaVariant.superseded_at.is_not(None)
            )
        ),
        "media_originals_bytes": total(
            select(func.coalesce(func.sum(MediaAsset.original_size), 0)).where(
                MediaAsset.original_key.is_not(None)
            )
        ),
        "premium_bytes": total(select(func.coalesce(func.sum(ProductFileVersion.size_bytes), 0))),
        "premium_files": total(select(func.count(ProductFile.id))),
        "premium_versions": total(select(func.count(ProductFileVersion.id))),
    }


def report(*, integrity: bool = True) -> dict[str, Any]:
    cfg = current_app.config
    media_root = Path(cfg["MEDIA_ROOT"]).resolve()
    private = get_private_storage()
    areas = [
        _area(
            "media_public",
            "Public images (optimised)",
            media_root / "public",
            "Optimised image versions served at /media/ by Nginx with long-lived caching.",
            private=False,
        ),
        _area(
            "media_originals",
            "Image originals",
            media_root / "private",
            "Retained original uploads (may contain camera metadata). Never served.",
            private=True,
        ),
        _area(
            "resources_private",
            "Premium resource files",
            Path(private.root),
            "Paid and free resource files. Delivered only through authorised download links.",
            private=True,
        ),
        _area(
            "upload_temp",
            "Temporary uploads",
            Path(private.temp_root),
            "Uploads in progress and files being validated. Cleaned automatically.",
            private=True,
        ),
    ]
    warnings: list[dict[str, str]] = []

    def warn(level: str, code: str, message: str) -> None:
        warnings.append({"level": level, "code": code, "message": message})

    for problem in storage_layout_problems(_ConfigView(cfg)):
        warn("critical", "layout", f"Unsafe storage configuration: {problem}.")
    accel = bool(cfg.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"))
    seen_disks: set[str] = set()
    for area in areas:
        mode = int(area["mode"], 8) if area["mode"] else None
        if not area["exists"]:
            warn(
                "warning" if area["key"] == "upload_temp" else "critical",
                f"{area['key']}_missing",
                f"{area['label']}: the folder {area['path']} does not exist yet. Run "
                "`flask storage init`.",
            )
            continue
        if not area["writable"]:
            warn(
                "critical",
                f"{area['key']}_readonly",
                f"{area['label']}: the application cannot write to {area['path']}.",
            )
        if area["private"] and mode is not None and mode & 0o007:
            warn(
                "critical",
                f"{area['key']}_world",
                f"{area['label']}: {area['path']} is accessible to every user on the server "
                f"(mode {area['mode']}). Run `chmod o-rwx` on it.",
            )
        if (
            area["key"] == "resources_private"
            and accel
            and mode is not None
            and mode & 0o050 != 0o050
        ):
            warn(
                "critical",
                "resources_accel_unreadable",
                "Nginx delivers premium files (X-Accel-Redirect) but the folder is not "
                "readable by its group: downloads would fail. Use mode 0750 and the Nginx "
                "group (www-data).",
            )
        if (
            area["key"] == "media_public"
            and not cfg.get("MEDIA_SERVE_FROM_FLASK")
            and mode is not None
            and not mode & 0o055
        ):
            warn(
                "warning",
                "media_public_unreadable",
                "Public images may not be readable by Nginx (no group/other access).",
            )
        disk = area["disk"]
        if disk:
            disk_id = f"{disk['total_bytes']}:{disk['free_bytes'] // (1 << 20)}"
            if disk_id in seen_disks:
                continue
            seen_disks.add(disk_id)
            if disk["free_percent"] < cfg["STORAGE_CRITICAL_FREE_PERCENT"]:
                warn(
                    "critical",
                    "disk_critical",
                    f"Only {disk['free_percent']}% disk space is free where {area['label']} "
                    "are stored. Uploads will start failing; free space or resize the disk.",
                )
            elif disk["free_percent"] < cfg["STORAGE_WARN_FREE_PERCENT"]:
                warn(
                    "warning",
                    "disk_low",
                    f"Disk space is getting low ({disk['free_percent']}% free) where "
                    f"{area['label']} are stored.",
                )

    stale = private.stale_temp_files(cfg["UPLOAD_TEMP_MAX_AGE_HOURS"])
    if stale:
        warn(
            "info",
            "temp_stale",
            f"{len(stale)} abandoned temporary upload(s) older than "
            f"{cfg['UPLOAD_TEMP_MAX_AGE_HOURS']} h. `flask storage cleanup-temp` removes them.",
        )

    checks = _integrity(private) if integrity else None
    if checks:
        if checks["missing_premium_count"]:
            warn(
                "critical",
                "premium_missing",
                f"{checks['missing_premium_count']} premium file version(s) are recorded but "
                "missing from disk. Restore them from a backup.",
            )
        if checks["missing_media_variants"]:
            warn(
                "warning",
                "media_missing",
                f"{checks['missing_media_variants']} image file(s) are missing from disk.",
            )
        if checks["orphan_premium_files"]:
            warn(
                "info",
                "premium_orphans",
                f"{checks['orphan_premium_files']} file(s) in premium storage are not linked to "
                "any version (left by an interrupted upload or a manual copy).",
            )

    backup = _backup_status()
    if not backup.get("configured"):
        warn(
            "warning" if cfg.get("ENV_NAME") == "production" else "info",
            "backup_unconfigured",
            "No backup status file is configured (BACKUP_STATUS_FILE), so backups can't be "
            "monitored here.",
        )
    elif not backup.get("found"):
        warn("warning", "backup_missing", "No backup has been recorded yet.")
    elif not backup.get("readable"):
        warn("warning", "backup_unreadable", "The backup status file could not be read.")
    elif not backup.get("ok"):
        warn("critical", "backup_failed", f"The last backup failed: {backup.get('message')}")
    elif backup.get("age_hours") is not None and backup["age_hours"] > cfg["BACKUP_MAX_AGE_HOURS"]:
        warn(
            "critical",
            "backup_stale",
            f"The last successful backup is {backup['age_hours']} hours old.",
        )

    rate_limit = str(cfg.get("RATELIMIT_STORAGE_URI", "memory://")).split(":", 1)[0]
    if cfg.get("ENV_NAME") == "production" and rate_limit == "memory":
        warn(
            "warning",
            "ratelimit_memory",
            "Rate limits are kept in each Gunicorn worker's memory. Set RATELIMIT_STORAGE_URI "
            "to Redis so limits are shared.",
        )

    status = max((w["level"] for w in warnings), key=LEVELS.get, default="ok")
    if status == "info":
        status = "ok"
    return {
        "generated_at": iso(_now()),
        "status": status,
        "areas": areas,
        "warnings": sorted(warnings, key=lambda w: -LEVELS[w["level"]]),
        "tracked": _tracked(),
        "temp": {"stale_files": len(stale), "max_age_hours": cfg["UPLOAD_TEMP_MAX_AGE_HOURS"]},
        "integrity": checks,
        "backup": backup,
        "rate_limit_storage": rate_limit,
        "limits": {
            "media_max_mb": cfg["MEDIA_MAX_UPLOAD_MB"],
            "premium_max_mb": cfg["PRODUCT_FILE_MAX_MB"],
            "premium_formats": list(cfg["RESOURCE_FILE_FORMATS"]),
            "x_accel_redirect": accel,
        },
    }


class _ConfigView:
    """Attribute access over app.config for storage_layout_problems."""

    def __init__(self, cfg):
        self._cfg = cfg

    def __getattr__(self, name):
        return self._cfg.get(name, "")


def cleanup_temp() -> int:
    cfg = current_app.config
    return get_private_storage().cleanup_temp(cfg["UPLOAD_TEMP_MAX_AGE_HOURS"])


def init_layout() -> list[str]:
    """Create every storage folder with safe permissions (idempotent)."""
    created = [str(p) for p in get_private_storage().init_layout()]
    media_root = Path(current_app.config["MEDIA_ROOT"])
    for name, mode in (("public", 0o755), ("private", 0o700)):
        folder = media_root / name
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, mode)
        created.append(str(folder))
    return created


def upload_errors(limit: int = 100) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(AuditLog)
        .where(AuditLog.action.in_(UPLOAD_ERROR_ACTIONS))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id,
            "at": iso(r.created_at),
            "area": "images" if r.action.startswith("media.") else "premium files",
            "kind": "rejected" if r.action.endswith("rejected") else "storage failure",
            "filename": (r.details or {}).get("filename", ""),
            "reason": (r.details or {}).get("reason", ""),
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "actor": r.actor.display_name if r.actor else None,
        }
        for r in rows
    ]
