from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.organization.models import Department, Employee

from .models import Document, DocumentCategory, DocumentVersion
from .testing import PDF, docx_bytes, upload
from .services import add_version
from .validation import validate_upload


def url(name, *args):
    return reverse(f"documents:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.cat = DocumentCategory.objects.first()
        self.root = Department.objects.create(name="A")
        self.child = Department.objects.create(name="A1", parent=self.root)
        self.other = Department.objects.create(name="B")
        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=self.head, role=Group.objects.get(name="department_head"), scope="department", department=self.root)
        self.in_a = self._person("ina", self.child)
        self.in_b = self._person("inb", self.other)
        self.employee_head = Employee.objects.create(last_name="Head", first_name="H", department=self.root, user=self.head, status="active")

    def _person(self, name, dept):
        u = make_user(name, role="employee")
        Employee.objects.create(last_name=name.title(), first_name="X", department=dept, user=u, status="active")
        return u

    def doc(self, creator=None, level="general", dept=None, status="active", data=PDF, title="Nizom"):
        creator = creator or self.hr
        d = Document.objects.create(title=title, category=self.cat, created_by=creator, access_level=level, department=dept, status=status)
        checked = validate_upload(upload("a.pdf", data))
        add_version(d, checked, actor=creator)
        return d

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c


