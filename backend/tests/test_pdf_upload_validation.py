"""PDF upload validation: structural inspection instead of a raw byte search.

Ordinary printable PDFs (fonts, JPEG images, flattened workbooks, links, plain forms)
are accepted even when their binary streams happen to contain bytes such as ``/JS``;
real scripts, launch and other unsafe actions, attachments, rich media, encrypted and
malformed files are refused, including when hidden behind indirect references, nested
action chains, name escapes or objects left out of the cross-reference table.
"""

from __future__ import annotations

import io
import os
import random
import re
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.commerce.files import FORMATS, FileRejected, validate_file

from .conftest import minimal_pdf

LIMITS = {"formats": FORMATS}
# The byte pattern the previous validator searched the whole file for.
OLD_PATTERN = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)\b")


def check(tmp_path: Path, data: bytes, name: str = "workbook.pdf"):
    path = tmp_path / f"upload-{random.random()}"
    path.write_bytes(data)
    return validate_file(path, name, LIMITS)


def rejected(tmp_path: Path, data: bytes, name: str = "workbook.pdf") -> str:
    with pytest.raises(FileRejected) as info:
        check(tmp_path, data, name)
    return str(info.value)


# ---- realistic PDFs ------------------------------------------------------------------


def _jpeg(width=240, height=160, seed=7) -> bytes:
    from PIL import Image

    rng = random.Random(seed)
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(width * height)
        ]
    )
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def reportlab_pdf(*, font=None, jpeg=False, pages=1, links=False, form=False) -> bytes:
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle("Calm Mornings Workbook")
    if font:
        pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))
    for page in range(1, pages + 1):
        c.setFont("Vera" if font else "Helvetica", 14)
        c.drawString(72, 770, f"Day {page}: what went well today?")
        for y in range(700, 150, -36):  # flattened writing lines
            c.line(72, y, 520, y)
        c.rect(60, 120, 475, 680)
        if jpeg:
            c.drawImage(ImageReader(io.BytesIO(_jpeg(seed=page))), 380, 40, 120, 80)
        if links:
            c.bookmarkPage(f"day{page}")
            c.addOutlineEntry(f"Day {page}", f"day{page}")
            c.linkURL("https://thinkpositivealways.com/shop", (72, 60, 300, 80))
            c.drawString(72, 64, "thinkpositivealways.com/shop")
        if form:
            c.acroForm.textfield(name=f"notes{page}", x=72, y=200, width=300, height=24)
            c.acroForm.checkbox(name=f"done{page}", x=400, y=200, size=18)
        c.showPage()
    c.save()
    return out.getvalue()


def edit(data: bytes, change) -> bytes:
    """Rewrite a PDF with pypdf after ``change(writer)`` (objects stay indirect)."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    change(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def raw_pdf(*bodies: bytes, after_eof: bytes = b"") -> bytes:
    """A hand-built PDF: object 1 is the catalogue, 2 the page tree, 3 the page."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    replaced = dict(enumerate(bodies, 1))
    objects = [replaced.get(i, body) for i, body in enumerate(objects, 1)]
    objects += list(bodies[3:])
    out = b"%PDF-1.7\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out + after_eof


CATALOG = b"<< /Type /Catalog /Pages 2 0 R >>"
PAGES = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
PAGE = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"


def page_with_annots(*refs: int) -> bytes:
    annots = b" ".join(b"%d 0 R" % r for r in refs)
    return b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Annots [%s] >>" % annots


def link(action_ref: int) -> bytes:
    return b"<< /Type /Annot /Subtype /Link /Rect [0 0 100 100] /A %d 0 R >>" % action_ref


def _stream(writer: PdfWriter, data: bytes, **entries) -> object:
    stream = DecodedStreamObject()
    stream.set_data(data)
    for key, value in entries.items():
        stream[NameObject(f"/{key}")] = value
    return writer._add_object(stream)


# ---- accepted ------------------------------------------------------------------------


def test_minimal_and_reportlab_pdfs_are_accepted(tmp_path):
    assert check(tmp_path, minimal_pdf()).format.key == "pdf"
    report = check(tmp_path, reportlab_pdf(pages=3))
    assert set(report.details) == {"pdf_version"}


def test_embedded_fonts_are_accepted(tmp_path):
    data = reportlab_pdf(font=True, pages=2)
    assert b"/FontFile2" in data  # the TrueType font program is embedded
    check(tmp_path, data)


def test_compressed_jpeg_images_are_accepted(tmp_path):
    data = reportlab_pdf(jpeg=True, pages=4)
    assert b"/DCTDecode" in data
    check(tmp_path, data)


