"""Batch 08: VPS file storage — roots, temp uploads, atomic commits, permissions, file
validation (DOCX/XLSX), path safety, storage failures, health checks and upload errors."""

from __future__ import annotations

import errno
import io
import json
import os
import stat
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import storage_layout_problems
from app.extensions import db
from app.models import AuditLog, ProductFileVersion
from app.storage import StorageError, validate_key
from app.storage.private_files import LocalPrivateFileStorage, category_for

from .conftest import make_photo, minimal_pdf
from .test_commerce_catalogue import _create, _upload

STORAGE = "/api/v1/admin/storage"


def ooxml(kind="docx", *, extra=None, content_types=None):
    main = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml"}[kind]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            content_types
            or '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
            "</Types>",
        )
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr(main, "<document>Daily planner</document>")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buf.getvalue()


def _versions(app):
    with app.app_context():
        return db.session.scalars(db.select(ProductFileVersion)).all()


def _audit(app, action):
    with app.app_context():
        return db.session.scalars(db.select(AuditLog).where(AuditLog.action == action)).all()


# ---- layout, keys and permissions -------------------------------------------------------


def test_premium_files_use_category_folders_owner_only_modes_and_temp_area(seeded, as_role, app):
    api = as_role("product_manager")
    workbook = _create(api, "Workbook", product_type="workbook")
    template = _create(api, "Budget template", product_type="template")
    guide = _create(api, "Reset guide", product_type="guide")
    assert _upload(api, workbook["id"]).status_code == 201
    assert _upload(api, template["id"], ooxml("xlsx"), "budget.xlsx").status_code == 201
    assert _upload(api, guide["id"]).status_code == 201
    root = Path(app.config["PRODUCT_FILES_ROOT"]).resolve()
    folders = sorted(v.storage_key.split("/")[0] for v in _versions(app))
    assert folders == ["downloads", "templates", "workbooks"]
    for v in _versions(app):
        path = root / v.storage_key
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert v.original_filename not in v.storage_key
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    temp = Path(app.config["UPLOAD_TEMP_ROOT"])
    assert temp.is_dir() and not list(temp.iterdir())  # validated, then moved away
    assert category_for("ebook") == "ebooks" and category_for("course") == "courses"


def test_nginx_delivery_makes_premium_files_group_readable(tmp_path):
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp", group_readable=True)
    tmp, size, _ = storage.receive(io.BytesIO(b"%PDF-1.4 x"), 1000)
    storage.commit(tmp, "ebooks/abc/v1/f.pdf")
    path = storage.path("ebooks/abc/v1/f.pdf")
    assert stat.S_IMODE(path.stat().st_mode) == 0o640  # the Nginx group must read it
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o750
    assert not stat.S_IMODE(path.stat().st_mode) & 0o007  # never other users


def test_commit_is_atomic_across_filesystems(tmp_path, monkeypatch):
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp")
    tmp, _, _ = storage.receive(io.BytesIO(b"content"), 100)
    real_replace = os.replace
    calls = []

    def replace(src, dst):
        calls.append(src)
        if len(calls) == 1:  # the temp area lives on another disk
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    storage.commit(tmp, "downloads/x/v1/file.pdf")
    final = storage.path("downloads/x/v1/file.pdf")
    assert final.read_bytes() == b"content"
    assert not tmp.exists()
    assert not [p for p in final.parent.iterdir() if p.name.startswith(".commit-")]


def test_upload_size_limit_leaves_no_partial_file(tmp_path):
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp")
    with pytest.raises(StorageError, match="too_large"):
        storage.receive(io.BytesIO(b"x" * 5000), 1000)
    assert not list((tmp_path / "tmp").iterdir())


@pytest.mark.parametrize(
    "key",
    [
        "../etc/passwd",
        "ebooks/../../secret",
        "/etc/passwd",
        "ebooks//x",
        "Ebooks/X.pdf",
        "ebooks/x\x00.pdf",
        "..",
        "ebooks/.hidden",
        "",
    ],
)
def test_path_traversal_and_unsafe_keys_are_refused(tmp_path, key):
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp")
    with pytest.raises(StorageError):
        storage.path(key)


