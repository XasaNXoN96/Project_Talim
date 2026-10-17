"""Day 20 end-to-end audit: scenarios that cross module borders and were not covered by one test before.
(Single-module scenarios already have their own suites; docs/END_TO_END_AUDIT.md maps every scenario to its test.)"""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.content import workflow
from apps.content.models import News, NewsCategory, NewsReview
from apps.core.acceptance import World
from apps.notifications.models import Notification

User = get_user_model()


def login(user):
    c = Client()
    login_with_two_factor(c, user)
    return c


def nurl(name, *args):
    return reverse(f"news_admin:{name}", args=args)


ARGLESS = ["portal:dashboard", "portal:search", "portal:jobs", "portal:audit", "tasks:list", "documents:list", "employees:list", "employees:structure",
           "employees:me", "reports:index", "notifications:list", "users:list", "accounts:security", "accounts:sessions", "news_admin:list",
           "news_admin:categories", "news_admin:create", "employees:import", "documents:create"]


class EditorialRolesAcrossThePortal(TestCase):
    """The ready-made news roles hold no task/document/people permissions: no page may crash for them, and each answers as designed."""

    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.cat = NewsCategory.objects.create(name="K", slug="k")

    def test_no_page_crashes_for_the_news_roles_and_access_is_what_the_role_allows(self):
        expected_ok = {
            "news_author": {"portal:dashboard", "portal:search", "accounts:security", "accounts:sessions", "notifications:list", "news_admin:list", "news_admin:create"},
            "news_editor": {"portal:dashboard", "portal:search", "accounts:security", "accounts:sessions", "notifications:list", "news_admin:list"},
            "news_publisher": {"portal:dashboard", "portal:search", "accounts:security", "accounts:sessions", "notifications:list", "news_admin:list"},
        }
        for role, allowed in expected_ok.items():
            c = login(make_user(f"u_{role}", role=role))
            for name in ARGLESS:
                r = c.get(reverse(name), {"q": "abc"} if name == "portal:search" else {})
                self.assertLess(r.status_code, 500, (role, name))
                if name in allowed:
                    self.assertEqual(r.status_code, 200, (role, name))
                else:
                    self.assertEqual(r.status_code, 403, (role, name))      # closed to this role: a clean 403, never a crash or a silent redirect

    def test_search_for_a_news_role_shows_no_unpublished_news_and_no_foreign_data(self):
        w = World()
        News.objects.create(title="Yashirin loyiha", slug="y", body="b", status="review", author=w.users["content"], category=self.cat)
        c = login(make_user("seeker", role="news_editor"))
        page = c.get(reverse("portal:search"), {"q": "Yashirin"}).content.decode()
        self.assertIn("Hech narsa topilmadi", page)
        people = c.get(reverse("portal:search"), {"q": "Aliyev"}).content.decode()     # the query itself is echoed; the person's first name is not
        self.assertNotIn("Vali", people)
        self.assertIn("Hech narsa topilmadi", people)

    def test_the_dashboard_of_a_news_role_does_not_offer_what_it_cannot_open(self):
        page = login(make_user("dash", role="news_author")).get(reverse("portal:dashboard")).content.decode()
        for closed in (reverse("tasks:list"), reverse("documents:list"), reverse("users:list"), reverse("reports:index")):
            self.assertNotIn(f'href="{closed}"', page)


class AccountLifecycleAcrossModules(TestCase):
    def setUp(self):
        self.w = World()
        self.cat = self.w.news_category
        self.author = make_user("lifecycle_au", role="news_author")
        self.editor = make_user("lifecycle_ed", role="news_editor")

    def test_deactivating_an_author_closes_the_session_but_keeps_their_news_and_history(self):
        c = login(self.author)
        n = News.objects.create(title="Qoldi", slug="qoldi", body="b", status="draft", author=self.author, category=self.cat)
        self.assertEqual(c.post(nurl("status", n.pk, "submit")).status_code, 302)
        self.assertEqual(self.w.client("admin").post(reverse("users:action", args=[self.author.pk, "deactivate"])).status_code, 302)
        self.assertIn(c.get(nurl("list")).status_code, (302, 403))                     # the old cookie gives nothing
        self.assertIn("/accounts/login/", c.get(nurl("list"))["Location"])
        n.refresh_from_db()
        self.assertEqual((n.status, n.author_id), ("review", self.author.pk))
        self.assertEqual(n.reviews.count(), 1)
        # the item can still be decided on, and nothing is sent to the inactive author
        before = Notification.objects.filter(user=self.author).count()
        version = workflow.version_token(n)
        self.assertEqual(login(self.editor).post(nurl("status", n.pk, "request_changes"), {"version": version, "comment": "Tuzating"}).status_code, 302)
        n.refresh_from_db()
        self.assertEqual(n.status, "changes_requested")
        self.assertEqual(Notification.objects.filter(user=self.author).count(), before)

    def test_removing_a_role_takes_effect_on_the_next_request_for_pages_and_notifications(self):
        n = News.objects.create(title="Rol", slug="rol", body="b", status="review", author=self.author, category=self.cat)
        Notification.objects.create(user=self.editor, kind="news_submitted", news=n, title=n.title)
        c = login(self.editor)
        self.assertEqual(c.get(reverse("notifications:list")).status_code, 200)
        RoleAssignment.objects.get(user=self.editor).delete()
        self.assertEqual(c.get(reverse("notifications:list")).status_code, 403)
        self.assertEqual(c.get(nurl("preview", n.pk)).status_code, 403)
        note = Notification.objects.get(user=self.editor)
        self.assertEqual(c.post(reverse("notifications:open", args=[note.pk])).status_code, 403)

    def test_a_deleted_news_item_does_not_break_the_notification_page(self):
        n = News.objects.create(title="Yo‘qoladi", slug="yoqoladi", body="b", status="review", author=self.author, category=self.cat)
        Notification.objects.create(user=self.editor, kind="news_submitted", news=n, title=n.title)
        n.delete()                                    # (not offered in the portal; possible from the Django admin by a superuser)
        self.assertFalse(Notification.objects.filter(user=self.editor).exists())    # cascades with it
        self.assertEqual(login(self.editor).get(reverse("notifications:list")).status_code, 200)


