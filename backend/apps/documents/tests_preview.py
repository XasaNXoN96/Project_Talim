"""In-portal viewer: shown only to people who may see the document, only for safe types, never as a way around the access rules."""
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.acceptance import World
from apps.documents import files
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import add_version
from apps.documents.testing import JPG, PDF, PNG, upload
from apps.documents.validation import validate_upload
from apps.organization.models import Employee

XSS = '<script>alert(1)</script><img src=x onerror=alert(2)>'


class Base(TestCase):
    def setUp(self):
        self.w = World()
        self.cat = DocumentCategory.objects.first()
        self.emp, self.stranger, self.hr = self.w.client("emp"), self.w.client("stranger"), self.w.client("hr")

    def doc(self, name, data, *, title="Hujjat", level="general", department=None, creator="hr", status="active"):
        d = Document.objects.create(title=title, category=self.cat, created_by=self.w.users[creator], access_level=level, department=department, status=status)
        add_version(d, validate_upload(upload(name, data)), actor=self.w.users[creator])
        return d

    def view(self, c, d, n=None):
        return c.get(reverse("documents:preview_version", args=[d.pk, n]) if n else reverse("documents:preview", args=[d.pk]))

    def raw(self, c, d, n=None):
        return c.get(reverse("documents:inline_version", args=[d.pk, n]) if n else reverse("documents:inline", args=[d.pk]))


