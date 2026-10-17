from django.test import SimpleTestCase, override_settings

from .testing import JPG, PDF, PNG, docx_bytes, make_zip, odt_bytes, upload, xlsx_bytes
from .validation import UploadRejected, clean_display_name, validate_upload


class AcceptTests(SimpleTestCase):
    def test_genuine_files_pass(self):
        for name, data, ctype in [
            ("a.pdf", PDF, "application/pdf"), ("a.png", PNG, "image/png"), ("a.jpg", JPG, "image/jpeg"), ("a.JPEG", JPG, "image/jpeg"),
            ("a.txt", "salom dunyo".encode(), "text/plain"), ("a.docx", docx_bytes(), "application/octet-stream"), ("a.xlsx", xlsx_bytes(), ""),
            ("a.odt", odt_bytes(), "application/vnd.oasis.opendocument.text"),
        ]:
            checked = validate_upload(upload(name, data, ctype))
            self.assertEqual(checked.size, len(data), name)

    def test_generic_declared_mime_is_ok_because_content_is_checked_anyway(self):
        validate_upload(upload("a.pdf", PDF, "application/octet-stream"))


class RejectTests(SimpleTestCase):
    def reject(self, uploaded, code):
        with self.assertRaises(UploadRejected) as ctx:
            validate_upload(uploaded)
        self.assertEqual(ctx.exception.code, code)

    def test_forbidden_extensions(self):
        for name in ("a.exe", "a.html", "a.htm", "a.svg", "a.js", "a.php", "a.sh", "a.zip", "a.docm", "a.xml", "a", "a."):
            self.reject(upload(name, b"x"), "extension" if name != "a." else "extension")

    def test_double_and_hidden_extensions(self):
        for name in ("report.php.pdf", "x.html.pdf", "x.exe.txt", "x.svg.png", "x.PHP.pdf", "x.js.docx"):
            self.reject(upload(name, PDF), "double_extension")

    def test_extension_must_match_content(self):
        self.reject(upload("a.pdf", b"<html><script>alert(1)</script></html>", "application/pdf"), "signature")
        self.reject(upload("a.png", PDF, "image/png"), "signature")
        self.reject(upload("a.jpg", PNG, "image/jpeg"), "signature")
        self.reject(upload("a.docx", PDF, ""), "signature")
        self.reject(upload("a.txt", b"abc\x00def", "text/plain"), "signature")
        self.reject(upload("a.txt", b"\xff\xfe\xfa", "text/plain"), "signature")

    def test_svg_html_content_disguised_as_image_or_text(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
        self.reject(upload("a.png", svg, "image/png"), "signature")
        self.reject(upload("a.jpg", svg, "image/jpeg"), "signature")
        self.reject(upload("a.pdf", svg, "application/pdf"), "signature")

    def test_declared_mime_contradicting_the_extension(self):
        self.reject(upload("a.pdf", PDF, "text/html"), "mime_mismatch")
        self.reject(upload("a.png", PNG, "image/svg+xml"), "mime_mismatch")
        self.reject(upload("a.docx", docx_bytes(), "application/pdf"), "mime_mismatch")

    def test_empty_and_oversized(self):
        self.reject(upload("a.pdf", b"", "application/pdf"), "empty")
        with override_settings(DOCUMENT_MAX_BYTES=100):
            self.reject(upload("a.pdf", PDF + b"0" * 200), "too_large")
            validate_upload(upload("a.pdf", PDF))

    def test_pdf_with_active_content(self):
        for marker in (b"/JavaScript", b"/JS (x)", b"/Launch", b"/EmbeddedFile"):
            self.reject(upload("a.pdf", PDF + b"<<" + marker + b">>"), "pdf_active")

    def test_office_macros_and_wrong_structure(self):
        self.reject(upload("a.docx", docx_bytes([("word/vbaProject.bin", "x")])), "office_active")
        self.reject(upload("a.docx", make_zip([("random.txt", "x")])), "office_structure")
        self.reject(upload("a.xlsx", docx_bytes()), "office_structure")  # a docx renamed to xlsx
        self.reject(upload("a.odt", odt_bytes([("Scripts/x.py", "x")])), "office_active")
        self.reject(upload("a.odt", make_zip([("content.xml", "x")])), "odf_structure")
        self.reject(upload("a.ods", odt_bytes()), "odf_structure")  # odt renamed to ods
        self.reject(upload("a.docx", b"PK\x03\x04garbage"), "bad_zip")

    def test_zip_path_traversal_entries_and_bombs(self):
        self.reject(upload("a.docx", docx_bytes([("../evil.txt", "x")])), "zip_unsafe")
        self.reject(upload("a.docx", docx_bytes([("/etc/passwd", "x")])), "zip_unsafe")
        bomb = docx_bytes([("word/big.bin", b"\x00" * (3 * 1024 * 1024))])
        self.reject(upload("a.docx", bomb), "zip_bomb")


class NameTests(SimpleTestCase):
    def test_display_name_is_never_a_path(self):
        for raw, expected in [("../../etc/passwd", "passwd"), ("C:\\Windows\\x.pdf", "x.pdf"), ("a/b/c.pdf", "c.pdf"), ("  .hidden.pdf ", "hidden.pdf"),
                              ("rep\u202eort.pdf", "report.pdf"), ("a\x00b.pdf", "ab.pdf"), ("x" * 400 + ".pdf", "x" * 150)]:
            self.assertEqual(clean_display_name(raw), expected, raw)

    def test_traversal_in_the_client_name_does_not_change_the_checks(self):
        checked = validate_upload(upload("../../../tmp/evil.pdf", PDF))
        self.assertEqual(checked.display_name, "evil.pdf")
        with self.assertRaises(UploadRejected):
            validate_upload(upload("../../x.php", PDF))
