"""Validation of private digital product files (PDF, EPUB and ZIP resource packs).

The decision is based on the actual content, not on the uploaded name or the
browser's declared type: the content is sniffed, the extension must agree with
it, and each format gets structural checks. ZIP-based formats are inspected
entry by entry with hard limits on entry count, total uncompressed size and
compression ratio (decompression bombs), and with path traversal, symlink,
encryption and executable checks. PDFs containing JavaScript or launch actions
are refused. A malware scanner can additionally be configured (see
``PRODUCT_FILES_SCAN_COMMAND``); it runs in the background worker, never in a
web request.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class FileFormat:
    key: str
    label: str
    extensions: tuple[str, ...]
    mime_type: str


FORMATS: dict[str, FileFormat] = {
    f.key: f
    for f in (
        FileFormat("pdf", "PDF", (".pdf",), "application/pdf"),
        FileFormat("epub", "EPUB", (".epub",), "application/epub+zip"),
        FileFormat("zip", "ZIP resource pack", (".zip",), "application/zip"),
    )
}

# What a resource pack may contain. Executables, scripts, nested archives and SVG
# (which can carry script) are never accepted.
ZIP_ENTRY_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".epub",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".txt",
        ".md",
        ".csv",
        ".rtf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".mp3",
        ".m4a",
        ".wav",
        ".mp4",
    }
)
_EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")
_PDF_DANGER = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)\b")


class FileRejected(ValueError):
    """The file is not acceptable; the message is safe to show to the uploader."""


@dataclass
class FileReport:
    format: FileFormat
    details: dict[str, Any] = field(default_factory=dict)


def safe_display_name(name: str | None, fallback: str = "file") -> str:
    """A display-only version of the uploaded file name (never used as a path)."""
    name = unicodedata.normalize("NFKC", name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    name = re.sub(r"[^\w.\- ()]+", "-", name, flags=re.UNICODE)
    return (name or fallback)[:200]


def _sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        # EPUB stores an uncompressed "mimetype" entry first.
        if head[30:38] == b"mimetype" and b"application/epub+zip" in head[:100]:
            return "epub"
        return "zip"
    return None


def _check_pdf(path: Path, limits: dict[str, int]) -> dict[str, Any]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(16)
        if not re.match(rb"%PDF-[12]\.\d", head):
            raise FileRejected("This is not a valid PDF file.")
        handle.seek(max(0, size - 2048))
        tail = handle.read()
    if b"%%EOF" not in tail:
        raise FileRejected("The PDF appears to be truncated or damaged (no end-of-file marker).")
    # Scan the whole file in overlapping windows for active content markers.
    overlap = 32
    with path.open("rb") as handle:
        previous = b""
        while chunk := handle.read(1024 * 1024):
            window = previous + chunk
            match = _PDF_DANGER.search(window)
            if match:
                kind = match.group(1).decode()
                raise FileRejected(
                    f"PDFs with active content ({kind}) are not accepted. Export the PDF again "
                    "without scripts, launch actions or embedded files."
                )
            previous = window[-overlap:]
    return {"pdf_version": head[5:8].decode("ascii", "replace")}


def _check_zip(path: Path, limits: dict[str, int], *, epub: bool) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise FileRejected("The archive is damaged or not a valid ZIP file.") from None
    with archive:
        infos = archive.infolist()
        if not infos:
            raise FileRejected("The archive is empty.")
        if len(infos) > limits["max_entries"]:
            raise FileRejected(f"The archive has more than {limits['max_entries']} entries.")
        declared = sum(i.file_size for i in infos)
        compressed = sum(i.compress_size for i in infos) or 1
        if declared > limits["max_uncompressed"]:
            raise FileRejected("The archive expands to more than the allowed size.")
        if declared / compressed > limits["max_ratio"]:
            raise FileRejected("The archive's compression ratio is suspiciously high.")
        files = 0
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name.replace("\\", "/")).parts
            if (
                not name
                or "\x00" in name
                or name.startswith(("/", "\\"))
                or re.match(r"^[A-Za-z]:", name)
                or ".." in parts
            ):
                raise FileRejected("The archive contains unsafe file paths.")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise FileRejected("The archive contains symbolic links, which are not allowed.")
            if info.flag_bits & 0x1:
                raise FileRejected("Encrypted archives are not accepted.")
            if info.is_dir():
                continue
            files += 1
            if epub:
                continue
            if parts and (parts[0] == "__MACOSX" or parts[-1] == ".DS_Store"):
                continue
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in ZIP_ENTRY_EXTENSIONS:
                raise FileRejected(
                    f"“{safe_display_name(name)}” is not an allowed file type inside a resource "
                    "pack (executables, scripts and nested archives are refused)."
                )
        # Read every entry with a hard cap: headers can lie about sizes, and this also
        # verifies each entry's CRC (file integrity).
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            seen = 0
            try:
                with archive.open(info) as member:
                    first = member.read(8)
                    if not epub and first.startswith(_EXECUTABLE_MAGIC):
                        raise FileRejected("The archive contains an executable file.")
                    seen += len(first)
                    while chunk := member.read(1024 * 1024):
                        seen += len(chunk)
                        if seen > info.file_size or total + seen > limits["max_uncompressed"]:
                            raise FileRejected("The archive expands beyond its declared size.")
            except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError):
                raise FileRejected("The archive is damaged (an entry failed its check).") from None
            except RuntimeError:  # encrypted entry
                raise FileRejected("Encrypted archives are not accepted.") from None
            total += seen
        if epub:
            names = {i.filename for i in infos}
            if infos[0].filename != "mimetype" or "META-INF/container.xml" not in names:
                raise FileRejected("This EPUB is missing its required structure.")
            if archive.read("mimetype").strip() != b"application/epub+zip":
                raise FileRejected("This EPUB has an invalid mimetype entry.")
        return {"entries": files, "uncompressed_bytes": total}


def validate_file(path: Path, original_name: str, limits: dict[str, int]) -> FileReport:
    """Validate a received file. Raises FileRejected with a user-facing message."""
    with path.open("rb") as handle:
        head = handle.read(120)
    if not head:
        raise FileRejected("The file is empty.")
    if head.startswith(_EXECUTABLE_MAGIC):
        raise FileRejected("Executable files are not accepted.")
    kind = _sniff(head)
    if kind is None or kind not in limits.get("formats", FORMATS):
        allowed = ", ".join(FORMATS[k].label for k in limits.get("formats", FORMATS))
        raise FileRejected(f"Unsupported file type. Allowed: {allowed}.")
    fmt = FORMATS[kind]
    suffix = Path(safe_display_name(original_name)).suffix.lower()
    if suffix not in fmt.extensions:
        raise FileRejected(
            f"The file content is {fmt.label}, but its name ends in “{suffix or 'nothing'}”. "
            f"Rename it to end in {fmt.extensions[0]}."
        )
    if kind == "pdf":
        details = _check_pdf(path, limits)
    else:
        details = _check_zip(path, limits, epub=kind == "epub")
    return FileReport(fmt, details)