def test_flattened_workbook_with_links_and_bookmarks_is_accepted(tmp_path):
    data = reportlab_pdf(font=True, jpeg=True, pages=12, links=True)
    assert b"/URI" in data and b"/Outlines" in data
    check(tmp_path, data)


def test_printable_form_without_actions_is_accepted(tmp_path):
    data = reportlab_pdf(form=True, pages=2)
    assert b"/AcroForm" in data and b"/Widget" in data
    check(tmp_path, data)


def test_marker_bytes_inside_streams_are_not_mistaken_for_active_content(tmp_path):
    """The false positive: ``/JS``, ``/EmbeddedFile`` … inside image, font or other data."""
    noise = b"/JS /JavaScript /EmbeddedFile /Launch /RichMedia /OpenAction /AA\n" * 4

    def add_streams(writer):
        page = writer.pages[0]
        image = _stream(
            writer,
            noise + os.urandom(2000) + noise,
            Type=NameObject("/XObject"),
            Subtype=NameObject("/Image"),
            Width=NumberObject(10),
            Height=NumberObject(10),
            ColorSpace=NameObject("/DeviceGray"),
            BitsPerComponent=NumberObject(8),
        )
        resources = page["/Resources"].get_object()
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im9"): image})
        writer._root_object[NameObject("/Metadata")] = _stream(
            writer, b"<x:xmpmeta>" + noise + b"</x:xmpmeta>", Type=NameObject("/Metadata")
        )
        writer.add_metadata({"/Title": "Using /JavaScript and /EmbeddedFile safely"})

    data = edit(reportlab_pdf(font=True, jpeg=True), add_streams)
    assert OLD_PATTERN.search(data)  # the previous byte search would have refused this
    check(tmp_path, data)


def test_cyclic_harmless_action_chain_is_accepted(tmp_path):
    data = raw_pdf(
        CATALOG,
        PAGES,
        page_with_annots(4),
        link(5),
        b"<< /S /GoTo /D [3 0 R /Fit] /Next 6 0 R >>",
        b"<< /S /Named /N /NextPage /Next 5 0 R >>",
    )
    check(tmp_path, data)


def test_open_action_destination_is_accepted(tmp_path):
    check(tmp_path, minimal_pdf(catalog=b"/OpenAction [3 0 R /Fit]"))


# ---- refused: scripts and actions ----------------------------------------------------


def test_document_javascript_name_tree_is_refused(tmp_path):
    data = edit(reportlab_pdf(), lambda w: w.add_js("app.alert('hi');"))
    assert "JavaScript" in rejected(tmp_path, data)


def test_indirect_open_action_javascript_is_refused(tmp_path):
    def add(writer):
        action = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/S"): NameObject("/JavaScript"),
                    NameObject("/JS"): _stream(writer, b"app.alert(1)"),
                }
            )
        )
        writer._root_object[NameObject("/OpenAction")] = action

    assert "JavaScript" in rejected(tmp_path, edit(reportlab_pdf(), add))


def test_escaped_names_cannot_hide_javascript(tmp_path):
    # /J#61vaScript and /J#53 are /JavaScript and /JS once the name escapes are decoded.
    data = raw_pdf(
        b"<< /Type /Catalog /Pages 2 0 R /OpenAction 4 0 R >>",
        PAGES,
        PAGE,
        b"<< /S /J#61vaScript /J#53 (app.alert(1)) >>",
    )
    assert b"/JS" not in data
    assert "JavaScript" in rejected(tmp_path, data)


def test_launch_action_nested_behind_references_is_refused(tmp_path):
    data = raw_pdf(
        CATALOG,
        PAGES,
        page_with_annots(4),
        link(5),
        b"<< /S /GoTo /D [3 0 R /Fit] /Next [6 0 R] >>",
        b"<< /Type /Action /S /Named /N /FirstPage /Next 7 0 R >>",
        b"<< /S /Launch /Win << /F (cmd.exe) >> >>",
    )
    assert "launch" in rejected(tmp_path, data)


def test_unknown_or_external_actions_in_nested_chains_are_refused(tmp_path):
    for action in (
        b"<< /S /SubmitForm /F (https://example.com/collect) >>",
        b"<< /S /ImportData /F (data.fdf) >>",
        b"<< /S /GoToR /F (other.pdf) /D [0 /Fit] >>",
        b"<< /S /SomethingNew >>",
    ):
        data = raw_pdf(
            CATALOG,
            PAGES,
            page_with_annots(4),
            link(5),
            b"<< /S /GoTo /D [3 0 R /Fit] /Next 6 0 R >>",
            action,
        )
        rejected(tmp_path, data)