class SafeTypes(Base):
    def test_pdf_is_embedded_and_served_inline_with_locked_down_headers(self):
        d = self.doc("a.pdf", PDF)
        page = self.view(self.emp, d)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertIn("<iframe", html)
        self.assertIn(reverse("documents:inline_version", args=[d.pk, 1]), html)
        r = self.raw(self.emp, d)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(r["Content-Disposition"], "inline")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("default-src 'none'", r["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'self'", r["Content-Security-Policy"])
        self.assertIn("no-store", r["Cache-Control"])
        self.assertEqual(b"".join(r.streaming_content), PDF)

    def test_images_are_shown_with_their_fixed_types(self):
        for name, data, ctype in (("a.png", PNG, "image/png"), ("b.jpg", JPG, "image/jpeg"), ("c.jpeg", JPG, "image/jpeg")):
            d = self.doc(name, data, title=name)
            self.assertIn("<img", self.view(self.emp, d).content.decode(), name)
            r = self.raw(self.emp, d)
            self.assertEqual((r.status_code, r["Content-Type"]), (200, ctype), name)
            self.assertEqual(b"".join(r.streaming_content), data)

    def test_text_is_escaped_truncated_and_survives_bad_bytes(self):
        d = self.doc("a.txt", ("Salom " + XSS + " ъ").encode())
        html = self.view(self.emp, d).content.decode()
        self.assertIn("&lt;script&gt;alert(1)", html)
        self.assertNotIn("<script>alert(1)", html)
        big = self.doc("b.txt", b"x" * (files.TEXT_PREVIEW_BYTES + 500), title="Katta")
        page = self.view(self.emp, big).content.decode()
        self.assertEqual(page.count("x" * 1000) > 0, True)
        self.assertNotIn("x" * (files.TEXT_PREVIEW_BYTES + 1), page)
        self.assertIn("pre", page)
        bad = self.doc("c.txt", b"ok", title="Buzuq")
        v = bad.versions.first()
        with v.file.storage.open(v.file.name, "wb") as handle:
            handle.write(b"ok \xff\xfe\x00 bad")  # bytes that are not UTF-8 (e.g. damaged on disk) must not crash the page
        page = self.view(self.emp, bad)
        self.assertEqual(page.status_code, 200)
        self.assertIn("ok ", page.content.decode())

    def test_other_formats_get_a_notice_and_a_download_but_are_never_sent_inline(self):
        d = self.doc("a.pdf", PDF)
        for ext in ("docx", "xlsx", "pptx", "odt", "ods"):
            self.assertIsNone(files.preview_kind(ext))
        for ext in ("html", "htm", "svg", "xml", "js", "exe", ""):
            self.assertIsNone(files.preview_kind(ext))
        from django.http import Http404

        for ext in ("docx", "svg", "html", "txt"):
            with self.assertRaises(Http404):
                files.inline_response(d.versions.first().file, extension=ext)
        # a stored version of an unsupported type: page explains, raw endpoint refuses, download still works
        v = d.versions.first()
        type(v).objects.filter(pk=v.pk).update(extension="docx")
        page = self.view(self.emp, d)
        html = page.content.decode()
        self.assertNotIn("<iframe", html)
        self.assertNotIn("<img", html.split('class="card card-pad viewer"')[1])
        self.assertIn(reverse("documents:download_version", args=[d.pk, 1]), html)
        self.assertEqual(self.raw(self.emp, d).status_code, 404)
        self.assertEqual(self.emp.get(reverse("documents:download", args=[d.pk])).status_code, 200)

    def test_a_forged_extension_cannot_make_active_content_inline(self):
        # validation matches extension to real content on upload, so html/svg never get in ...
        for name, data in (("x.html", b"<script>alert(1)</script>"), ("x.svg", b"<svg onload=alert(1)/>"), ("x.pdf", b"<html><script>alert(1)</script></html>"), ("x.png", b"<script>alert(1)</script>")):
            d = Document.objects.create(title="T", category=self.cat, created_by=self.w.users["hr"])
            from apps.documents.validation import UploadRejected

            with self.assertRaises(UploadRejected):
                add_version(d, validate_upload(upload(name, data)), actor=self.w.users["hr"])
            self.assertEqual(d.versions.count(), 0, name)


class AccessIsDecidedFirst(Base):
    def test_closed_documents_are_closed_on_all_four_routes_for_every_unauthorised_actor(self):
        conf = self.w.secret_doc
        other_dept = self.doc("d.pdf", PDF, title="Bo‘lim", level="department", department=self.w.other)
        arch = self.doc("e.pdf", PDF, title="Arxiv", status="archived")
        cases = [(conf, ("emp", "stranger", "head", "content")), (other_dept, ("emp", "content")), (arch, ("emp", "stranger", "content"))]
        for d, actors in cases:
            for actor in actors:
                c = self.w.client(actor)
                for name in ("preview", "preview_version", "inline", "inline_version"):
                    args = [d.pk, 1] if name.endswith("version") else [d.pk]
                    r = c.get(reverse(f"documents:{name}", args=args))
                    self.assertEqual(r.status_code, 403, (d.title, actor, name))
                    self.assertNotEqual(r.get("Content-Type"), "application/pdf")
                    self.assertNotIn(b"%PDF", r.content)
        for name in ("preview", "inline"):
            r = Client().get(reverse(f"documents:{name}", args=[conf.pk]))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])

    def test_authorised_people_do_get_in(self):
        conf = self.w.secret_doc
        self.assertEqual(self.view(self.hr, conf).status_code, 200)
        self.assertEqual(self.raw(self.hr, conf).status_code, 200)
        self.assertEqual(self.view(self.w.client("admin"), conf).status_code, 200)
        dept = self.doc("d.pdf", PDF, title="Bo‘lim", level="department", department=self.w.root)
        self.assertEqual(self.raw(self.emp, dept).status_code, 200)  # emp sits in a child department of `root`
        self.assertEqual(self.raw(self.w.client("head"), dept).status_code, 200)

    def test_changing_the_department_changes_access_on_the_next_request(self):
        dept = self.doc("d.pdf", PDF, title="Bo‘lim", level="department", department=self.w.root)
        self.assertEqual(self.raw(self.emp, dept).status_code, 200)
        Employee.objects.filter(user=self.w.users["emp"]).update(department=self.w.other)
        self.assertEqual(self.raw(self.emp, dept).status_code, 403)
        self.assertEqual(self.view(self.emp, dept).status_code, 403)

    def test_version_numbers_cannot_reach_other_documents_or_missing_versions(self):
        a, b = self.doc("a.pdf", PDF, title="A"), self.doc("b.pdf", PDF + b"B", title="B")
        self.assertEqual(self.view(self.emp, a, 2).status_code, 404)
        self.assertEqual(self.raw(self.emp, a, 99).status_code, 404)
        r = self.raw(self.emp, b, 1)
        self.assertEqual(b"".join(r.streaming_content), PDF + b"B")
        add_version(a, validate_upload(upload("a2.pdf", PDF + b"2")), actor=self.w.users["hr"])
        self.assertEqual(b"".join(self.raw(self.emp, a, 1).streaming_content), PDF)
        self.assertEqual(b"".join(self.raw(self.emp, a).streaming_content), PDF + b"2")  # default = latest
        self.assertEqual(self.emp.get(reverse("documents:inline_version", args=[a.pk, 0])).status_code, 404)

    def test_infected_versions_are_never_shown(self):
        d = self.doc("a.pdf", PDF)
        v = d.versions.first()
        type(v).objects.filter(pk=v.pk).update(scan_status="infected")
        self.assertEqual(self.view(self.emp, d).status_code, 404)
        self.assertEqual(self.raw(self.emp, d).status_code, 404)

    def test_the_private_storage_is_not_reachable_by_a_public_address(self):
        d = self.doc("a.pdf", PDF)
        stored = d.versions.first().file.name
        html = self.view(self.emp, d).content.decode()
        self.assertNotIn(stored, html)
        for prefix in ("/media/", "/private_media/", "/static/", "/"):
            self.assertEqual(Client().get(prefix + stored).status_code, 404, prefix)

    def test_only_reading_methods_work(self):
        d = self.doc("a.pdf", PDF)
        for name in ("preview", "inline"):
            u = reverse(f"documents:{name}", args=[d.pk])
            self.assertEqual(self.emp.post(u).status_code, 405)
            for m in ("put", "patch", "delete"):
                self.assertEqual(getattr(self.emp, m)(u).status_code, 405)
            self.assertEqual(self.emp.head(u).status_code, 200)
            self.assertEqual(self.emp.options(u).status_code, 200)


