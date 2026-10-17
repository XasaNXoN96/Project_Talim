from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.documents.testing import PDF, docx_bytes, upload
from apps.organization.models import Department, Employee

from .models import Task, TaskAttachment, TaskEvent


def url(name, *args):
    return reverse(f"tasks:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.dept, self.other = Department.objects.create(name="A"), Department.objects.create(name="B")
        self.head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=self.head, role=Group.objects.get(name="department_head"), scope="department", department=self.dept)
        Employee.objects.create(last_name="Head", first_name="H", department=self.dept, user=self.head, status="active")
        self.worker, self.worker2, self.stranger = (self._person(n, d) for n, d in (("worker", self.dept), ("worker2", self.dept), ("stranger", self.other)))
        self.admin = make_user("boss", role="admin")
        self.task = self.make_task()

    def _person(self, name, dept):
        u = make_user(name, role="employee")
        Employee.objects.create(last_name=name.title(), first_name="X", department=dept, user=u, status="active")
        return u

    def make_task(self, assignees=None, **kw):
        t = Task.objects.create(title=kw.pop("title", "Hisobot"), created_by=self.head, **kw)
        t.assignees.set(assignees or [self.worker])
        return t

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def attach(self, user, task=None, name="x.pdf", data=PDF):
        task = task or self.task
        return self.client_for(user).post(url("attachment_add", task.pk), {"file": upload(name, data)})

    def stored(self, task=None, user=None):
        task = task or self.task
        before = set(task.attachments.values_list("pk", flat=True))
        self.attach(user or self.worker, task, name=f"f{len(before)}.pdf", data=PDF + str(len(before)).encode())
        return task.attachments.exclude(pk__in=before).get()


class UploadTests(Base):
    def test_assignee_and_creator_can_attach_others_cannot(self):
        for user, expected in ((self.worker, 1), (self.head, 2), (self.admin, 3)):
            self.attach(user, name=f"{user.username}.pdf")
            self.assertEqual(self.task.attachments.count(), expected, user.username)
        for user in (self.stranger, self.worker2):
            self.assertEqual(self.attach(user).status_code, 403, user.username)
        self.assertEqual(self.task.attachments.count(), 3)

    def test_stored_privately_with_a_random_name_and_audited_without_names(self):
        a = self.stored(user=self.worker)
        self.assertRegex(a.file.name, r"^[0-9a-f]{2}/[0-9a-f]{32}\.pdf$")
        self.assertTrue(Path(a.file.path).exists())
        with self.assertRaises(ValueError):
            a.file.url
        e = AuditLog.objects.get(action=AuditLog.Action.TASK_ATTACHMENT_ADDED)
        self.assertEqual((e.user, e.object_id), (self.worker, str(self.task.pk)))
        self.assertEqual(set(e.meta), {"attachment", "ext", "size"})
        ev = self.task.events.get(kind=TaskEvent.Kind.ATTACHED)
        self.assertNotIn("x.pdf", str(ev.meta))

    def test_the_same_validation_as_documents_applies(self):
        for name, data in (("x.exe", b"MZ"), ("x.php.pdf", PDF), ("x.pdf", b"<html>"), ("x.docx", docx_bytes([("word/vbaProject.bin", "x")]))):
            self.attach(self.worker, name=name, data=data)
        self.assertEqual(self.task.attachments.count(), 0)
        reasons = sorted(e.meta["reason"] for e in AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED))
        self.assertEqual(reasons, ["double_extension", "extension", "office_active", "signature"])
        self.assertTrue(all(e.object_type == "Task" for e in AuditLog.objects.filter(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED)))

    def test_too_large_is_refused(self):
        with override_settings(DOCUMENT_MAX_BYTES=50):
            self.attach(self.worker, data=PDF + b"0" * 100)
        self.assertEqual(self.task.attachments.count(), 0)

    def test_antivirus_applies_and_fails_closed(self):
        from apps.documents.tests_scanner import FakeClamd, scanning

        for behaviour in ("found", "silent", "error"):
            fake = FakeClamd(behaviour).start()
            try:
                with scanning(fake, CLAMAV_TIMEOUT=0.5):
                    self.attach(self.worker)
            finally:
                fake.stop()
        self.assertEqual(self.task.attachments.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.FILE_THREAT_DETECTED, object_type="Task").exists())
        fake = FakeClamd("ok").start()
        try:
            with scanning(fake):
                self.attach(self.worker)
        finally:
            fake.stop()
        a = self.task.attachments.get()
        self.assertEqual(a.scan_status, "clean")

    def test_limit_per_task(self):
        for i in range(TaskAttachment.MAX_PER_TASK):
            self.attach(self.worker, name=f"f{i}.pdf", data=PDF + str(i).encode())
        self.attach(self.worker, name="extra.pdf")
        self.assertEqual(self.task.attachments.count(), TaskAttachment.MAX_PER_TASK)

    def test_closed_and_cancelled_tasks_accept_no_new_files(self):
        for status in ("done", "cancelled"):
            t = self.make_task(status=status, title=status)
            for user in (self.worker, self.head, self.admin):
                self.assertEqual(self.attach(user, t).status_code, 403, (status, user.username))
            self.assertEqual(t.attachments.count(), 0)

    def test_get_not_allowed_and_csrf(self):
        self.assertEqual(self.client_for(self.worker).get(url("attachment_add", self.task.pk)).status_code, 405)
        c = Client(enforce_csrf_checks=True)
        login_with_two_factor(c, self.worker)
        self.assertEqual(c.post(url("attachment_add", self.task.pk), {"file": upload()}).status_code, 403)

    def test_anonymous(self):
        self.assertEqual(Client().post(url("attachment_add", self.task.pk), {"file": upload()}).status_code, 302)