def test_automatic_actions_are_refused(tmp_path):
    # A page-open (/AA) form submission and an on-open link to a website.
    page_aa = raw_pdf(
        CATALOG,
        PAGES,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /AA << /O 4 0 R >> >>",
        b"<< /S /SubmitForm /F (https://example.com/) >>",
    )
    assert "form submission" in rejected(tmp_path, page_aa)
    open_uri = minimal_pdf(catalog=b"/OpenAction << /S /URI /URI (https://example.com/) >>")
    assert "automatic actions" in rejected(tmp_path, open_uri)
    field_js = raw_pdf(
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R] >> >>",
        PAGES,
        page_with_annots(4),
        b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (total) /Rect [0 0 50 20]"
        b" /AA << /C 5 0 R >> >>",
        b"<< /S /JavaScript /JS 6 0 R >>",
        b"<< /Length 12 >>\nstream\napp.alert(1)\nendstream",
    )
    assert "JavaScript" in rejected(tmp_path, field_js)


def test_links_with_script_or_file_schemes_are_refused(tmp_path):
    for uri in (b"javascript:alert(1)", b"file:///etc/passwd", b" JAVASCRIPT:alert(1)"):
        data = raw_pdf(
            CATALOG, PAGES, page_with_annots(4), link(5), b"<< /S /URI /URI (%s) >>" % uri
        )
        assert "links" in rejected(tmp_path, data)
    ok = raw_pdf(
        CATALOG, PAGES, page_with_annots(4), link(5), b"<< /S /URI /URI (mailto:hi@x.org) >>"
    )
    check(tmp_path, ok)


def test_xfa_forms_are_refused(tmp_path):
    data = minimal_pdf(catalog=b"/AcroForm << /Fields [] /XFA [(template) 4 0 R] >>")
    assert "XFA" in rejected(tmp_path, data)


# ---- refused: attachments and media ----------------------------------------------------


def test_embedded_attachments_are_refused(tmp_path):
    data = edit(reportlab_pdf(), lambda w: w.add_attachment("answers.exe", b"MZ..."))
    assert "embedded files" in rejected(tmp_path, data)


def test_file_attachment_annotation_is_refused(tmp_path):
    data = raw_pdf(
        CATALOG,
        PAGES,
        page_with_annots(4),
        b"<< /Type /Annot /Subtype /FileAttachment /Rect [0 0 20 20] /FS 5 0 R >>",
        b"<< /Type /Filespec /F (notes.txt) >>",
    )
    assert "embedded files" in rejected(tmp_path, data)


def test_associated_files_are_refused(tmp_path):
    data = raw_pdf(
        b"<< /Type /Catalog /Pages 2 0 R /AF [4 0 R] >>",
        PAGES,
        PAGE,
        b"<< /Type /Filespec /F (invoice.xml) >>",
    )
    assert "embedded files" in rejected(tmp_path, data)


def test_rich_media_and_multimedia_are_refused(tmp_path):
    for annot in (
        b"<< /Type /Annot /Subtype /RichMedia /Rect [0 0 9 9] /RichMediaContent 5 0 R >>",
        b"<< /Type /Annot /Subtype /Screen /Rect [0 0 9 9] >>",
        b"<< /Type /Annot /Subtype /Movie /Rect [0 0 9 9] >>",
        b"<< /Type /Annot /Subtype /3D /Rect [0 0 9 9] >>",
    ):
        data = raw_pdf(CATALOG, PAGES, page_with_annots(4), annot, b"<< >>")
        rejected(tmp_path, data)


def incremental_update(original: bytes, appended_object: bytes) -> bytes:
    """Append an object plus an update section that lists it as free ("deleted")."""
    prev = int(re.findall(rb"startxref\s+(\d+)", original)[-1])
    out = original + appended_object
    xref = len(out)
    out += b"xref\n0 1\n0000000000 65535 f \n9 1\n0000000000 00001 f \n"
    out += b"trailer\n<< /Size 10 /Root 1 0 R /Prev %d >>\nstartxref\n%d\n%%%%EOF\n" % (prev, xref)
    return out


