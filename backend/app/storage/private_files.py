"""Private storage for premium resource files (paid and free digital products).

This is deliberately separate from the media library storage: it has its own
root (``PRODUCT_FILES_ROOT``, e.g. ``/var/lib/tpa/resources/private``, outside
``MEDIA_ROOT`` and outside every web root), no public URL prefix, and random keys
that are never derived from uploaded file names. Files are only ever delivered by
the authenticated download endpoint (streamed by Flask, or handed to Nginx
through an ``internal`` X-Accel-Redirect location).

Layout: ``<category>/<file id>/v<n>/<random>.<ext>``, where the category folder
(``ebooks``, ``workbooks``, ``templates``, ``courses``, ``downloads``) follows the
product type; learners' assignment documents live under ``submissions/``. Keys written
before Batch 08 have no category folder; they stay valid because the full key is stored
with each version.

Uploads are received into ``UPLOAD_TEMP_ROOT`` (validated there), then moved into
place atomically. Permissions are owner-only, except that the group may read when
Nginx delivers the files (``PRODUCT_FILES_ACCEL_REDIRECT_PREFIX`` is set): the
Nginx worker must be able to open them, never write them, and other users get nothing.

How the Nginx worker gets read access (Batch 15.1): the server grants it on the storage
folder, either with a default ACL (``setfacl -d -m u:www-data:rX``) or by giving the
folder the Nginx group with the setgid bit. Both only apply to files *created* in that
folder. A file renamed into place from the temp area keeps the temp area's (empty) ACL
and group, which is how an upload ended up ``0640 tpa-staging:tpa-staging`` and
unreadable by ``www-data``. So when Nginx delivers files, ``commit`` always writes the
final file inside its destination folder (then renames it within that folder), and the
file inherits the folder's ACL and group; ``chmod 0640`` then sets the ACL mask to read
only. Nothing is ever world-readable and Nginx never gets write access.

``local`` is used in development and on the VPS. ``s3`` remains an adapter slot
that is not activated; primary storage stays on the server's own disk.
"""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from flask import current_app

from . import StorageError, validate_key

CHUNK = 1024 * 1024
TEMP_PREFIX = "upload-"

# Product type -> category folder (anything else goes to "downloads").
CATEGORY_FOLDERS = {
    "ebook": "ebooks",
    "workbook": "workbooks",
    "journal": "workbooks",
    "planner": "workbooks",
    "worksheet": "workbooks",
    "template": "templates",
    "checklist": "templates",
    "course": "courses",
}
# "submissions" holds learners' assignment documents (Batch 09.2); never product files.
CATEGORIES = ("ebooks", "workbooks", "templates", "courses", "downloads", "submissions")


def category_for(product_type: str) -> str:
    return CATEGORY_FOLDERS.get(product_type, "downloads")