def test_symlink_escape_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.pdf").write_bytes(b"secret")
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp")
    storage.init_layout()
    (storage.root / "downloads" / "link").symlink_to(outside)
    validate_key("downloads/link/secret.pdf")  # the key itself looks harmless
    with pytest.raises(StorageError):
        storage.path("downloads/link/secret.pdf")


def test_stale_temp_uploads_are_cleaned_up(tmp_path, app):
    storage = LocalPrivateFileStorage(tmp_path / "res", tmp_path / "tmp")
    storage.init_layout()
    old = storage.temp_root / "upload-old"
    fresh = storage.temp_root / "upload-fresh"
    old.write_bytes(b"x")
    fresh.write_bytes(b"y")
    past = time.time() - 8 * 3600
    os.utime(old, (past, past))
    assert storage.stale_temp_files(6) == [old]
    assert storage.cleanup_temp(6) == 1
    assert not old.exists() and fresh.exists()


def test_cli_init_and_cleanup(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["storage", "init"])
    assert result.exit_code == 0, result.output
    root = Path(app.config["PRODUCT_FILES_ROOT"])
    for folder in ("ebooks", "workbooks", "templates", "courses", "downloads"):
        assert (root / folder).is_dir()
    assert stat.S_IMODE((Path(app.config["MEDIA_ROOT"]) / "private").stat().st_mode) == 0o700
    stale = Path(app.config["UPLOAD_TEMP_ROOT"]) / "upload-stale"
    stale.write_bytes(b"x")
    past = time.time() - 48 * 3600
    os.utime(stale, (past, past))
    result = runner.invoke(args=["storage", "cleanup-temp"])
    assert "Removed 1" in result.output and not stale.exists()


