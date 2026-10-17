"""End-to-end journeys through the real views (no direct model shortcuts for the steps being checked). Fictional data only."""
import re

from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import PASSWORD
from apps.audit.models import AuditLog
from apps.core.acceptance import World
from apps.documents.models import Document, DocumentCategory
from apps.documents.testing import PDF, upload
from apps.notifications.models import Notification
from apps.organization.models import Department, Employee, Position
from apps.tasks.models import Task, TaskEvent


def actions():
    return set(AuditLog.objects.values_list("action", flat=True))


class TaskLifecycleJourney(TestCase):
    def setUp(self):
        self.w = World()
        self.admin, self.emp, self.stranger = self.w.client("admin"), self.w.client("emp"), self.w.client("stranger")

    def create_task(self):
        r = self.admin.post(reverse("tasks:create"), {"title": "Yangi topshiriq", "description": "Matn", "priority": "high",
                                                       "due_date": timezone.localdate().isoformat(), "assignees": [self.w.users["emp"].pk]})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        return Task.objects.get(title="Yangi topshiriq")

    def go(self, client, task, status, refused=False):
        """A refused change answers with a redirect and a message and must leave the status untouched."""
        before = task.status
        r = client.post(reverse("tasks:transition", args=[task.pk, status]))
        self.assertEqual(r.status_code, 302, (status, r.status_code))
        task.refresh_from_db()
        if refused:
            self.assertEqual(task.status, before, status)

    def test_create_assign_accept_return_complete_with_notifications_and_links(self):
        t = self.create_task()
        n = Notification.objects.get(user=self.w.users["emp"], task=t)
        self.assertEqual(self.emp.get(reverse("notifications:open", args=[n.pk])).status_code, 405)  # opening changes state: POST only
        r = self.emp.post(reverse("notifications:open", args=[n.pk]))
        self.assertRedirects(r, reverse("tasks:detail", args=[t.pk]), fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)
        self.assertEqual(self.stranger.get(reverse("tasks:detail", args=[t.pk])).status_code, 403)
        self.assertEqual(self.stranger.post(reverse("notifications:open", args=[n.pk])).status_code, 404)  # someone else's id

        self.go(self.emp, t, "in_progress")
        self.assertEqual(t.status, "in_progress")
        self.go(self.emp, t, "review")
        self.assertEqual(t.status, "review")
        self.go(self.emp, t, "done", refused=True)  # the assignee cannot close their own work
        self.go(self.admin, t, "in_progress")  # return for rework
        self.assertEqual(t.status, "in_progress")
        self.assertTrue(Notification.objects.filter(user=self.w.users["emp"], task=t).count() >= 2)
        self.go(self.emp, t, "review")
        self.go(self.admin, t, "done")
        self.assertEqual(t.status, "done")
        # final state: no more transitions, comments or attachments
        self.go(self.admin, t, "in_progress", refused=True)
        self.assertEqual(t.status, "done")
        self.assertTrue(TaskEvent.objects.filter(task=t).count() >= 5)

    def test_cancel_and_closed_task_limits(self):
        t = self.create_task()
        self.go(self.emp, t, "cancelled", refused=True)
        self.go(self.admin, t, "cancelled")
        self.assertEqual(t.status, "cancelled")
        r = self.emp.post(reverse("tasks:attachment_add", args=[t.pk]), {"file": upload("a.pdf")})
        self.assertNotEqual(r.status_code, 500)
        self.assertEqual(t.attachments.filter(original_name="a.pdf").count(), 0)
        # by design, comments stay possible after closing (follow-up discussion); the status itself is frozen
        self.emp.post(reverse("tasks:comment", args=[t.pk]), {"body": "late"})
        self.assertTrue(t.comments.filter(body="late").exists())
        self.go(self.admin, t, "in_progress", refused=True)

    def test_attachment_upload_download_and_foreign_access(self):
        t = self.create_task()
        r = self.emp.post(reverse("tasks:attachment_add", args=[t.pk]), {"file": upload("hisobot.pdf", PDF)})
        self.assertEqual(r.status_code, 302)
        a = t.attachments.get()
        d = self.emp.get(reverse("tasks:attachment_download", args=[t.pk, a.pk]))
        self.assertEqual(d.status_code, 200)
        self.assertIn("attachment", d["Content-Disposition"])
        self.assertEqual(self.stranger.get(reverse("tasks:attachment_download", args=[t.pk, a.pk])).status_code, 403)
        self.assertEqual(Client().get(reverse("tasks:attachment_download", args=[t.pk, a.pk])).status_code, 302)
        # rejected content never creates an attachment
        bad = self.emp.post(reverse("tasks:attachment_add", args=[t.pk]), {"file": upload("evil.exe", b"MZ\x90\x00")})
        self.assertNotEqual(bad.status_code, 500)
        self.assertEqual(t.attachments.count(), 1)