class VisibilityTests(Base):
    def test_anonymous(self):
        d = self.doc()
        for u in (url("list"), url("detail", d.pk), url("download", d.pk), url("create")):
            r = Client().get(u)
            self.assertEqual(r.status_code, 302, u)
            self.assertIn("/accounts/login/", r["Location"])

    def test_general_visible_to_every_employee_not_to_sysadmin(self):
        d = self.doc()
        for u in (self.in_a, self.in_b, self.head):
            self.assertEqual(self.client_for(u).get(url("detail", d.pk)).status_code, 200)
        sysadm = make_user("sys", role="sysadmin")
        self.assertEqual(self.client_for(sysadm).get(url("detail", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(sysadm).get(url("download", d.pk)).status_code, 403)

    def test_department_level_follows_the_branch(self):
        d = self.doc(level="department", dept=self.root)
        self.assertEqual(self.client_for(self.in_a).get(url("detail", d.pk)).status_code, 200)  # child department of A
        self.assertEqual(self.client_for(self.head).get(url("detail", d.pk)).status_code, 200)
        self.assertEqual(self.client_for(self.in_b).get(url("detail", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.in_b).get(url("download", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.hr).get(url("detail", d.pk)).status_code, 200)

    def test_child_department_document_is_not_visible_to_the_parent_branch_members_above_it(self):
        d = self.doc(level="department", dept=self.child)
        # someone sitting in the parent department only is NOT inside the child's branch
        parent_member = self._person("parentmember", self.root)
        self.assertEqual(self.client_for(parent_member).get(url("detail", d.pk)).status_code, 403)

    def test_confidential_only_author_hr_admin(self):
        d = self.doc(level="confidential", creator=self.head)
        for u, code in ((self.head, 200), (self.hr, 200), (self.admin, 200), (self.in_a, 403), (self.in_b, 403)):
            self.assertEqual(self.client_for(u).get(url("download", d.pk)).status_code, code, u.username)

    def test_list_contains_only_visible_documents(self):
        self.doc(title="Ommaviy")
        self.doc(title="Maxfiy-hujjat", level="confidential")
        self.doc(title="BolimB", level="department", dept=self.other)
        body = self.client_for(self.in_a).get(url("list")).content.decode()
        self.assertIn("Ommaviy", body)
        self.assertNotIn("Maxfiy-hujjat", body)
        self.assertNotIn("BolimB", body)

    def test_changing_the_id_to_someone_elses_document_is_refused(self):
        mine = self.doc(creator=self.head, level="department", dept=self.root, title="Mening")
        secret = self.doc(level="confidential", title="Begona")
        c = self.client_for(self.head)
        self.assertEqual(c.get(url("detail", mine.pk)).status_code, 200)
        for name in ("detail", "download", "edit"):
            self.assertEqual(c.get(url(name, secret.pk)).status_code, 403, name)
        self.assertEqual(c.get(url("download_version", secret.pk, 1)).status_code, 403)
        self.assertEqual(c.post(url("archive", secret.pk)).status_code, 403)
        self.assertEqual(c.post(url("version_add", secret.pk), {"file": upload("n.pdf")}).status_code, 403)

    def test_version_number_of_another_document_cannot_be_used(self):
        a, b = self.doc(title="A1"), self.doc(level="confidential", title="B1")
        v_b = b.versions.get()
        c = self.client_for(self.in_a)
        self.assertEqual(c.get(url("download_version", a.pk, 1)).status_code, 200)
        self.assertEqual(c.get(url("download_version", a.pk, 99)).status_code, 404)
        self.assertEqual(c.get(url("download_version", b.pk, v_b.number)).status_code, 403)

    def test_archived_visible_to_author_and_hr_only(self):
        d = self.doc(creator=self.head, status="archived", title="Arxivlangan-hujjat")
        self.assertEqual(self.client_for(self.in_a).get(url("detail", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.head).get(url("detail", d.pk)).status_code, 200)
        self.assertEqual(self.client_for(self.hr).get(url("detail", d.pk)).status_code, 200)
        self.assertNotContains(self.client_for(self.in_a).get(url("list"), {"status": "archived"}), "Arxivlangan-hujjat")
        self.assertContains(self.client_for(self.hr).get(url("list"), {"status": "archived"}), "Arxivlangan-hujjat")

    def test_list_filters_and_bad_category_id(self):
        self.doc(title="Hisobot-yili")
        c = self.client_for(self.in_a)
        self.assertContains(c.get(url("list"), {"q": "hisobot"}), "Hisobot-yili")
        self.assertNotContains(c.get(url("list"), {"q": "yoq-narsa"}), "Hisobot-yili")
        self.assertContains(c.get(url("list"), {"category": self.cat.pk}), "Hisobot-yili")
        self.assertEqual(c.get(url("list"), {"category": "garbage"}).status_code, 200)
        self.assertNotContains(c.get(url("list"), {"category": "garbage"}), "Hisobot-yili")


class DownloadTests(Base):
    def test_download_is_an_attachment_with_safe_headers_and_audited(self):
        d = self.doc(title='Buyruq <b>"1"</b>/../x')
        r = self.client_for(self.in_a).get(url("download", d.pk))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertTrue(r["Content-Disposition"].startswith("attachment;"))
        self.assertNotIn("/", r["Content-Disposition"].split("filename", 1)[1])
        self.assertNotIn('<', r["Content-Disposition"])
        self.assertEqual(r["Content-Type"], "application/octet-stream")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", r["Cache-Control"])
        entry = AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_DOWNLOADED)
        self.assertEqual((entry.user, entry.object_id), (self.in_a, str(d.pk)))

    def test_denied_download_is_not_audited_as_a_download(self):
        d = self.doc(level="confidential")
        self.client_for(self.in_a).get(url("download", d.pk))
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_DOWNLOADED).exists())

    def test_missing_file_on_disk_is_404(self):
        d = self.doc()
        v = d.versions.get()
        Path(v.file.path).unlink()
        self.assertEqual(self.client_for(self.in_a).get(url("download", d.pk)).status_code, 404)

    def test_confidential_view_is_audited_general_view_is_not(self):
        c = self.client_for(self.hr)
        c.get(url("detail", self.doc(level="confidential").pk))
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_VIEWED).count(), 1)
        c.get(url("detail", self.doc().pk))
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_VIEWED).count(), 1)