def test_objects_left_out_of_the_xref_are_still_inspected(tmp_path):
    # An attachment "deleted" by an incremental save still sits in the file, where a
    # viewer repairing the file could find it.
    attachment = b"9 0 obj\n<< /Type /EmbeddedFile /Length 2 >>\nstream\nMZ\nendstream\nendobj\n"
    assert "embedded files" in rejected(tmp_path, incremental_update(raw_pdf(), attachment))
    # An object between the others that the table doesn't mention.
    hidden_js = b"9 0 obj\n<< /S /JavaScript /JS (app.alert(1)) >>\nendobj\n"
    assert "JavaScript" in rejected(tmp_path, minimal_pdf(extra=hidden_js))
    # A harmless incremental update is fine.
    note = b"9 0 obj\n<< /Note (edited) >>\nendobj\n"
    check(tmp_path, incremental_update(raw_pdf(), note))


# ---- refused: unreadable ---------------------------------------------------------------


def test_encrypted_pdfs_are_refused(tmp_path):
    def protect(writer):
        writer.encrypt(user_password="", owner_password="owner", algorithm="RC4-128")

    message = rejected(tmp_path, edit(reportlab_pdf(), protect))
    assert "encrypted" in message


def test_malformed_pdfs_fail_closed(tmp_path):
    good = reportlab_pdf(pages=2)
    cases = [
        b"%PDF-1.7\n" + os.urandom(4000) + b"\n%%EOF\n",  # no structure at all
        good[: len(good) // 2] + b"\n%%EOF\n",  # truncated, marker re-added
        raw_pdf(b"<< /Type /Page >>"),  # the trailer's root is not a catalogue
        raw_pdf(b"<< /Type /Catalog >>"),  # no page tree
        raw_pdf(CATALOG, PAGES, PAGE, b"[" * 200_000 + b"]" * 200_000),  # absurd nesting
    ]
    for data in cases:
        assert "couldn't be checked safely" in rejected(tmp_path, data)
    assert "truncated" in rejected(tmp_path, good[:-200])  # no end-of-file marker


def test_too_complex_pdfs_fail_closed(tmp_path, monkeypatch):
    from app.commerce import pdf_safety

    monkeypatch.setattr(pdf_safety, "MAX_OBJECTS", 5)
    assert "couldn't be checked safely" in rejected(tmp_path, reportlab_pdf(pages=3))


def test_format_and_extension_checks_still_apply(tmp_path):
    assert "Rename it" in rejected(tmp_path, reportlab_pdf(), "workbook.docx")
    assert "Executable" in rejected(tmp_path, b"MZ\x90\x00" + reportlab_pdf())
    assert "not a valid PDF" in rejected(tmp_path, b"%PDF-x" + reportlab_pdf()[6:])
    only_epub = {"formats": {"epub": FORMATS["epub"]}}
    path = tmp_path / "w.pdf"
    path.write_bytes(reportlab_pdf())
    with pytest.raises(FileRejected, match="Unsupported file type"):
        validate_file(path, "w.pdf", only_epub)


# ---- through the product upload API ------------------------------------------------------

PRODUCTS = "/api/v1/admin/products"


def test_product_upload_accepts_real_workbooks_and_refuses_scripts(seeded, as_role):
    api = as_role("product_manager")
    res = api.post(PRODUCTS, {"title": "Gratitude Journal", "product_type": "workbook"})
    pid = res.get_json()["data"]["id"]
    url = f"{PRODUCTS}/{pid}/files"

    def with_noise(writer):
        writer.add_metadata({"/Subject": "/JS /EmbeddedFile"})
        resources = writer.pages[0]["/Resources"].get_object()
        image = _stream(
            writer,
            b"/JS /EmbeddedFile" + os.urandom(100),
            Type=NameObject("/XObject"),
            Subtype=NameObject("/Image"),
            Width=NumberObject(1),
            Height=NumberObject(1),
            ColorSpace=NameObject("/DeviceGray"),
            BitsPerComponent=NumberObject(8),
            Decode=ArrayObject([FloatObject(0), FloatObject(1)]),
        )
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im1"): image})

    workbook = edit(reportlab_pdf(font=True, jpeg=True, pages=6, links=True), with_noise)
    ok = api.upload(url, workbook, "Gratitude Journal.pdf")
    assert ok.status_code == 201, ok.get_json()

    scripted = edit(workbook, lambda w: w.add_js("app.alert(1)"))
    res = api.upload(url, scripted, "scripted.pdf")
    assert res.status_code == 400 and "JavaScript" in str(res.get_json())
    attached = edit(workbook, lambda w: w.add_attachment("a.txt", b"x"))
    assert api.upload(url, attached, "attached.pdf").status_code == 400
    assert "Error" not in str(res.get_json())  # no parser internals leak
