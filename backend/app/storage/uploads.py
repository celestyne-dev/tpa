"""Request bodies with uploaded files are spooled into ``UPLOAD_TEMP_ROOT``.

Werkzeug normally spools large multipart uploads to the system temp directory.
Keeping them in the configured upload area means they are on the storage disk
(not a small /tmp), owner-only, covered by the disk-space checks and removed by
``flask storage cleanup-temp`` if a worker dies mid-request.
"""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import IO

from flask import Request, current_app

IN_MEMORY_LIMIT = 500 * 1024  # same threshold Werkzeug uses


class UploadRequest(Request):
    def _get_file_stream(
        self,
        total_content_length: int | None,
        content_type: str | None,
        filename: str | None = None,
        content_length: int | None = None,
    ) -> IO[bytes]:
        if total_content_length is not None and total_content_length <= IN_MEMORY_LIMIT:
            return BytesIO()
        root = current_app.config.get("UPLOAD_TEMP_ROOT")
        if not root:
            return tempfile.TemporaryFile("rb+")
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        # An unnamed temporary file: removed by the OS as soon as it is closed.
        return tempfile.TemporaryFile("rb+", dir=path, prefix="request-")
