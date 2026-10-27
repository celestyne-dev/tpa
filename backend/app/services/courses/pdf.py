"""A tiny single-page PDF writer for completion certificates.

It uses the PDF standard fonts (Helvetica, Helvetica-Bold) with WinAnsi encoding, so no
font files or extra packages are needed on the server. Text outside Windows-1252 is
transliterated where possible (é stays é, "ł" becomes "l"); the online verification page
always shows the exact name.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Advance widths (1/1000 em) for ASCII 32..126, from the Adobe core font metrics.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]  # fmt: skip
_HELVETICA_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]  # fmt: skip
FONTS = {
    "regular": ("F1", "Helvetica", _HELVETICA),
    "bold": ("F2", "Helvetica-Bold", _HELVETICA_BOLD),
}


def to_winansi(text: str) -> bytes:
    out = bytearray()
    for char in text:
        try:
            out += char.encode("cp1252")
        except UnicodeEncodeError:
            plain = unicodedata.normalize("NFKD", char).encode("ascii", "ignore")
            out += plain or b"?"
    return bytes(out)


def text_width(text: str, font: str, size: float) -> float:
    widths = FONTS[font][2]
    total = 0
    for byte in to_winansi(text):
        total += widths[byte - 32] if 32 <= byte <= 126 else 556
    return total * size / 1000


def wrap(text: str, font: str, size: float, max_width: float, max_lines: int = 3) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_width(candidate, font, size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "…"
    return lines


_FONT = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"


def _escape(raw: bytes) -> bytes:
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


@dataclass
class Page:
    width: float = 792  # US Letter, landscape
    height: float = 612

    def __post_init__(self):
        self.ops: list[bytes] = []

    def text(
        self,
        value: str,
        *,
        y: float,
        size: float,
        font: str = "regular",
        x: float | None = None,
        gray: float = 0.15,
    ) -> None:
        name = FONTS[font][0]
        if x is None:  # centred
            x = (self.width - text_width(value, font, size)) / 2
        self.ops.append(
            b"BT %.3f g /%s %.1f Tf %.2f %.2f Td (" % (gray, name.encode(), size, x, y)
            + _escape(to_winansi(value))
            + b") Tj ET"
        )

    def rect(
        self, x: float, y: float, w: float, h: float, *, line: float = 1, rgb=(0.36, 0.45, 0.36)
    ) -> None:
        self.ops.append(
            b"%.3f %.3f %.3f RG %.2f w %.2f %.2f %.2f %.2f re S" % (*rgb, line, x, y, w, h)
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        width: float = 0.8,
        rgb=(0.75, 0.66, 0.42),
    ) -> None:
        self.ops.append(
            b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (*rgb, width, x1, y1, x2, y2)
        )

    def render(self, title: str = "") -> bytes:
        stream = b"\n".join(self.ops)
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (self.width, self.height),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            _FONT % b"Helvetica",
            _FONT % b"Helvetica-Bold",
            b"<< /Title (" + _escape(to_winansi(title)) + b") /Producer (Think Positive Always) >>",
        ]
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for offset in offsets:
            out += b"%010d 00000 n \n" % offset
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1,
            len(objects),
            xref,
        )
        return bytes(out)
