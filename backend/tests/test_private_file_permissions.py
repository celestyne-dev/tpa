"""Batch 15.1: premium files must be readable by the Nginx worker (X-Accel-Redirect), never
by other users, and never writable by Nginx.

Production grants Nginx read access with a default ACL on the private storage folder
(``setfacl -d -m u:www-data:rX``). A default ACL only applies to files *created* in the
folder, and uploads used to be renamed in from the temp area, so a new PDF arrived as
``0640 tpa-staging:tpa-staging`` with no ACL and Nginx could not open it. These tests
set real POSIX ACLs (through extended attributes, no extra tools) and real setgid
folders, and skip only where the filesystem does not support them.
"""

from __future__ import annotations

import errno
import io
import os
import stat
import struct
from pathlib import Path

import pytest

from app.extensions import db
from app.models import DownloadGrant, ProductFileVersion
from app.storage.private_files import LocalPrivateFileStorage

from .test_commerce_checkout import _library_file, _paid_order, shop  # noqa: F401

NGINX_UID = 65534  # any other user stands in for www-data ("nobody")
READ, WRITE, EXEC = 4, 2, 1
USER_OBJ, USER, GROUP_OBJ, MASK, OTHER = 0x01, 0x02, 0x04, 0x10, 0x20
UNDEFINED = 0xFFFFFFFF
KEY = "ebooks/abc/v1/f.pdf"


def _acl(entries):
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, perm, uid) for tag, perm, uid in entries
    )