class DownloadTests(Base):
    def test_download_for_those_who_can_see_the_task_and_is_audited(self):
        a = self.stored()
        for user in (self.worker, self.head, self.admin):
            r = self.client_for(user).get(url("attachment_download", self.task.pk, a.pk))
            self.assertEqual(r.status_code, 200, user.username)
            self.assertEqual(b"".join(r.streaming_content), PDF + b"0")
            self.assertTrue(r["Content-Disposition"].startswith("attachment;"))
            self.assertEqual(r["Content-Type"], "application/octet-stream")
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.TASK_ATTACHMENT_DOWNLOADED).count(), 3)

    def test_others_get_403_and_nothing_is_audited(self):
        a = self.stored()
        for user in (self.stranger, self.worker2, make_user("sys", role="sysadmin")):
            self.assertEqual(self.client_for(user).get(url("attachment_download", self.task.pk, a.pk)).status_code, 403, user.username)
        self.assertEqual(Client().get(url("attachment_download", self.task.pk, a.pk)).status_code, 302)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.TASK_ATTACHMENT_DOWNLOADED).exists())

    def test_swapping_ids_between_tasks_gives_nothing(self):
        mine = self.stored(task=self.task)
        secret_task = self.make_task(assignees=[self.stranger], title="Begona")
        secret = self.stored(task=secret_task, user=self.stranger)
        c = self.client_for(self.worker)
        self.assertEqual(c.get(url("attachment_download", secret_task.pk, secret.pk)).status_code, 403)  # task not visible
        self.assertEqual(c.get(url("attachment_download", self.task.pk, secret.pk)).status_code, 404)  # attachment of another task
        self.assertEqual(c.post(url("attachment_remove", self.task.pk, secret.pk)).status_code, 404)
        self.assertEqual(c.get(url("attachment_download", self.task.pk, mine.pk)).status_code, 200)
        secret.refresh_from_db()
        self.assertIsNone(secret.removed_at)

    def test_closed_and_cancelled_tasks_do_not_widen_access(self):
        a = self.stored()
        for status in ("done", "cancelled"):
            self.task.status = status
            self.task.save()
            self.assertEqual(self.client_for(self.worker).get(url("attachment_download", self.task.pk, a.pk)).status_code, 200)  # still readable by participants
            self.assertEqual(self.client_for(self.stranger).get(url("attachment_download", self.task.pk, a.pk)).status_code, 403)
            self.assertEqual(self.client_for(self.worker2).get(url("attachment_download", self.task.pk, a.pk)).status_code, 403)

    def test_reassigning_the_task_removes_the_old_assignees_access(self):
        a = self.stored()
        self.task.assignees.set([self.worker2])
        self.assertEqual(self.client_for(self.worker).get(url("attachment_download", self.task.pk, a.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.worker2).get(url("attachment_download", self.task.pk, a.pk)).status_code, 200)

    def test_infected_after_rescan_is_never_served(self):
        a = self.stored()
        a.scan_status = "infected"
        a.save()
        self.assertEqual(self.client_for(self.worker).get(url("attachment_download", self.task.pk, a.pk)).status_code, 404)

    def test_no_public_path_exists(self):
        a = self.stored()
        c = self.client_for(self.worker)
        for guess in (f"/media/{a.file.name}", f"/static/{a.file.name}", f"/{a.file.name}"):
            self.assertEqual(c.get(guess).status_code, 404, guess)
        page = c.get(url("detail", self.task.pk)).content.decode()
        self.assertNotIn(a.file.name, page)
        self.assertIn(url("attachment_download", self.task.pk, a.pk), page)

    def test_missing_file_on_disk_is_404(self):
        a = self.stored()
        Path(a.file.path).unlink()
        self.assertEqual(self.client_for(self.worker).get(url("attachment_download", self.task.pk, a.pk)).status_code, 404)


class RemoveTests(Base):
    def test_uploader_and_manager_can_unlink_with_history_and_audit_file_stays(self):
        a = self.stored(user=self.worker)
        path = Path(a.file.path)
        self.client_for(self.worker).post(url("attachment_remove", self.task.pk, a.pk))
        a.refresh_from_db()
        self.assertIsNotNone(a.removed_at)
        self.assertEqual(a.removed_by, self.worker)
        self.assertTrue(path.exists())  # kept for audit and backups
        self.assertTrue(self.task.events.filter(kind=TaskEvent.Kind.DETACHED).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TASK_ATTACHMENT_REMOVED, user=self.worker).exists())
        b = self.stored(user=self.worker)
        self.client_for(self.head).post(url("attachment_remove", self.task.pk, b.pk))
        b.refresh_from_db()
        self.assertIsNotNone(b.removed_at)

    def test_unlinked_file_is_no_longer_served_or_listed(self):
        a = self.stored()
        self.client_for(self.head).post(url("attachment_remove", self.task.pk, a.pk))
        self.assertEqual(self.client_for(self.worker).get(url("attachment_download", self.task.pk, a.pk)).status_code, 404)
        self.assertEqual(self.client_for(self.admin).get(url("attachment_download", self.task.pk, a.pk)).status_code, 404)
        self.assertNotContains(self.client_for(self.worker).get(url("detail", self.task.pk)), "attachment_download")

    def test_other_assignee_cannot_unlink_someone_elses_file(self):
        other = self.make_task(assignees=[self.worker, self.worker2], title="Ikki")
        a = self.stored(task=other, user=self.worker)
        self.assertEqual(self.client_for(self.worker2).post(url("attachment_remove", other.pk, a.pk)).status_code, 403)
        self.assertEqual(self.client_for(self.stranger).post(url("attachment_remove", other.pk, a.pk)).status_code, 403)
        a.refresh_from_db()
        self.assertIsNone(a.removed_at)

    def test_no_unlinking_on_closed_tasks(self):
        a = self.stored()
        for status in ("done", "cancelled"):
            self.task.status = status
            self.task.save()
            self.assertEqual(self.client_for(self.head).post(url("attachment_remove", self.task.pk, a.pk)).status_code, 403)
        a.refresh_from_db()
        self.assertIsNone(a.removed_at)

    def test_unlinking_twice_is_404_and_get_is_405(self):
        a = self.stored()
        self.assertEqual(self.client_for(self.head).get(url("attachment_remove", self.task.pk, a.pk)).status_code, 405)
        self.client_for(self.head).post(url("attachment_remove", self.task.pk, a.pk))
        self.assertEqual(self.client_for(self.head).post(url("attachment_remove", self.task.pk, a.pk)).status_code, 404)

    def test_integrity_command_covers_attachments(self):
        from django.core.management.base import CommandError

        a = self.stored()
        call_command("verify_document_files")
        Path(a.file.path).write_bytes(b"tampered")
        with self.assertRaises(CommandError):
            call_command("verify_document_files")

    def test_rescan_covers_attachments(self):
        from apps.documents.tests_scanner import FakeClamd, scanning

        a = self.stored()
        fake = FakeClamd("found").start()
        try:
            with scanning(fake):
                call_command("scan_documents")
        finally:
            fake.stop()
        a.refresh_from_db()
        self.assertEqual(a.scan_status, "infected")
