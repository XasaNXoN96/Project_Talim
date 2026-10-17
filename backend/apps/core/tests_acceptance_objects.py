"""Object-level access table: exactly who may open which object. A change in any cell is a deliberate policy change."""
from django.test import TestCase
from django.urls import reverse

from .acceptance import World

OK, DENY, LOGIN, GONE = 200, 403, 302, 404


class ObjectAccessTable(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = World()

    def status(self, actor, name, method="get", **kw):
        c = self.w.client(actor)
        return getattr(c, method)(reverse(name, kwargs=kw)).status_code

    def check(self, name, expected, method="get", **kw):
        got = {actor: self.status(actor, name, method, **kw) for actor in expected}
        self.assertEqual(got, expected, name)

    def test_task_detail_and_attachment_download(self):
        pk, att = self.w.task.pk, self.w.attachment.pk
        # emp = assignee; head sits above emp's department; admin created the task
        expected = {"anon": LOGIN, "emp": OK, "stranger": DENY, "content": DENY, "head": OK, "hr": DENY, "admin": OK, "sysadmin": DENY, "superuser": OK}
        self.check("tasks:detail", expected, pk=pk)
        self.check("tasks:attachment_download", expected, pk=pk, attachment_id=att)

    def test_closed_and_cancelled_tasks_do_not_widen_access_to_files_or_the_card(self):
        expected = {"anon": LOGIN, "emp": OK, "stranger": DENY, "content": DENY, "head": OK, "hr": DENY, "admin": OK, "sysadmin": DENY, "superuser": OK}
        for status in ("done", "cancelled"):
            self.w.task.status = status
            self.w.task.save()
            self.check("tasks:detail", expected, pk=self.w.task.pk)
            self.check("tasks:attachment_download", expected, pk=self.w.task.pk, attachment_id=self.w.attachment.pk)

    def test_task_edit_status_and_attachment_management(self):
        pk = self.w.task.pk
        # edit: change_task + (creator, or covered): admin (creator) yes; head covers emp's department yes; assignee/others no
        self.check("tasks:edit", {"emp": DENY, "stranger": DENY, "head": OK, "hr": DENY, "admin": OK, "sysadmin": DENY}, pk=pk)
        # sending without an assignee role: a stranger cannot move or comment
        for actor in ("stranger", "hr", "sysadmin", "content"):
            self.assertEqual(self.status(actor, "tasks:transition", "post", pk=pk, status="done"), DENY, actor)
            self.assertEqual(self.status(actor, "tasks:comment", "post", pk=pk), DENY, actor)
            self.assertEqual(self.status(actor, "tasks:attachment_add", "post", pk=pk), DENY, actor)
        self.assertEqual(self.w.task.__class__.objects.get(pk=pk).status, "review")

    def test_general_document(self):
        pk = self.w.doc.pk
        expected = {"anon": LOGIN, "emp": OK, "stranger": OK, "content": OK, "head": OK, "hr": OK, "admin": OK, "sysadmin": DENY, "superuser": OK}
        self.check("documents:detail", expected, pk=pk)
        self.check("documents:download", expected, pk=pk)
        self.check("documents:download_version", expected, pk=pk, number=1)

    def test_confidential_document(self):
        pk = self.w.secret_doc.pk
        expected = {"anon": LOGIN, "emp": DENY, "stranger": DENY, "content": DENY, "head": DENY, "hr": OK, "admin": OK, "sysadmin": DENY, "superuser": OK}
        self.check("documents:detail", expected, pk=pk)
        self.check("documents:download", expected, pk=pk)
        self.check("documents:download_version", expected, pk=pk, number=1)
        for actor in ("emp", "stranger", "content", "head", "sysadmin"):
            self.assertEqual(self.status(actor, "documents:edit", pk=pk), DENY, actor)
            self.assertEqual(self.status(actor, "documents:archive", "post", pk=pk), DENY, actor)
            self.assertEqual(self.status(actor, "documents:version_add", "post", pk=pk), DENY, actor)

    def test_archived_and_infected_documents_are_not_served(self):
        self.w.doc.status = "archived"
        self.w.doc.save()
        pk = self.w.doc.pk
        # archived: author (hr) and holders of view_all_documents only; admin has it too
        self.check("documents:download", {"emp": DENY, "stranger": DENY, "head": DENY, "content": DENY, "hr": OK, "admin": OK}, pk=pk)
        self.w.doc.status = "active"
        self.w.doc.save()
        v = self.w.doc.versions.get()
        v.scan_status = "infected"
        v.save()
        self.check("documents:download", {"emp": GONE, "hr": GONE, "admin": GONE, "superuser": GONE}, pk=pk)

    def test_documents_editing_rights(self):
        pk = self.w.doc.pk
        self.check("documents:edit", {"emp": DENY, "stranger": DENY, "content": DENY, "head": DENY, "hr": OK, "admin": OK, "sysadmin": DENY}, pk=pk)
        self.check("documents:create", {"emp": DENY, "content": DENY, "head": OK, "hr": OK, "admin": OK, "sysadmin": DENY})

    def test_notifications_belong_to_their_owner_only(self):
        n = self.w.notification.pk
        for actor in ("stranger", "head", "hr", "admin", "content", "superuser"):
            self.assertEqual(self.status(actor, "notifications:open", "post", pk=n), GONE, actor)
            self.assertEqual(self.status(actor, "notifications:read", "post", pk=n), GONE, actor)
        self.assertEqual(self.status("sysadmin", "notifications:open", "post", pk=n), DENY)
        self.w.notification.refresh_from_db()
        self.assertIsNone(self.w.notification.read_at)
        self.assertEqual(self.status("emp", "notifications:open", "post", pk=n), 302)

    def test_user_administration(self):
        pk = self.w.users["emp"].pk
        self.check("users:detail", {"emp": DENY, "stranger": DENY, "content": DENY, "head": DENY, "hr": OK, "admin": OK, "sysadmin": DENY, "superuser": OK}, pk=pk)
        self.check("users:edit", {"hr": DENY, "admin": OK, "superuser": OK, "head": DENY}, pk=pk)
        self.check("users:create", {"hr": DENY, "admin": OK, "head": DENY, "sysadmin": DENY})
        for actor in ("hr", "head", "emp", "sysadmin"):  # HR can view users but not change them
            for action in ("deactivate", "unlock", "invite", "force_password"):
                self.assertEqual(self.status(actor, "users:action", "post", pk=pk, action=action), DENY, (actor, action))
        self.assertTrue(self.w.users["emp"].__class__.objects.get(pk=pk).is_active)

    def test_audit_log_and_reports(self):
        self.check("portal:audit", {"emp": DENY, "hr": DENY, "head": DENY, "content": DENY, "sysadmin": OK, "admin": OK, "superuser": OK})
        self.check("reports:index", {"emp": DENY, "stranger": DENY, "content": DENY, "sysadmin": DENY, "head": OK, "hr": OK, "admin": OK, "superuser": OK})
        self.check("reports:export", {"emp": DENY, "content": DENY, "sysadmin": DENY, "head": OK, "hr": OK, "admin": OK}, fmt="xlsx")

    def test_employee_directory_and_structure(self):
        card = self.w.card.pk
        self.check("employees:detail", {"anon": LOGIN, "emp": OK, "stranger": OK, "head": OK, "hr": OK, "admin": OK, "content": DENY, "sysadmin": DENY}, pk=card)
        self.check("employees:edit", {"emp": DENY, "head": DENY, "stranger": DENY, "hr": OK, "admin": OK}, pk=card)
        self.check("employees:structure", {"emp": OK, "stranger": OK, "head": OK, "hr": OK, "admin": OK, "sysadmin": DENY})
        self.check("employees:department_create", {"emp": DENY, "head": DENY, "hr": OK, "admin": OK})
        self.check("employees:position_create", {"emp": DENY, "head": DENY, "hr": OK, "admin": OK})

    def test_employee_card_field_tiers_by_viewer(self):
        card = reverse("employees:detail", args=[self.w.card.pk])
        secrets = {"personal_phone": "+998 90 555 66 77", "birth": "17.05.1990", "work_phone": "+998 71 111 22 33", "work_email": "vali@work.example.test"}
        seen = {}
        for actor in ("emp", "stranger", "head", "hr", "admin", "superuser"):
            body = self.w.client(actor).get(card).content.decode()
            seen[actor] = {k for k, v in secrets.items() if v in body}
        self.assertEqual(seen["emp"], set(secrets))  # one's own card, in full
        self.assertEqual(seen["stranger"], set())  # directory fields only
        self.assertEqual(seen["head"], {"work_phone", "work_email"})  # contacts within the branch, no private data
        for actor in ("hr", "admin", "superuser"):
            self.assertEqual(seen[actor], set(secrets), actor)