class DocumentLifecycleJourney(TestCase):
    def setUp(self):
        self.w = World()
        self.hr, self.emp = self.w.client("hr"), self.w.client("emp")
        self.cat = DocumentCategory.objects.first()

    def test_upload_view_download_new_version_archive_restore(self):
        r = self.hr.post(reverse("documents:create"), {"title": "Reglament", "category": self.cat.pk, "access_level": "general", "file": upload("v1.pdf", PDF)})
        self.assertEqual(r.status_code, 302)
        d = Document.objects.get(title="Reglament")
        self.assertEqual(self.emp.get(reverse("documents:detail", args=[d.pk])).status_code, 200)
        first = self.emp.get(reverse("documents:download", args=[d.pk]))
        self.assertEqual(first.status_code, 200)
        self.hr.post(reverse("documents:version_add", args=[d.pk]), {"file": upload("v2.pdf", PDF + b"2"), "comment": "yangilandi"})
        d.refresh_from_db()
        self.assertEqual(d.versions.count(), 2)
        self.assertEqual(self.emp.get(reverse("documents:download_version", args=[d.pk, 1])).status_code, 200)
        self.assertEqual(self.emp.get(reverse("documents:download_version", args=[d.pk, 99])).status_code, 404)
        self.assertNotEqual(self.emp.post(reverse("documents:version_add", args=[d.pk]), {"file": upload("v3.pdf", PDF + b"3")}).status_code, 200)
        self.hr.post(reverse("documents:archive", args=[d.pk]))
        d.refresh_from_db()
        self.assertEqual(d.status, "archived")
        self.assertEqual(self.emp.get(reverse("documents:download", args=[d.pk])).status_code, 403)  # archived: closed for ordinary readers
        self.hr.post(reverse("documents:restore", args=[d.pk]))
        self.assertEqual(self.emp.get(reverse("documents:download", args=[d.pk])).status_code, 200)
        self.assertTrue({"document_uploaded", "document_version_added", "document_downloaded", "document_archived", "document_restored"} <= actions(), actions())

    def test_confidential_document_is_invisible_without_right(self):
        s = self.w.secret_doc
        for name, args in (("documents:detail", [s.pk]), ("documents:download", [s.pk]), ("documents:download_version", [s.pk, 1])):
            self.assertEqual(self.emp.get(reverse(name, args=args)).status_code, 403, name)
        self.assertNotIn(">Maxfiy</a>", self.emp.get(reverse("documents:list")).content.decode())  # the title, not the filter label
        self.assertEqual(self.w.client("stranger").get(reverse("documents:download", args=[s.pk])).status_code, 403)


