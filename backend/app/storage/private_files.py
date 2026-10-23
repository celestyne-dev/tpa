"""Private storage for paid digital product files.

This is deliberately separate from the media library storage: it has its own
root (``PRODUCT_FILES_ROOT``, outside ``MEDIA_ROOT`` and outside the frontend
build), no public URL prefix, owner-only permissions, and random keys that are
never derived from uploaded file names. Files are only ever delivered by the
authenticated download endpoint (streamed by Flask, or handed to Nginx through
an ``internal`` X-Accel-Redirect location).

``local`` is used in development and on a single VPS. ``s3`` is an adapter slot
for private S3-compatible object storage (bucket without public access, served
through the same gateway); it is not activated in this release and local tests
never need S3 credentials.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from flask import current_app

from . import StorageError, validate_key

CHUNK = 1024 * 1024


class LocalPrivateFileStorage:
    name = "local"

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

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
        self._ensure_root()
        tmp_dir = self.root / ".incoming"
        tmp_dir.mkdir(exist_ok=True)
        os.chmod(tmp_dir, 0o700)
        fd, tmp = tempfile.mkstemp(dir=tmp_dir, prefix="upload-")
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
            os.chmod(tmp, 0o600)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return Path(tmp), size, digest.hexdigest()

    def commit(self, tmp: Path, key: str) -> None:
        final = self.path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        for parent in [final.parent, *final.parent.parents]:
            if parent == self.root:
                break
            os.chmod(parent, 0o700)
        os.replace(tmp, final)

    @staticmethod
    def discard(tmp: Path) -> None:
        tmp.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        path = self.path(key)
        path.unlink(missing_ok=True)
        parent = path.parent
        while parent != self.root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


class S3PrivateFileStorage:  # pragma: no cover - adapter slot, not activated in this release
    name = "s3"

    def __init__(self, *_args, **_kwargs):
        raise StorageError(
            "PRODUCT_FILES_STORAGE=s3 is not activated yet. Use 'local'; the S3 adapter will "
            "implement the same receive/commit/path/exists/delete interface against a private "
            "bucket and keep serving files through the authenticated download endpoint."
        )


def get_private_storage():
    app = current_app._get_current_object()
    cached = app.extensions.get("tpa_private_files")
    if cached is None:
        backend = app.config.get("PRODUCT_FILES_STORAGE", "local")
        if backend == "local":
            cached = LocalPrivateFileStorage(app.config["PRODUCT_FILES_ROOT"])
        elif backend == "s3":
            cached = S3PrivateFileStorage()
        else:
            raise StorageError(f"Unknown PRODUCT_FILES_STORAGE '{backend}'.")
        app.extensions["tpa_private_files"] = cached
    return cached