class StorageTests(Base):
    def test_file_is_stored_privately_with_a_random_name(self):
        r = self.client_for(self.hr).post(url("create"), {"title": "T", "category": self.cat.pk, "access_level": "general", "file": upload("../../Maxfiy nom.pdf")})
        d = Document.objects.get(title="T")
        self.assertRedirects(r, url("detail", d.pk), fetch_redirect_response=False)
        v = d.versions.get()
        stored = Path(v.file.path).resolve()
        root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        self.assertTrue(str(stored).startswith(str(root)))
        self.assertNotIn("Maxfiy", v.file.name)
        self.assertRegex(v.file.name, r"^[0-9a-f]{2}/[0-9a-f]{32}\.pdf$")
        self.assertEqual(v.original_name, "Maxfiy nom.pdf")
        self.assertEqual(oct(stored.stat().st_mode & 0o777), "0o600")
        self.assertEqual(len(v.sha256), 64)

    def test_private_root_is_not_inside_static_or_served_by_any_url(self):
        root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
        for static_dir in [Path(p[1] if isinstance(p, tuple) else p).resolve() for p in settings.STATICFILES_DIRS] + [Path(settings.STATIC_ROOT).resolve()]:
            self.assertFalse(str(root).startswith(str(static_dir)))
            self.assertFalse(str(static_dir).startswith(str(root)))
        d = self.doc()
        v = d.versions.get()
        with self.assertRaises(ValueError):
            v.file.url
        c = self.client_for(self.hr)
        for guess in (f"/media/{v.file.name}", f"/static/{v.file.name}", f"/{v.file.name}", f"/private_media/{v.file.name}", f"/portal/documents/{v.file.name}"):
            self.assertEqual(c.get(guess).status_code, 404, guess)
        self.assertNotIn(v.file.name, c.get(url("detail", d.pk)).content.decode())

    def test_the_detail_page_never_exposes_a_storage_path(self):
        d = self.doc()
        body = self.client_for(self.hr).get(url("detail", d.pk)).content.decode()
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), body)

    def test_each_upload_gets_a_different_name(self):
        a, b = self.doc(title="1"), self.doc(title="2")
        self.assertNotEqual(a.versions.get().file.name, b.versions.get().file.name)


class UploadFlowTests(Base):
    def payload(self, **kw):
        d = {"title": "Yangi", "category": self.cat.pk, "access_level": "general", "file": upload("x.pdf")}
        d.update(kw)
        return d

    def test_employee_cannot_upload(self):
        c = self.client_for(self.in_a)
        self.assertEqual(c.get(url("create")).status_code, 403)
        self.assertEqual(c.post(url("create"), self.payload()).status_code, 403)
        self.assertEqual(Document.objects.count(), 0)

    def test_rejected_uploads_create_nothing_and_are_audited_by_reason_only(self):
        c = self.client_for(self.hr)
        for f in (upload("x.exe", b"MZ"), upload("x.pdf", b"<html>"), upload("x.php.pdf", PDF), upload("x.docx", docx_bytes([("word/vbaProject.bin", "x")]))):
            r = c.post(url("create"), self.payload(file=f))
            self.assertEqual(r.status_code, 200)
        self.assertEqual((Document.objects.count(), DocumentVersion.objects.count()), (0, 0))
        reasons = [e.meta["reason"] for e in AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED)]
        self.assertEqual(sorted(reasons), ["double_extension", "extension", "office_active", "signature"])
        for e in AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED):
            self.assertNotIn("x.exe", str(e.meta))

    def test_too_large_is_refused_by_the_server(self):
        with override_settings(DOCUMENT_MAX_BYTES=50):
            r = self.client_for(self.hr).post(url("create"), self.payload(file=upload("x.pdf", PDF + b"0" * 100)))
        self.assertContains(r, "oshmasligi kerak")
        self.assertEqual(Document.objects.count(), 0)

    def test_department_level_requires_department(self):
        r = self.client_for(self.hr).post(url("create"), self.payload(access_level="department"))
        self.assertContains(r, "bo‘lim tanlang")
        self.assertEqual(Document.objects.count(), 0)

    def test_upload_is_audited_without_content_or_name(self):
        self.client_for(self.hr).post(url("create"), self.payload(file=upload("shaxsiy-ism.pdf")))
        e = AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_UPLOADED)
        self.assertEqual(set(e.meta), {"version", "size", "ext"})
        self.assertNotIn("shaxsiy", str(e.meta))

    def test_new_version_keeps_the_old_one(self):
        d = self.doc(creator=self.hr)
        c = self.client_for(self.hr)
        c.post(url("version_add", d.pk), {"file": upload("v2.pdf", PDF + b"%2"), "comment": "tuzatish"})
        self.assertEqual(list(d.versions.order_by("number").values_list("number", flat=True)), [1, 2])
        self.assertEqual(b"".join(c.get(url("download", d.pk)).streaming_content), PDF + b"%2")
        self.assertEqual(b"".join(c.get(url("download_version", d.pk, 1)).streaming_content), PDF)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_VERSION_ADDED).exists())

    def test_bad_version_file_is_refused(self):
        d = self.doc(creator=self.hr)
        self.client_for(self.hr).post(url("version_add", d.pk), {"file": upload("v2.html", b"<html>")})
        self.assertEqual(d.versions.count(), 1)

    def test_non_authors_without_all_rights_cannot_add_versions_or_edit(self):
        d = self.doc(creator=self.hr, level="general")
        c = self.client_for(self.head)  # department head: may add documents, but not touch HR's
        self.assertEqual(c.post(url("version_add", d.pk), {"file": upload("v2.pdf")}).status_code, 403)
        self.assertEqual(c.get(url("edit", d.pk)).status_code, 403)
        self.assertEqual(d.versions.count(), 1)

    def test_no_versions_can_be_added_to_an_archived_document(self):
        d = self.doc(creator=self.hr, status="archived")
        self.assertEqual(self.client_for(self.hr).post(url("version_add", d.pk), {"file": upload("v2.pdf")}).status_code, 403)