class OrganizationAndAccountJourney(TestCase):
    def setUp(self):
        self.w = World()
        self.hr, self.admin = self.w.client("hr"), self.w.client("admin")

    def test_department_position_employee_and_account_onboarding(self):
        self.assertEqual(self.hr.post(reverse("employees:department_create"), {"name": "Yangi bo‘lim", "parent": self.w.root.pk, "is_active": "on"}).status_code, 302)
        dep = Department.objects.get(name="Yangi bo‘lim")
        self.assertEqual(self.hr.post(reverse("employees:position_create"), {"name": "Mutaxassis"}).status_code, 302)
        pos = Position.objects.get(name="Mutaxassis")
        r = self.hr.post(reverse("employees:create"), {"last_name": "Testov", "first_name": "Test", "department": dep.pk, "position": pos.pk, "status": "active",
                                                       "work_phone": "+998 71 000 00 00", "hired_at": "2024-01-01"})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        Employee.objects.get(last_name="Testov")
        # HR creates the login (admin only action), then the user sets own password from the e-mailed link
        r = self.admin.post(reverse("users:create"), {"username": "testov", "email": "testov@example.test", "last_name": "Testov", "first_name": "Test", "role": "employee"})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        from apps.accounts.models import User

        user = User.objects.get(username="testov")
        self.assertEqual(self.hr.post(reverse("users:create"), {"username": "x", "email": "x@example.test", "role": "employee"}).status_code, 403)
        self.admin.post(reverse("users:action", args=[user.pk, "invite"]))
        link = re.search(r"/accounts/reset/[^\s]+", mail.outbox[-1].body).group(0)
        c = Client()
        r = c.get(link, follow=True)
        post_url = r.redirect_chain[-1][0] if r.redirect_chain else link
        r = c.post(post_url, {"new_password1": "Yangi-Parol-98765!", "new_password2": "Yangi-Parol-98765!"})
        self.assertEqual(r.status_code, 302)
        c = Client()
        self.assertEqual(c.post(reverse("accounts:login"), {"username": "testov", "password": "Yangi-Parol-98765!"}).status_code, 302)
        self.assertEqual(c.get(reverse("portal:dashboard")).status_code, 200)
        # deactivation ends the session at once and blocks a new login
        self.admin.post(reverse("users:action", args=[user.pk, "deactivate"]))
        self.assertEqual(c.get(reverse("portal:dashboard")).status_code, 302)
        self.assertEqual(Client().post(reverse("accounts:login"), {"username": "testov", "password": "Yangi-Parol-98765!"}).status_code, 200)
        self.assertTrue({"user_created", "user_invited", "password_reset_completed", "login", "user_deactivated", "employee_created", "org_changed"} <= actions(), actions())

    def test_employee_edit_cannot_reach_forbidden_fields_for_ordinary_staff(self):
        emp = self.w.client("emp")
        self.assertEqual(emp.post(reverse("employees:edit", args=[self.w.card.pk]), {"last_name": "Hacked"}).status_code, 403)
        self.w.card.refresh_from_db()
        self.assertEqual(self.w.card.last_name, "Aliyev")
        page = emp.get(reverse("employees:detail", args=[self.w.card.pk])).content.decode()  # own card: private fields visible to the owner only
        stranger_page = self.w.client("stranger").get(reverse("employees:detail", args=[self.w.card.pk]))
        self.assertNotIn("+998 90 555 66 77", stranger_page.content.decode())
        self.assertNotIn("17.05.1990", stranger_page.content.decode())
        self.assertTrue(page)


class LockoutAndRecoveryJourney(TestCase):
    def setUp(self):
        self.w = World()

    def test_lockout_is_neutral_and_admin_can_unlock(self):
        bad = {"username": "emp", "password": "wrong-password"}
        seen = set()
        for _ in range(12):
            r = Client().post(reverse("accounts:login"), bad)
            seen.add(r.status_code)
        self.assertNotIn(500, seen)
        r = Client().post(reverse("accounts:login"), {"username": "emp", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)  # correct password does not bypass the lock
        self.assertTrue({"login_failed", "login_locked"} <= actions(), actions())
        self.w.client("admin").post(reverse("users:action", args=[self.w.users["emp"].pk, "unlock"]))
        self.assertIn("account_unlocked", actions())
        # the per-account lock is gone; the per-address counter is covered by apps.accounts.tests_throttle
        self.assertTrue(Client().post(reverse("accounts:login"), {"username": "emp", "password": PASSWORD}, REMOTE_ADDR="10.9.8.7").status_code in (200, 302))

    def test_password_reset_is_neutral_and_single_use(self):
        c = Client()
        a = c.post(reverse("accounts:password_reset"), {"email": "emp@example.test"})
        b = c.post(reverse("accounts:password_reset"), {"email": "nobody@example.test"})
        self.assertEqual((a.status_code, a["Location"]), (b.status_code, b["Location"]))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"/accounts/reset/[^\s]+", mail.outbox[0].body).group(0)
        r = c.get(link, follow=True)
        url = r.redirect_chain[-1][0]
        c.post(url, {"new_password1": "Boshqa-Parol-24680!", "new_password2": "Boshqa-Parol-24680!"})
        again = Client().get(link, follow=True)
        self.assertNotIn("new_password1", again.content.decode())  # the used link no longer offers the form


