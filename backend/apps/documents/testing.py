"""Builders for small, valid, harmless sample files (tests only)."""
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


def docx_bytes(extra=()):
    return make_zip([("[Content_Types].xml", "<Types/>"), ("word/document.xml", "<w/>"), *extra])


def xlsx_bytes():
    return make_zip([("[Content_Types].xml", "<Types/>"), ("xl/workbook.xml", "<w/>")])


def odt_bytes(extra=()):
    return make_zip([("mimetype", "application/vnd.oasis.opendocument.text"), ("content.xml", "<o/>"), *extra])


def upload(name="a.pdf", data=PDF, content_type=""):
    return SimpleUploadedFile(name, data, content_type=content_type)