class AuditAndContent(Base):
    def test_confidential_views_are_audited_without_titles_or_names_and_ordinary_views_are_not(self):
        self.raw(self.emp, self.doc("a.pdf", PDF, title="Oddiy hujjat"))
        self.assertEqual(AuditLog.objects.filter(action="document_viewed").count(), 0)
        self.raw(self.hr, self.w.secret_doc)
        entry = AuditLog.objects.get(action="document_viewed")
        self.assertEqual((entry.object_id, entry.user), (str(self.w.secret_doc.pk), self.w.users["hr"]))
        self.assertEqual(entry.meta, {"version": 1, "how": "preview"})
        self.assertNotIn("Maxfiy", str(entry.meta))

    def test_failed_attempts_are_not_confused_with_views(self):
        self.raw(self.emp, self.w.secret_doc)
        self.assertEqual(AuditLog.objects.filter(action="document_viewed").count(), 0)

    def test_titles_and_file_names_are_escaped_on_the_viewer_page(self):
        d = self.doc("a.pdf", PDF, title="T " + XSS)
        type(d.versions.first()).objects.filter(pk=d.versions.first().pk).update(original_name=XSS + ".pdf", comment=XSS)
        html = self.view(self.emp, d).content.decode()
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_detail_page_offers_the_viewer_and_the_old_download_still_works(self):
        d = self.doc("a.pdf", PDF)
        page = self.emp.get(reverse("documents:detail", args=[d.pk])).content.decode()
        self.assertIn(reverse("documents:preview", args=[d.pk]), page)
        self.assertIn(reverse("documents:preview_version", args=[d.pk, 1]), page)
        r = self.emp.get(reverse("documents:download", args=[d.pk]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/octet-stream"))
        self.assertIn("attachment", r["Content-Disposition"])