class AuditAndMail(TestCase):
    def setUp(self):
        self.w = World()
        self.cat = self.w.news_category
        self.author = make_user("mail_au", role="news_author")
        self.editor = make_user("mail_ed", role="news_editor")
        self.editor.email = "editor@example.test"
        self.editor.save()

    def test_every_news_decision_shows_up_in_the_audit_page_with_its_label_and_nothing_else(self):
        n = News.objects.create(title="Auditga mos", slug="audit", body="b", status="draft", author=self.author, category=self.cat)
        au, ed, pu = login(self.author), login(self.editor), login(make_user("mail_pu", role="news_publisher"))
        au.post(nurl("status", n.pk, "submit"))
        n.refresh_from_db()
        ed.post(nurl("status", n.pk, "approve"), {"version": workflow.version_token(n), "comment": "MAXFIY-IZOH", "internal_note": "MAXFIY-QAYD"})
        pu.post(nurl("status", n.pk, "publish"))
        n.refresh_from_db()
        self.assertEqual(n.status, "published")
        page = self.w.client("admin").get(reverse("portal:audit")).content.decode()
        for label in ("Yangilik tekshiruvga yuborildi", "Yangilik ma’qullandi", "Yangilik nashr etildi"):
            self.assertIn(label, page)
        for secret in ("MAXFIY-IZOH", "MAXFIY-QAYD", "Auditga mos"):
            self.assertNotIn(secret, page)

    @override_settings(NOTIFICATION_EMAILS_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_the_optional_e_mail_copy_of_a_news_notice_carries_the_event_and_title_only(self):
        n = News.objects.create(title="Pochta sarlavhasi", slug="pochta", body="Matn-ichida-sir", status="draft", author=self.author, category=self.cat)
        au = login(self.author)
        with self.captureOnCommitCallbacks(execute=True):
            au.post(nurl("status", n.pk, "submit"))
        to_editor = [m for m in mail.outbox if "editor@example.test" in m.to]
        self.assertEqual(len(to_editor), 1)
        text = to_editor[0].subject + to_editor[0].body
        self.assertIn("Pochta sarlavhasi", text)
        self.assertNotIn("Matn-ichida-sir", text)
        self.assertNotIn("http", to_editor[0].body)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            au.post(nurl("status", n.pk, "submit"))                      # a repeated click: no second mail
        self.assertEqual(mail.outbox, [])


class UpgradeFromThePreviousSchema(TransactionTestCase):
    """A database that already holds data in the schema BEFORE days 18-19 is upgraded: data stays, access is kept, roles are intact."""

    OLD = [("content", "0001_initial"), ("audit", "0010_alter_auditlog_action"), ("notifications", "0001_initial")]

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_old_data_survives_the_upgrade_and_task_viewers_keep_their_notifications(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.OLD)
        old = MigrationExecutor(connection).loader.project_state(self.OLD).apps
        Group_, Perm, UserM = old.get_model("auth", "Group"), old.get_model("auth", "Permission"), old.get_model("accounts", "User")
        Task_ = old.get_model("tasks", "Task")
        task_perm = Perm.objects.get(content_type__app_label="tasks", codename="view_task")
        group = Group_.objects.create(name="legacy-staff")
        group.permissions.add(task_perm)
        user = UserM.objects.create(username="legacy", email="legacy@example.test", password="x")
        user.groups.add(group)
        News_, Notif = old.get_model("content", "News"), old.get_model("notifications", "Notification")
        news = News_.objects.create(title="Eski yangilik", slug="eski", body="b", status="review")
        task = Task_.objects.create(title="Eski topshiriq", description="d", created_by=user, due_date=datetime.date(2026, 1, 1))
        Notif.objects.create(user=user, kind="task_assigned", title=task.title, task=task)
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        self.assertEqual(News.objects.get(pk=news.pk).status, "review")
        self.assertEqual(Notification.objects.get(user_id=user.pk).title, "Eski topshiriq")
        self.assertEqual(NewsReview.objects.count(), 0)
        group = Group.objects.get(name="legacy-staff")
        self.assertTrue(group.permissions.filter(codename="view_notification").exists())      # access to the notifications page is kept
        self.assertTrue(User.objects.get(pk=user.pk).groups.filter(name="legacy-staff").exists())
        # the roles are then (re)seeded: existing assignments are untouched and the legacy group is not deleted
        call_command("seed_roles", verbosity=0)
        self.assertTrue(Group.objects.filter(name="legacy-staff").exists())
        self.assertTrue(User.objects.get(pk=user.pk).groups.filter(name="legacy-staff").exists())
        self.assertTrue(Group.objects.get(name="news_editor").permissions.filter(codename="review_news").exists())
        self.assertIsNotNone(Permission.objects.get(codename="approve_own_news"))


class DjangoAdminDoesNotBypassTheNewsWorkflow(TestCase):
    """Found in the audit: the Django admin (superusers only) let anyone set status=published on a draft, with no approval, no history and no audit entry."""

    def setUp(self):
        self.w = World()
        self.su = self.w.client("superuser")
        self.news = News.objects.create(title="Admin sinovi", slug="admin-sinovi", body="Matn", status="draft", author=self.w.users["content"], category=self.w.news_category)

    def post_change(self, **over):
        data = {"title": self.news.title, "slug": self.news.slug, "excerpt": "", "body": "Matn", "category": self.w.news_category.pk, "status": "published",
                "publish_at_0": "2026-01-01", "publish_at_1": "10:00:00", "author": self.w.users["content"].pk, **over}
        return self.su.post(reverse("admin:content_news_change", args=[self.news.pk]), data)

    def test_status_publication_date_and_author_cannot_be_set_through_the_admin(self):
        self.post_change()
        self.news.refresh_from_db()
        self.assertEqual(self.news.status, "draft")                       # still a draft: only the workflow changes status
        self.assertIsNone(self.news.publish_at)
        self.assertEqual(Client().get(reverse("content:news_detail", args=[self.news.slug])).status_code, 404)

    def test_the_admin_cannot_delete_news_and_with_it_the_approval_history(self):
        NewsReview.objects.create(news=self.news, action="submit", from_status="draft", to_status="review")
        r = self.su.post(reverse("admin:content_news_delete", args=[self.news.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(News.objects.filter(pk=self.news.pk).exists())
        self.assertEqual(NewsReview.objects.count(), 1)

    def test_the_review_history_is_not_editable_in_the_admin(self):
        from django.contrib import admin as dj_admin
        self.assertNotIn(NewsReview, dj_admin.site._registry)


class SeedRolesIsNotSilentAboutWhatItRemoves(TestCase):
    """Found in the audit: `seed_roles` resets each role to the project's definition. A permission someone had added to a role group by hand
    (for example approve_own_news) was removed without a word at the next deployment. The behaviour stays (roles are defined in code);
    the command now says exactly what it removed, so the operator notices and grants such exceptions per user instead."""

    def test_extra_permissions_on_a_role_group_are_reported_by_name_when_they_are_removed(self):
        from io import StringIO
        call_command("seed_roles", verbosity=0)
        group = Group.objects.get(name="content_manager")
        extra = Permission.objects.get(content_type__app_label="content", codename="approve_own_news")
        group.permissions.add(extra)
        out, err = StringIO(), StringIO()
        call_command("seed_roles", verbosity=0, stdout=out, stderr=err)
        self.assertNotIn(extra, group.permissions.all())                        # roles are still defined in code
        self.assertIn("content_manager", err.getvalue())
        self.assertIn("content.approve_own_news", err.getvalue())
        self.assertIn("per user", err.getvalue())

    def test_a_clean_run_reports_nothing_and_user_level_grants_survive(self):
        from io import StringIO
        call_command("seed_roles", verbosity=0)
        user = make_user("granted", role="content_manager")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="content", codename="approve_own_news"))
        err = StringIO()
        call_command("seed_roles", verbosity=0, stderr=err)
        self.assertEqual(err.getvalue(), "")
        self.assertTrue(User.objects.get(pk=user.pk).user_permissions.filter(codename="approve_own_news").exists())