class LifecycleTests(Base):
    def test_archive_and_restore_with_audit(self):
        d = self.doc(creator=self.head)
        c = self.client_for(self.head)
        c.post(url("archive", d.pk))
        d.refresh_from_db()
        self.assertEqual(d.status, "archived")
        self.assertEqual(self.client_for(self.in_a).get(url("detail", d.pk)).status_code, 403)
        c.post(url("restore", d.pk))
        d.refresh_from_db()
        self.assertEqual(d.status, "active")
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_ARCHIVED, user=self.head).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_RESTORED, user=self.head).exists())

    def test_archive_forbidden_for_others_and_needs_post(self):
        d = self.doc(creator=self.hr)
        self.assertEqual(self.client_for(self.in_a).post(url("archive", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.head).post(url("archive", d.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.hr).get(url("archive", d.pk)).status_code, 405)
        d.refresh_from_db()
        self.assertEqual(d.status, "active")

    def test_edit_audits_changed_field_names_only(self):
        d = self.doc(creator=self.hr, title="Eski")
        data = {"title": "Yangi-nom", "number": "", "category": self.cat.pk, "doc_date": "", "description": "", "access_level": "general", "department": ""}
        self.client_for(self.hr).post(url("edit", d.pk), data)
        d.refresh_from_db()
        self.assertEqual(d.title, "Yangi-nom")
        e = AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_UPDATED)
        self.assertEqual(e.meta["fields"], ["title"])
        self.assertNotIn("Yangi-nom", str(e.meta))

    def test_csrf_is_enforced_on_state_changes(self):
        d = self.doc(creator=self.hr)
        c = Client(enforce_csrf_checks=True)
        login_with_two_factor(c, self.hr)
        self.assertEqual(c.post(url("archive", d.pk)).status_code, 403)

    def test_html_in_metadata_is_escaped(self):
        d = self.doc(creator=self.hr, title="<script>alert(1)</script>")
        body = self.client_for(self.hr).get(url("detail", d.pk)).content.decode()
        self.assertNotIn("<script>alert(1)</script>", body)

    def test_documents_have_no_django_admin_pages(self):
        from django.contrib import admin

        from .models import Document as D, DocumentVersion as V

        self.assertNotIn(D, admin.site._registry)
        self.assertNotIn(V, admin.site._registry)