def test_request_bodies_spool_into_the_upload_temp_root(app, monkeypatch):
    import tempfile

    from app.storage.uploads import UploadRequest

    seen = {}
    real = tempfile.TemporaryFile

    def capture(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryFile", capture)
    with app.test_request_context("/"):
        stream = UploadRequest({})._get_file_stream(10 * 1024 * 1024, "application/pdf")
        stream.close()
        small = UploadRequest({})._get_file_stream(1024, "image/png")
    assert Path(seen["dir"]) == Path(app.config["UPLOAD_TEMP_ROOT"])
    assert isinstance(small, io.BytesIO)  # small bodies stay in memory


# ---- validation of written resource formats ---------------------------------------------


def test_docx_and_xlsx_are_accepted_and_dangerous_documents_refused(seeded, as_role, app):
    api = as_role("product_manager")
    pid = _create(api, "Planner", product_type="template")["id"]
    ok = _upload(api, pid, ooxml("docx"), "Planner.docx")
    assert ok.status_code == 201, ok.get_json()
    assert ok.get_json()["data"]["current_version"]["format"] == "docx"
    assert _upload(api, pid, ooxml("xlsx"), "Tracker.xlsx").status_code == 201
    refused = {
        "macro.docx": ooxml("docx", extra={"word/vbaProject.bin": b"\x00macro"}),
        "activex.docx": ooxml("docx", extra={"word/activeX/activeX1.xml": "<x/>"}),
        "ole.xlsx": ooxml("xlsx", extra={"xl/embeddings/oleObject1.bin": b"\xd0\xcf"}),
        "macro-type.xlsx": ooxml(
            "xlsx",
            content_types="<Types><Override ContentType="
            '"application/vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>',
        ),
        "broken.docx": ooxml("xlsx"),  # a workbook renamed to .docx: no word/document.xml
        "pdf-named.docx": minimal_pdf(),
        "exe.docx": b"MZ\x90\x00" + b"\x00" * 100,
    }
    for name, data in refused.items():
        res = _upload(api, pid, data, name)
        assert res.status_code == 400, (name, res.get_json())
    assert len(_versions(app)) == 2
    rejected = _audit(app, "product_file.rejected")
    assert len(rejected) == len(refused)
    assert {r.details["filename"] for r in rejected} >= {"macro.docx", "ole.xlsx"}


def test_accepted_formats_are_configurable(seeded, as_role, app):
    app.config["RESOURCE_FILE_FORMATS"] = ["pdf"]
    api = as_role("product_manager")
    pid = _create(api, "Planner", product_type="template")["id"]
    res = _upload(api, pid, ooxml("docx"), "Planner.docx")
    assert res.status_code == 400 and "Allowed: PDF" in str(res.get_json())
    assert _upload(api, pid).status_code == 201


def test_zip_bombs_are_refused(seeded, as_role):
    api = as_role("product_manager")
    pid = _create(api, "Pack", product_type="resource_pack")["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.txt", b"0" * (20 * 1024 * 1024))
    res = _upload(api, pid, buf.getvalue(), "pack.zip")
    assert res.status_code == 400 and "compression ratio" in str(res.get_json())


# ---- storage failures and upload errors -------------------------------------------------


def test_storage_failures_are_reported_and_logged(seeded, as_role, app, monkeypatch):
    api = as_role("product_manager")
    pid = _create(api, "Workbook")["id"]
    app.config["PRODUCT_FILES_MIN_FREE_MB"] = 10**9  # pretend the disk is full
    res = _upload(api, pid)
    assert res.status_code == 507 and res.get_json()["error"]["code"] == "storage_unavailable"
    app.config["PRODUCT_FILES_MIN_FREE_MB"] = 0

    def broken(self, stream, max_bytes):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(LocalPrivateFileStorage, "receive", broken)
    assert _upload(api, pid).status_code == 507
    failures = _audit(app, "product_file.storage_failed")
    assert [f.details["reason"] for f in failures] == [
        "not enough free disk space",
        "Input/output error",
    ]
    assert not _versions(app)
    admin = as_role("administrator", email="ops@example.org")
    errors = admin.get(f"{STORAGE}/upload-errors").get_json()["data"]
    assert {e["kind"] for e in errors} == {"storage failure"}
    assert all(e["area"] == "premium files" for e in errors)


def test_rejected_image_uploads_are_listed_as_upload_errors(seeded, as_role):
    api = as_role("super_admin", email="boss@example.org")
    res = api.upload("/api/v1/admin/media", b"not an image at all", "photo.jpg")
    assert res.status_code == 400
    errors = api.get(f"{STORAGE}/upload-errors").get_json()["data"]
    assert errors[0]["area"] == "images" and errors[0]["kind"] == "rejected"
    assert errors[0]["filename"] == "photo.jpg" and errors[0]["reason"]


def test_public_image_uploads_keep_working_with_categories(seeded, as_role, app):
    api = as_role("super_admin", email="boss@example.org")
    res = api.upload("/api/v1/admin/media", make_photo(800, 600), "cover.jpg", category="resources")
    assert res.status_code == 201, res.get_json()
    asset = res.get_json()["data"]
    assert asset["category"] == "resources"
    assert asset["image"]["src"].startswith("/media/")  # public URL layout unchanged
    listed = api.get("/api/v1/admin/media?category=resources").get_json()["data"]
    assert [a["id"] for a in listed] == [asset["id"]]
    assert api.get("/api/v1/admin/media?category=branding").get_json()["data"] == []
    bad = api.patch(f"/api/v1/admin/media/{asset['id']}", {"category": "nonsense"})
    assert bad.status_code == 400
    ok = api.patch(f"/api/v1/admin/media/{asset['id']}", {"category": "branding"})
    assert ok.get_json()["data"]["category"] == "branding"
    stats = api.get("/api/v1/admin/media/stats").get_json()["data"]
    assert {"key": "resources", "label": "Resource covers & previews"} in stats["categories"]
    public = Path(app.config["MEDIA_ROOT"]) / "public"
    private_root = Path(app.config["PRODUCT_FILES_ROOT"]).resolve()
    assert not any(private_root in p.resolve().parents for p in public.rglob("*"))


# ---- health ------------------------------------------------------------------------------


def test_storage_health_requires_permission(seeded, as_role):
    for role in ("content_writer", "product_manager"):
        assert as_role(role, email=f"{role}@example.org").get(STORAGE).status_code == 403
    for role in ("administrator", "website_manager"):
        assert as_role(role, email=f"{role}@example.org").get(STORAGE).status_code == 200


def test_storage_health_reports_problems(seeded, as_role, app, tmp_path):
    api = as_role("product_manager")
    pid = _create(api, "Workbook")["id"]
    assert _upload(api, pid).status_code == 201
    admin = as_role("super_admin", email="boss@example.org")
    app.test_cli_runner().invoke(args=["storage", "init"])
    report = admin.get(STORAGE).get_json()["data"]
    codes = {w["code"] for w in report["warnings"]}
    assert {a["key"] for a in report["areas"]} == {
        "media_public",
        "media_originals",
        "resources_private",
        "upload_temp",
    }
    assert "premium_missing" not in codes and report["integrity"]["premium_versions"] == 1
    assert report["tracked"]["premium_versions"] == 1
    assert "storage_key" not in json.dumps(report)

    root = Path(app.config["PRODUCT_FILES_ROOT"])
    os.chmod(root, 0o777)
    version = _versions(app)[0]
    (root / version.storage_key).unlink()
    (root / "downloads" / "stray.pdf").write_bytes(b"%PDF")
    app.config["PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"] = "/_protected_downloads"
    app.extensions.pop("tpa_private_files", None)
    os.chmod(root, 0o707)
    report = admin.get(STORAGE).get_json()["data"]
    codes = {w["code"]: w["level"] for w in report["warnings"]}
    assert codes["resources_private_world"] == "critical"
    assert codes["resources_accel_unreadable"] == "critical"  # Nginx couldn't read it
    assert codes["premium_missing"] == "critical"
    assert codes["premium_orphans"] == "info"
    assert report["status"] == "critical"
    assert report["integrity"]["missing_premium_versions"] == [version.id]
    os.chmod(root, 0o700)


def test_backup_status_is_monitored(seeded, as_role, app, tmp_path):
    admin = as_role("super_admin", email="boss@example.org")
    status_file = tmp_path / "backup-status.json"
    app.config["BACKUP_STATUS_FILE"] = str(status_file)

    def codes():
        report = admin.get(f"{STORAGE}?quick=1").get_json()["data"]
        return {w["code"] for w in report["warnings"]}

    assert "backup_missing" in codes()
    now = datetime.now(UTC)
    status_file.write_text(
        json.dumps({"status": "ok", "finished_at": now.isoformat(), "size_bytes": 1234})
    )
    assert not {c for c in codes() if c.startswith("backup")}
    old = (now - timedelta(hours=50)).isoformat()
    status_file.write_text(json.dumps({"status": "ok", "finished_at": old}))
    assert "backup_stale" in codes()
    status_file.write_text(
        json.dumps({"status": "failed", "finished_at": now.isoformat(), "message": "disk full"})
    )
    report = admin.get(f"{STORAGE}?quick=1").get_json()["data"]
    assert report["backup"]["ok"] is False
    assert any("disk full" in w["message"] for w in report["warnings"])


def test_storage_check_cli_exit_codes(app):
    runner = app.test_cli_runner()
    runner.invoke(args=["storage", "init"])
    app.config["STORAGE_WARN_FREE_PERCENT"] = 0
    app.config["STORAGE_CRITICAL_FREE_PERCENT"] = 0
    ok = runner.invoke(args=["storage", "check", "--quick"])
    assert ok.exit_code == 0, ok.output
    app.config["STORAGE_CRITICAL_FREE_PERCENT"] = 101  # every disk is "full"
    critical = runner.invoke(args=["storage", "check", "--json"])
    assert critical.exit_code == 2
    assert json.loads(critical.output)["status"] == "critical"


def test_production_refuses_unsafe_storage_layouts(tmp_path):
    class Cfg:
        MEDIA_ROOT = str(tmp_path / "media")
        PRODUCT_FILES_ROOT = str(tmp_path / "resources" / "private")
        UPLOAD_TEMP_ROOT = str(tmp_path / "temporary" / "uploads")
        PUBLISH_RELEASES_DIR = str(tmp_path / "site" / "releases")
        PUBLISH_CURRENT_LINK = str(tmp_path / "site" / "current")

    assert storage_layout_problems(Cfg) == []
    Cfg.PRODUCT_FILES_ROOT = str(tmp_path / "media" / "public" / "premium")
    problems = storage_layout_problems(Cfg)
    assert any("public web root" in p for p in problems)
    assert any("overlap MEDIA_ROOT" in p for p in problems)
    Cfg.PRODUCT_FILES_ROOT = str(tmp_path / "site" / "current" / "files")
    assert any("public web root" in p for p in storage_layout_problems(Cfg))
    Cfg.PRODUCT_FILES_ROOT = "relative/path"
    assert storage_layout_problems(Cfg) == ["PRODUCT_FILES_ROOT (must be an absolute path)"]
