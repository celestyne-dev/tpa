"""Structural safety inspection of uploaded PDFs.

The PDF is parsed with ``pypdf`` and every object it contains is inspected, rather
than searching the raw bytes for names such as ``/JS``: those bytes occur by chance
inside compressed images, fonts and other binary streams, which made ordinary
printable workbooks look dangerous. Stream *data* is never searched; stream
*dictionaries* are.

Refused (the document can run, open or carry something other than pages):

* JavaScript actions and the document-level JavaScript name tree (``/JS``,
  ``/JavaScript``), and XFA forms, which carry their own scripts;
* launch actions and every other action that is not on a short allow-list (form
  submission, data import, links into other files, multimedia, 3D and so on);
* anything that runs automatically (``/OpenAction``, ``/AA``) other than moving to
  a page or a view;
* links whose address uses a scheme other than http, https or mailto;
* attachments and associated files (``/EmbeddedFiles``, ``/EF``, ``/AF``, file
  attachment annotations), rich media, movies, sound, screen and 3D content;
* encrypted PDFs, PDFs without a valid catalogue, and anything the parser can't
  read completely within the limits below (it fails closed).

Accepted: embedded fonts, images (JPEG and other compressed streams), text,
flattened pages, page links, bookmarks, and printable forms without actions.

Every object listed in the cross-reference table is inspected, whether or not it
is reachable from the catalogue, and so are objects present in the file but left
out of the table (for example an attachment "deleted" by an incremental save, which
a viewer repairing the file could still pick up). Name obfuscation (``/J#53``) is
decoded by the parser before comparison.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import IO, Any

from pypdf import PdfReader
from pypdf.errors import DependencyError
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    read_object,
)

# Bounds on the inspection itself (the upload size limit applies before this).
MAX_OBJECTS = 300_000
MAX_ORPHANS = 5_000
MAX_SECONDS = 30.0
MAX_ACTION_CHAIN = 200

# Keys that only exist to carry scripts, attachments or rich media.
_FORBIDDEN_KEYS = {
    "/JS": "JavaScript",
    "/JavaScript": "JavaScript",
    "/XFA": "XFA form scripts",
    "/EmbeddedFiles": "embedded files",
    "/EF": "embedded files",
    "/AF": "embedded files",
    "/RichMediaContent": "rich media",
    "/RichMediaSettings": "rich media",
    "/3DD": "3D content",
}
# /Type or /Subtype values of objects that are attachments or multimedia.
_FORBIDDEN_TYPES = {
    "/EmbeddedFile": "embedded files",
    "/FileAttachment": "embedded files",
    "/RichMedia": "rich media",
    "/RichMediaContent": "rich media",
    "/Movie": "multimedia",
    "/Sound": "multimedia",
    "/Screen": "multimedia",
    "/Rendition": "multimedia",
    "/MediaClip": "multimedia",
    "/3D": "3D content",
}
# Action types: what is refused gets a readable name; anything not allowed is refused.
_ACTION_LABELS = {
    "/JavaScript": "JavaScript",
    "/Launch": "launch actions",
    "/ImportData": "data import actions",
    "/SubmitForm": "form submission",
    "/GoToR": "links to other files",
    "/GoToE": "embedded files",
    "/Rendition": "multimedia",
    "/Movie": "multimedia",
    "/Sound": "multimedia",
    "/RichMediaExecute": "rich media",
    "/GoTo3DView": "3D content",
}
_SAFE_ACTIONS = frozenset(
    {"/GoTo", "/URI", "/Named", "/Thread", "/ResetForm", "/Hide", "/SetOCGState", "/Trans"}
)
# Actions allowed to run by themselves (on open, page open, field events).
_SAFE_AUTOMATIC = frozenset({"/GoTo", "/Named", "/SetOCGState", "/Trans", "/Hide"})
_SAFE_URI_SCHEMES = frozenset({"http", "https", "mailto"})
_URI_SCHEME = re.compile(r"^\s*([A-Za-z][A-Za-z0-9+.\-]*):")
_OBJ_HEADER = re.compile(rb"(?<![0-9])(\d{1,10})[\x00\t\n\f\r ]+(\d{1,5})[\x00\t\n\f\r ]+obj\b")


class PdfUnsafe(Exception):
    """Active or embedded content was found; ``label`` names it for the uploader."""

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label


class PdfUnreadable(Exception):
    """The PDF could not be inspected completely (fail closed)."""

    def __init__(self, reason: str, *, encrypted: bool = False):
        super().__init__(reason)
        self.encrypted = encrypted


class _Inspector:
    def __init__(self, reader: PdfReader, handle: IO[bytes], size: int):
        self.reader = reader
        self.handle = handle
        self.size = size
        self.deadline = time.monotonic() + MAX_SECONDS
        self.inspected = 0

    # -- bounds --------------------------------------------------------------------
    def _tick(self) -> None:
        self.inspected += 1
        if self.inspected > MAX_OBJECTS or time.monotonic() > self.deadline:
            raise PdfUnreadable("too complex to inspect")

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, IndirectObject):
            self._tick()
            return value.get_object()
        return value

    # -- the walk ------------------------------------------------------------------
    def run(self) -> int:
        trailer = self.reader.trailer
        if trailer.get("/Encrypt") is not None or self.reader.is_encrypted:
            raise PdfUnreadable("encrypted", encrypted=True)
        root = self._resolve(trailer.get("/Root"))
        if not isinstance(root, DictionaryObject) or root.get("/Type") != "/Catalog":
            raise PdfUnreadable("no document catalogue")
        if not isinstance(self._resolve(root.get("/Pages")), DictionaryObject):
            raise PdfUnreadable("no page tree")

        known: set[int] = set()
        self._inspect(trailer)
        for generation, entries in self.reader.xref.items():
            free = self.reader.xref_free_entry.get(generation, {})
            for number in entries:
                if free.get(number):
                    continue
                known.add(number)
                self._inspect(self._resolve(IndirectObject(number, generation, self.reader)))
        for number in self.reader.xref_objStm:
            known.add(number)
            self._inspect(self._resolve(IndirectObject(number, 0, self.reader)))
        self._inspect_orphans(known)
        return len(known)

    def _inspect(self, obj: Any) -> None:
        """Inspect one object and everything nested in it directly (not references)."""
        stack = [obj]
        while stack:
            item = stack.pop()
            if isinstance(item, DictionaryObject):  # includes stream dictionaries
                self._tick()
                self._check_dict(item)
                stack.extend(v for v in item.values() if not isinstance(v, IndirectObject))
            elif isinstance(item, ArrayObject):
                self._tick()
                stack.extend(v for v in item if not isinstance(v, IndirectObject))

    def _check_dict(self, d: DictionaryObject) -> None:
        for key in d:
            if key in _FORBIDDEN_KEYS:
                raise PdfUnsafe(_FORBIDDEN_KEYS[key])
        for key in ("/Type", "/Subtype"):
            value = d.get(key)
            if isinstance(value, NameObject) and value in _FORBIDDEN_TYPES:
                raise PdfUnsafe(_FORBIDDEN_TYPES[value])
        kind = d.get("/S")
        if isinstance(kind, NameObject) and kind in _ACTION_LABELS:
            raise PdfUnsafe(_ACTION_LABELS[kind])
        if d.get("/Type") == "/Action":
            self._check_action(d, automatic=False)
        if "/A" in d:
            self._check_action(self._resolve(d["/A"]), automatic=False)
        if "/OpenAction" in d:
            self._check_action(self._resolve(d["/OpenAction"]), automatic=True)
        if "/AA" in d:
            triggers = self._resolve(d["/AA"])
            if isinstance(triggers, DictionaryObject):
                for trigger in triggers.values():
                    self._check_action(self._resolve(trigger), automatic=True)
            elif triggers is not None:
                raise PdfUnreadable("invalid additional-actions entry")

    def _check_action(self, action: Any, *, automatic: bool) -> None:
        """Check an action and the chain that follows it (``/Next``)."""
        pending = [action]
        seen: set[int] = set()
        while pending:
            if len(seen) > MAX_ACTION_CHAIN:
                raise PdfUnreadable("action chain too long")
            item = self._resolve(pending.pop())
            if not isinstance(item, DictionaryObject) or "/S" not in item:
                # Destinations (arrays, names) and structure attributes are not actions.
                continue
            if id(item) in seen:
                continue
            seen.add(id(item))
            kind = item.get("/S")
            allowed = _SAFE_AUTOMATIC if automatic else _SAFE_ACTIONS
            if not isinstance(kind, NameObject) or kind not in allowed:
                label = _ACTION_LABELS.get(str(kind))
                raise PdfUnsafe(label or ("automatic actions" if automatic else "actions"))
            if kind == "/URI":
                self._check_uri(self._resolve(item.get("/URI")))
            if kind == "/Thread" and "/F" in item:
                raise PdfUnsafe("links to other files")
            following = self._resolve(item.get("/Next"))
            if isinstance(following, ArrayObject):
                pending.extend(following)
            elif following is not None:
                pending.append(following)

    def _check_uri(self, uri: Any) -> None:
        if isinstance(uri, bytes):
            uri = uri.decode("latin-1")
        if not isinstance(uri, str):
            raise PdfUnsafe("links")
        scheme = _URI_SCHEME.match(uri)
        if scheme and scheme.group(1).lower() not in _SAFE_URI_SCHEMES:
            raise PdfUnsafe(f"{scheme.group(1).lower()}: links")

    # -- objects outside the cross-reference table ------------------------------------
    def _inspect_orphans(self, known: set[int]) -> None:
        offsets: set[int] = set()
        overlap = 64 * 1024  # a header split across two reads is still seen
        position = 0
        self.handle.seek(0)
        previous = b""
        while chunk := self.handle.read(1024 * 1024):
            window = previous + chunk
            base = position - len(previous)
            for match in _OBJ_HEADER.finditer(window):
                start = base + match.start()
                if int(match.group(1)) not in known:
                    offsets.add(start)
                    if len(offsets) > MAX_ORPHANS:
                        raise PdfUnreadable("too many unlisted objects")
            position += len(chunk)
            previous = window[-overlap:]
            if time.monotonic() > self.deadline:
                raise PdfUnreadable("too complex to inspect")
        stream = self.reader.stream
        for offset in sorted(offsets):
            try:
                stream.seek(offset)
                self.reader.read_object_header(stream)
                obj = read_object(stream, self.reader)
            except (PdfUnsafe, PdfUnreadable):
                raise
            except Exception:  # noqa: BLE001 - chance digits inside binary data
                continue
            self._inspect(obj)


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Inspect a PDF; raises ``PdfUnsafe`` or ``PdfUnreadable``."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        try:
            reader = PdfReader(handle, strict=False, root_object_recovery_limit=0)
            objects = _Inspector(reader, handle, size).run()
        except (PdfUnsafe, PdfUnreadable):
            raise
        except Exception as exc:  # noqa: BLE001 - anything else means we couldn't inspect
            # Without the optional crypto library pypdf can't even open AES-encrypted files.
            encrypted = isinstance(exc, DependencyError) or "encrypt" in str(exc).lower()
            raise PdfUnreadable(type(exc).__name__, encrypted=encrypted) from exc
    return {"objects": objects}
