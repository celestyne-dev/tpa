"""The certificate of completion as a printable, one-page A4 landscape PDF.

Pure rendering: it takes the certificate's snapshot (never the live learner or course) and
returns bytes, so it needs no database or request and can be tested on its own.

- Fonts: DejaVu Serif (regular and bold, embedded and subset; licence in
  ``app/assets/fonts``). It covers Latin (including Vietnamese, Polish, Turkish, Icelandic
  and other accented letters), Greek and Cyrillic, so most names print exactly.
- Names that need a script the font lacks or right-to-left / complex shaping (Arabic,
  Hebrew, Devanagari, Chinese, Japanese, Korean...) print as close as possible and the page
  says that the verification address shows the exact name.
- The verification URL is printed and encoded in a QR code.
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
SERIF, SERIF_BOLD = "TPASerif", "TPASerif-Bold"

# Think Positive Always colours (frontend/src/assets/styles/globals.css).
SAGE = HexColor("#364631")
SAGE_SOFT = HexColor("#57704b")
GOLD = HexColor("#b08d45")
GOLD_LIGHT = HexColor("#dcc28a")
CREAM = HexColor("#faf6ee")
CHARCOAL = HexColor("#24221f")
MUTED = HexColor("#5b574f")

# Scripts that need right-to-left ordering or glyph shaping, which this renderer can't do.
_COMPLEX = (
    (0x0590, 0x08FF),  # Hebrew, Arabic, Syriac, Thaana, NKo...
    (0x0900, 0x0DFF),  # Indic scripts
    (0x0E00, 0x0FFF),  # Thai, Lao, Tibetan
    (0x1000, 0x109F),  # Myanmar
    (0xFB1D, 0xFDFF),  # Hebrew and Arabic presentation forms
    (0xFE70, 0xFEFF),
)


@dataclass(frozen=True)
class CertificateContent:
    recipient_name: str
    course_title: str
    code: str
    issued_at: datetime
    completed_at: datetime | None
    verify_url: str
    issuer: str = "Think Positive Always"
    signatory_name: str = ""
    signatory_title: str = ""
    statement: str = ""


@cache
def _fonts() -> set[int]:
    """Register the embedded fonts once; return the code points the regular face covers."""
    regular = TTFont(SERIF, str(FONT_DIR / "DejaVuSerif.ttf"))
    pdfmetrics.registerFont(regular)
    pdfmetrics.registerFont(TTFont(SERIF_BOLD, str(FONT_DIR / "DejaVuSerif-Bold.ttf")))
    return set(regular.face.charToGlyph)


def printable(text: str) -> tuple[str, bool]:
    """(text the font can print, whether it is exactly the original)."""
    covered = _fonts()
    out, exact = [], True
    for char in unicodedata.normalize("NFC", text):
        code = ord(char)
        if any(low <= code <= high for low, high in _COMPLEX) or (
            code not in covered and not char.isspace()
        ):
            exact = False
            plain = unicodedata.normalize("NFKD", char)
            plain = "".join(c for c in plain if ord(c) in covered and not unicodedata.combining(c))
            out.append(plain)
        else:
            out.append(char)
    result = " ".join("".join(out).split())
    return result, exact


def _fit(text: str, font: str, size: float, width: float, minimum: float) -> float:
    """The largest size up to ``size`` (not below ``minimum``) at which ``text`` fits."""
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _wrap(text: str, font: str, size: float, width: float, max_lines: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and pdfmetrics.stringWidth(f"{last}…", font, size) > width:
            last = last[:-1]
        lines[-1] = f"{last.rstrip(' ,.;:')}…"
    return lines


def _date(value: datetime) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _spaced(text: str) -> str:
    return " ".join(text.upper())


def render(content: CertificateContent) -> bytes:
    _fonts()
    buffer = io.BytesIO()
    width, height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(width, height), pageCompression=1)
    pdf.setTitle(f"Certificate of Completion — {content.course_title}")
    pdf.setAuthor(content.issuer)
    pdf.setSubject(f"Certificate {content.code}")
    pdf.setCreator(content.issuer)

    # Page, double frame and corner accents.
    pdf.setFillColor(CREAM)
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    pdf.setStrokeColor(SAGE)
    pdf.setLineWidth(2.2)
    pdf.rect(26, 26, width - 52, height - 52, stroke=1, fill=0)
    pdf.setStrokeColor(GOLD_LIGHT)
    pdf.setLineWidth(0.8)
    pdf.rect(36, 36, width - 72, height - 72, stroke=1, fill=0)
    pdf.setFillColor(GOLD)
    for x, y in ((36, 36), (width - 36, 36), (36, height - 36), (width - 36, height - 36)):
        pdf.circle(x, y, 3.2, stroke=0, fill=1)

    center = width / 2
    text_width = width - 200

    def line(text: str, y: float, font: str, size: float, color=CHARCOAL) -> None:
        pdf.setFont(font, size)
        pdf.setFillColor(color)
        pdf.drawCentredString(center, y, text)

    # Issuer and title.
    line(_spaced(content.issuer), height - 96, SERIF_BOLD, 11, SAGE)
    line("Certificate of Completion", height - 154, SERIF_BOLD, 38, CHARCOAL)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.line(center - 70, height - 173, center + 70, height - 173)
    pdf.setFillColor(GOLD)
    pdf.circle(center, height - 173, 2.4, stroke=0, fill=1)

    line("This certifies that", height - 214, SERIF, 14, MUTED)

    # Learner's name: one line, shrunk to fit, or two lines for very long names. A name the
    # font can't print at all is never left blank or garbled: the page points to the
    # verification address, which shows it exactly.
    name, exact = printable(content.recipient_name)
    if not any(char.isalpha() for char in name):
        name = "the learner named at the verification address"
    size = _fit(name, SERIF_BOLD, 34, text_width, 22)
    names = (
        [name]
        if pdfmetrics.stringWidth(name, SERIF_BOLD, size) <= text_width
        else _wrap(name, SERIF_BOLD, 22, text_width, 2)
    )
    y = height - 264
    for part in names:
        line(part, y, SERIF_BOLD, size if len(names) == 1 else 22, SAGE)
        y -= 28
    pdf.setStrokeColor(GOLD_LIGHT)
    pdf.setLineWidth(0.6)
    pdf.line(center - 190, y + 14, center + 190, y + 14)

    line("has completed all requirements of the online course", y - 14, SERIF, 14, MUTED)
    title_size = 21 if pdfmetrics.stringWidth(content.course_title, SERIF_BOLD, 21) <= 560 else 18
    y -= 52
    for part in _wrap(content.course_title, SERIF_BOLD, title_size, 600, 2):
        line(part, y, SERIF_BOLD, title_size, CHARCOAL)
        y -= title_size + 6

    # Footer row: date (left), signatory (centre), QR code and verification (right).
    base = 132
    completed = content.completed_at or content.issued_at
    pdf.setFillColor(CHARCOAL)
    pdf.setFont(SERIF_BOLD, 12)
    pdf.drawString(86, base + 24, _date(completed))
    pdf.setStrokeColor(SAGE_SOFT)
    pdf.setLineWidth(0.7)
    pdf.line(86, base + 16, 266, base + 16)
    pdf.setFont(SERIF, 9.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(86, base + 2, "Date of completion")
    if content.completed_at and content.issued_at.date() != content.completed_at.date():
        pdf.drawString(86, base - 11, f"Issued {_date(content.issued_at)}")

    # Approved signatory (Settings › Certificates); without one, the issuing organisation.
    signer = printable(content.signatory_name.strip())[0]
    pdf.setFillColor(CHARCOAL)
    pdf.setFont(SERIF_BOLD, 13)
    pdf.drawCentredString(center, base + 24, signer or content.issuer)
    pdf.line(center - 100, base + 16, center + 100, base + 16)
    pdf.setFont(SERIF, 9.5)
    pdf.setFillColor(MUTED)
    role = printable(content.signatory_title.strip())[0]
    role = role or (f"For {content.issuer}" if signer else "Issuing organisation")
    pdf.drawCentredString(center, base + 2, role)

    qr_size = 74
    qr_x, qr_y = width - 86 - qr_size, base - 12
    widget = QrCodeWidget(content.verify_url, barLevel="M")
    bounds = widget.getBounds()
    scale = qr_size / max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    drawing = Drawing(qr_size, qr_size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, pdf, qr_x, qr_y)
    pdf.setFont(SERIF, 8.5)
    pdf.setFillColor(MUTED)
    right = qr_x - 10
    pdf.drawRightString(right, base + 40, "Certificate ID")
    pdf.setFont(SERIF_BOLD, 10.5)
    pdf.setFillColor(CHARCOAL)
    pdf.drawRightString(right, base + 27, content.code)
    pdf.setFont(SERIF, 8.5)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(right, base + 12, "Scan to verify")
    pdf.linkURL(content.verify_url, (qr_x, qr_y, qr_x + qr_size, qr_y + qr_size), relative=0)

    # The full verification address on its own line (also a link).
    verify = f"Verify at {content.verify_url}"
    verify_size = _fit(verify, SERIF, 9, width - 180, 6.5)
    pdf.setFont(SERIF, verify_size)
    pdf.setFillColor(SAGE)
    pdf.drawCentredString(center, 84, verify)
    half = pdfmetrics.stringWidth(verify, SERIF, verify_size) / 2
    pdf.linkURL(content.verify_url, (center - half, 81, center + half, 93), relative=0)

    # Statement (not an accredited qualification) and the exact-name note.
    notes = []
    if not exact:
        notes.append(
            "The learner's name is shown in full, exactly as registered, at the verification "
            "address."
        )
    if content.statement:
        notes.append(content.statement)
    y = 66
    pdf.setFont(SERIF, 7.5)
    pdf.setFillColor(MUTED)
    for note in notes:
        for part in _wrap(note, SERIF, 7.5, width - 180, 2):
            pdf.drawCentredString(center, y, part)
            y -= 10.5

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