def _parse(raw):
    return [struct.unpack_from("<HHI", raw, 4 + 8 * i) for i in range((len(raw) - 4) // 8)]


def _grant_nginx_default_acl(folder: Path) -> None:
    """The equivalent of ``setfacl -d -m u:www-data:rX folder``."""
    acl = _acl(
        [
            (USER_OBJ, READ | WRITE | EXEC, UNDEFINED),
            (USER, READ | EXEC, NGINX_UID),
            (GROUP_OBJ, READ | EXEC, UNDEFINED),
            (MASK, READ | EXEC, UNDEFINED),
            (OTHER, 0, UNDEFINED),
        ]
    )
    try:
        os.setxattr(folder, "system.posix_acl_default", acl)
    except (OSError, AttributeError) as exc:
        if isinstance(exc, AttributeError) or exc.errno in (errno.ENOTSUP, errno.EPERM):
            pytest.skip("this filesystem does not support POSIX ACLs")
        raise


def _nginx_permissions(path: Path) -> int | None:
    """What the Nginx user may do with the file: its ACL entry limited by the mask."""
    try:
        entries = _parse(os.getxattr(path, "system.posix_acl_access"))
    except OSError:
        return None
    user = next((perm for tag, perm, uid in entries if tag == USER and uid == NGINX_UID), None)
    mask = next((perm for tag, perm, _ in entries if tag == MASK), 7)
    return None if user is None else user & mask


def _storage(tmp_path, *, acl=False):
    root = tmp_path / "resources" / "private"
    root.mkdir(parents=True)
    if acl:
        _grant_nginx_default_acl(root)
    storage = LocalPrivateFileStorage(root, tmp_path / "tmp-uploads", group_readable=True)
    storage.init_layout()
    return storage


def _commit(storage, data=b"%PDF-1.4 premium", key=KEY):
    tmp, _, _ = storage.receive(io.BytesIO(data), 10_000)
    storage.commit(tmp, key)
    return storage.path(key)


def test_new_uploads_inherit_the_folders_nginx_read_acl(tmp_path):
    storage = _storage(tmp_path, acl=True)
    path = _commit(storage)
    assert path.read_bytes() == b"%PDF-1.4 premium"
    # The bug: renamed in from the temp area, the file had no ACL at all.
    assert _nginx_permissions(path) == READ  # read only: never write or execute
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o640 and not mode & 0o007  # nothing for other users
    # Folders created for the file let Nginx traverse them, not write.
    assert _nginx_permissions(path.parent) == READ | EXEC
    assert not stat.S_IMODE(path.parent.stat().st_mode) & 0o007
    # The temp area stays owner-only and leaves nothing behind.
    assert stat.S_IMODE(storage.temp_root.stat().st_mode) == 0o700
    assert not list(storage.temp_root.iterdir())
    assert not [p for p in path.parent.iterdir() if p.name.startswith(".commit-")]


def test_a_new_version_replacing_a_key_also_gets_the_acl(tmp_path):
    storage = _storage(tmp_path, acl=True)
    _commit(storage, b"%PDF-1.4 first")
    path = _commit(storage, b"%PDF-1.4 second")
    assert path.read_bytes() == b"%PDF-1.4 second" and _nginx_permissions(path) == READ


def test_setgid_folder_group_is_inherited_and_kept(tmp_path):
    groups = [g for g in os.getgroups() if g != os.getgid()]
    if not groups:
        pytest.skip("the test user belongs to no second group")
    root = tmp_path / "resources" / "private"
    root.mkdir(parents=True)
    os.chown(root, -1, groups[0])
    os.chmod(root, 0o2750)  # the Nginx group, setgid: new files get that group
    storage = LocalPrivateFileStorage(root, tmp_path / "tmp-uploads", group_readable=True)
    storage.init_layout()
    path = _commit(storage)
    assert path.stat().st_gid == groups[0]  # not the uploader's own group
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    # The app's own chmod calls keep the setgid bit on the root and the new folders.
    assert root.stat().st_mode & 0o2000 and path.parent.stat().st_mode & 0o2000
    assert storage.files_without_folder_access() == []


def test_files_that_missed_the_folder_access_are_reported(tmp_path):
    storage = _storage(tmp_path, acl=True)
    good = _commit(storage)
    # A file renamed in from elsewhere, as uploads were before this fix.
    outside = tmp_path / "elsewhere.pdf"
    outside.write_bytes(b"%PDF-1.4 old")
    os.chmod(outside, 0o640)
    old = storage.path("ebooks/old/v1/old.pdf")
    old.parent.mkdir(parents=True)
    os.replace(outside, old)
    assert _nginx_permissions(old) is None
    assert storage.files_without_folder_access() == ["ebooks/old/v1/old.pdf"]
    assert _nginx_permissions(good) == READ


def test_owner_only_storage_without_nginx_is_unchanged(tmp_path):
    root = tmp_path / "private"
    storage = LocalPrivateFileStorage(root, tmp_path / "tmp")
    path = _commit(storage)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert storage.files_without_folder_access() == []  # the folder grants nothing


def test_storage_health_reports_files_nginx_cannot_read(seeded, as_role, app, tmp_path):
    root = Path(app.config["PRODUCT_FILES_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    _grant_nginx_default_acl(root)
    app.config["PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"] = "/_protected_downloads"
    app.extensions.pop("tpa_private_files", None)
    with app.app_context():
        from app.storage.private_files import get_private_storage

        storage = get_private_storage()
        storage.init_layout()
        _commit(storage)
        outside = tmp_path / "x.pdf"
        outside.write_bytes(b"%PDF-1.4 old")
        stale = storage.path("ebooks/old/v1/old.pdf")
        stale.parent.mkdir(parents=True)
        os.replace(outside, stale)
    report = as_role("super_admin").get("/api/v1/admin/storage").get_json()["data"]
    [warning] = [w for w in report["warnings"] if w["code"] == "resources_files_unreadable"]
    assert warning["level"] == "critical" and "1 premium file" in warning["message"]
    assert "ebooks/old/v1/old.pdf" in warning["message"]


def test_nginx_delivery_answers_with_the_internal_location_only(shop, client):  # noqa: F811
    """With PRODUCT_FILES_ACCEL_REDIRECT_PREFIX set, Flask checks the link and hands the
    file to Nginx's internal location: no file bytes, no storage path in the public URL."""
    app = shop["app"]
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    url = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    app.config["PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"] = "/_protected_downloads"
    app.extensions.pop("tpa_private_files", None)
    with app.app_context():
        grant = db.session.scalar(db.select(DownloadGrant))
        key = db.session.get(ProductFileVersion, grant.file_version_id).storage_key
    assert key not in url and "resources" not in url
    res = shopper.get(url)
    assert res.status_code == 200
    assert res.headers["X-Accel-Redirect"] == f"/_protected_downloads/{key}"
    assert res.data == b""  # Nginx sends the bytes, from the internal location
    assert res.headers["Content-Disposition"].startswith("attachment;")
    assert res.headers["Cache-Control"] == "private, no-store"
    # Refused requests never reach the internal location.
    assert client.get(url).status_code == 403
    assert "X-Accel-Redirect" not in client.get(url).headers