class LocalPrivateFileStorage:
    name = "local"

    def __init__(
        self,
        root: str | os.PathLike,
        temp_root: str | os.PathLike | None = None,
        *,
        group_readable: bool = False,
    ):
        self.root = Path(root).resolve()
        self.temp_root = Path(temp_root).resolve() if temp_root else self.root / ".incoming"
        self.group_readable = group_readable
        self.dir_mode = 0o750 if group_readable else 0o700
        self.file_mode = 0o640 if group_readable else 0o600

    def _chmod_dir(self, path: Path) -> None:
        """Set the folder mode, keeping a setgid bit the server set (new files then get
        the folder's group, e.g. the Nginx group)."""
        keep = path.stat().st_mode & 0o2000 if self.group_readable else 0
        os.chmod(path, self.dir_mode | keep)

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._chmod_dir(self.root)

    def _ensure_temp(self) -> None:
        self.temp_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.temp_root, 0o700)

    def init_layout(self) -> list[Path]:
        """Create the root, the category folders and the temp area with safe modes."""
        self._ensure_root()
        self._ensure_temp()
        created = []
        for name in CATEGORIES:
            folder = self.root / name
            folder.mkdir(exist_ok=True)
            self._chmod_dir(folder)
            created.append(folder)
        return [self.root, self.temp_root, *created]

    def path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("Unsafe storage key.")
        return path

    def free_bytes(self) -> int:
        self._ensure_root()
        return shutil.disk_usage(self.root).free

    def writable(self) -> bool:
        try:
            self._ensure_root()
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".probe-")
            os.close(fd)
            os.unlink(tmp)
            return True
        except OSError:
            return False

    def receive(self, stream: BinaryIO, max_bytes: int) -> tuple[Path, int, str]:
        """Copy an upload into a private temporary file, enforcing the size limit.

        Returns (temporary path, size, sha256). The caller validates the file and
        then calls ``commit`` or ``discard``.
        """
        self._ensure_temp()
        fd, tmp = tempfile.mkstemp(dir=self.temp_root, prefix=TEMP_PREFIX)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError("too_large")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return Path(tmp), size, digest.hexdigest()

    def commit(self, tmp: Path, key: str) -> None:
        """Move a validated temporary file to its final key, atomically.

        Owner-only storage on the same filesystem: one rename. When Nginx delivers the
        files (``group_readable``), or the temp area is on another disk, the file is
        copied into a new file next to its destination and then renamed, so it inherits
        the destination folder's default ACL and group, and a partial file is never
        visible under the final key.
        """
        final = self.path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        for parent in [final.parent, *final.parent.parents]:
            if parent == self.root:
                break
            self._chmod_dir(parent)
        os.chmod(tmp, self.file_mode)
        if self.group_readable:
            # Must be created in its folder to get the Nginx reader's access (see above).
            self._copy_into_place(tmp, final)
            return
        try:
            os.replace(tmp, final)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            self._copy_into_place(tmp, final)

    def _copy_into_place(self, tmp: Path, final: Path) -> None:
        """Copy into a new file in the destination folder, then rename it over the key.

        A file created in the folder inherits its default ACL and (setgid) group; the
        rename within the folder keeps them and is atomic."""
        fd, staging = tempfile.mkstemp(dir=final.parent, prefix=".commit-")
        try:
            with os.fdopen(fd, "wb") as out, open(tmp, "rb") as src:
                shutil.copyfileobj(src, out, CHUNK)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(staging, self.file_mode)  # 0640: the ACL mask becomes read-only
            os.replace(staging, final)
        except BaseException:
            Path(staging).unlink(missing_ok=True)
            raise
        Path(tmp).unlink(missing_ok=True)

    def files_without_folder_access(self, limit: int = 1000) -> list[str]:
        """Stored files that did not get the access the storage folder grants new files.

        When the root has a default ACL, every file should carry an access ACL; when the
        root is setgid, every file should have the root's group. Files committed before
        Batch 15.1 (renamed in from the temp area) can miss both, and Nginx cannot read
        them. Returns their keys (an empty list when the folder grants nothing, or on
        systems without ACL support)."""
        try:
            root_stat = self.root.stat()
        except OSError:
            return []
        default_acl = _has_xattr(self.root, "system.posix_acl_default")
        setgid = bool(root_stat.st_mode & 0o2000)
        if not default_acl and not setgid:
            return []
        found = []
        for key in self.iter_keys(limit):
            path = self.root / key
            try:
                st = path.stat()
            except OSError:
                continue
            if (default_acl and not _has_xattr(path, "system.posix_acl_access")) or (
                setgid and st.st_gid != root_stat.st_gid
            ):
                found.append(key)
        return found

    @staticmethod
    def discard(tmp: Path) -> None:
        tmp.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        path = self.path(key)
        path.unlink(missing_ok=True)
        parent = path.parent
        while (
            parent != self.root
            and parent.parent != self.root  # keep the category folders
            and parent.is_dir()
            and not any(parent.iterdir())
        ):
            parent.rmdir()
            parent = parent.parent

    def iter_keys(self, limit: int = 100_000) -> Iterator[str]:
        """Stored keys (for orphan checks). Skips temp/probe files and the temp area."""
        if not self.root.is_dir():
            return
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            current = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and current / d != self.temp_root
            ]
            for name in filenames:
                if name.startswith("."):
                    continue
                yield (current / name).relative_to(self.root).as_posix()
                count += 1
                if count >= limit:
                    return

    def stale_temp_files(self, max_age_hours: int) -> list[Path]:
        cutoff = time.time() - max_age_hours * 3600
        found = []
        for area in {self.temp_root, self.root / ".incoming"}:
            if not area.is_dir():
                continue
            for entry in area.iterdir():
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        found.append(entry)
                except OSError:
                    continue
        return found

    def cleanup_temp(self, max_age_hours: int) -> int:
        removed = 0
        for entry in self.stale_temp_files(max_age_hours):
            try:
                entry.unlink()
                removed += 1
            except OSError:
                continue
        return removed


def _has_xattr(path: Path, name: str) -> bool:
    try:
        os.getxattr(path, name)
        return True
    except (OSError, AttributeError):  # no such attribute, no ACL support, not Linux
        return False


class S3PrivateFileStorage:  # pragma: no cover - adapter slot, not activated
    name = "s3"

    def __init__(self, *_args, **_kwargs):
        raise StorageError(
            "PRODUCT_FILES_STORAGE=s3 is not activated. Premium files are stored on the "
            "server's own disk (PRODUCT_FILES_STORAGE=local)."
        )


def get_private_storage():
    app = current_app._get_current_object()
    cached = app.extensions.get("tpa_private_files")
    if cached is None:
        backend = app.config.get("PRODUCT_FILES_STORAGE", "local")
        if backend == "local":
            cached = LocalPrivateFileStorage(
                app.config["PRODUCT_FILES_ROOT"],
                app.config.get("UPLOAD_TEMP_ROOT") or None,
                group_readable=bool(app.config.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX")),
            )
        elif backend == "s3":
            cached = S3PrivateFileStorage()
        else:
            raise StorageError(f"Unknown PRODUCT_FILES_STORAGE '{backend}'.")
        app.extensions["tpa_private_files"] = cached
    return cached