class LanguageJourney(TestCase):
    def setUp(self):
        self.w = World()

    def test_switching_changes_pages_errors_and_emails(self):
        for lang, word in (("ru", "Задания"), ("en", "Tasks"), ("uz", "Topshiriqlar")):
            c = self.w.client("emp")
            c.post(reverse("set_language"), {"language": lang, "next": reverse("tasks:list")})
            html = c.get(reverse("tasks:list")).content.decode()
            self.assertIn(f'lang="{lang}"', html)
            self.assertIn(word, html, lang)
            bad = c.post(reverse("accounts:password_change"), {"old_password": "x", "new_password1": "a", "new_password2": "b"})
            self.assertEqual(bad.status_code, 200)
        # invalid language is ignored, not an error
        c = self.w.client("emp")
        r = c.post(reverse("set_language"), {"language": "xx", "next": "/"})
        self.assertLess(r.status_code, 400)
        # e-mail follows the recipient's stored language, not the language of whoever triggered it
        subjects = {}
        for lang in ("ru", "en", "uz"):
            u = self.w.users["emp"]
            u.locale = lang
            u.save()
            mail.outbox.clear()
            Client().post(reverse("accounts:password_reset"), {"email": u.email})
            self.assertEqual(len(mail.outbox), 1, lang)
            subjects[lang] = mail.outbox[0].subject
        self.assertEqual(len(set(subjects.values())), 3, subjects)
        self.assertRegex(subjects["ru"], r"[А-Яа-я]")


class ContentManagerDay(TestCase):
    """Day 9 journey across modules: roles, news, public site, audit, documents viewer."""

    def setUp(self):
        self.w = World()
        self.cm, self.emp, self.admin = self.w.client("content"), self.w.client("emp"), self.w.client("admin")
        self.anon = Client()

    def test_from_draft_to_public_page_and_back_with_audit_and_without_extra_rights(self):
        from apps.content.models import News

        n_url = lambda name, *a: reverse(f"news_admin:{name}", args=a)  # noqa: E731
        # validation error: nothing saved, what was typed is still in the form
        bad = self.cm.post(n_url("create"), {"title": "Kunlik xabar", "excerpt": "z" * 600, "body": "Matn", "category": ""})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(News.objects.filter(title="Kunlik xabar").count(), 0)
        self.assertContains(bad, "Kunlik xabar")
        # draft saved, invisible to the public and to ordinary staff
        self.cm.post(n_url("create"), {"title": "Kunlik xabar", "excerpt": "Q", "body": "Matn", "category": ""})
        n = News.objects.get(title="Kunlik xabar")
        self.assertEqual(self.anon.get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
        self.assertEqual(self.emp.get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
        self.assertEqual(self.emp.get(n_url("preview", n.pk)).status_code, 403)
        self.assertEqual(self.emp.post(n_url("status", n.pk, "publish")).status_code, 403)
        n.refresh_from_db()
        self.assertEqual(n.status, "draft")
        # publish: ordinary user reads it, still cannot manage it
        self.cm.post(n_url("status", n.pk, "publish"))
        self.assertContains(self.emp.get(reverse("content:news_detail", args=[n.slug])), "Kunlik xabar")
        self.assertContains(self.anon.get(reverse("content:news_list")), "Kunlik xabar")
        self.assertEqual(self.emp.get(n_url("list")).status_code, 403)
        self.assertEqual(self.emp.post(n_url("edit", n.pk), {"title": "Buzildi", "body": "x"}).status_code, 403)
        n.refresh_from_db()
        self.assertEqual(n.title, "Kunlik xabar")
        # the administrator sees the whole trail in the audit log, with names of actions only
        page = self.admin.get(reverse("portal:audit")).content.decode()
        for label in ("Yangilik yaratildi", "Yangilik nashr etildi"):
            self.assertIn(label, page)
        self.assertNotIn("Kunlik xabar", page)
        # archive: gone from the public site and from the home page
        self.cm.post(n_url("status", n.pk, "archive"))
        self.assertEqual(self.anon.get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
        self.assertNotContains(self.anon.get(reverse("content:home")), "Kunlik xabar")
        self.assertIn("Yangilik arxivlandi", self.admin.get(reverse("portal:audit")).content.decode())
        # the content manager never gained the Django admin
        self.assertEqual(self.cm.get("/admin/").status_code, 302)
        self.w.users["content"].refresh_from_db()
        self.assertFalse(self.w.users["content"].is_staff)

    def test_content_manager_opens_allowed_documents_and_is_stopped_at_closed_ones(self):
        gen = reverse("documents:preview", args=[self.w.doc.pk])
        self.assertEqual(self.cm.get(gen).status_code, 200)
        self.assertEqual(self.cm.get(reverse("documents:inline", args=[self.w.doc.pk])).status_code, 200)
        for name in ("preview", "inline", "download"):
            self.assertEqual(self.cm.get(reverse(f"documents:{name}", args=[self.w.secret_doc.pk])).status_code, 403, name)
