"""Day 19: ready-made editorial roles, notification permission independent of tasks, private editorial notes, old history."""
import importlib
import threading

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.access.roles import ROLE_HINTS, ROLE_PERMISSIONS, ROLE_SCOPE, RoleCode
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.core.acceptance import World
from apps.notifications.models import Notification

from . import workflow
from .models import News, NewsCategory, NewsReview


def url(name, *args):
    return reverse(f"news_admin:{name}", args=args)


def login(user):
    c = Client()
    login_with_two_factor(c, user)
    return c


def perms_of(group_name):
    return {f"{p.content_type.app_label}.{p.codename}" for p in Group.objects.get(name=group_name).permissions.select_related("content_type")}


class RoleMatrix(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def test_the_three_editorial_roles_have_exactly_these_permissions(self):
        self.assertEqual(perms_of("news_author"), {"content.view_news", "content.add_news", "content.change_news", "notifications.view_notification"})
        self.assertEqual(perms_of("news_editor"), {"content.view_news", "content.review_news", "notifications.view_notification"})
        self.assertEqual(perms_of("news_publisher"), {"content.view_news", "content.publish_news", "notifications.view_notification"})

    def test_no_editorial_role_can_do_two_jobs_that_must_stay_apart(self):
        a, e, p = perms_of("news_author"), perms_of("news_editor"), perms_of("news_publisher")
        self.assertFalse({"content.review_news", "content.publish_news"} & a)       # an author neither approves nor publishes
        self.assertFalse({"content.add_news", "content.change_news", "content.publish_news"} & e)   # an editor neither writes nor publishes
        self.assertFalse({"content.add_news", "content.change_news", "content.review_news"} & p)    # a publisher neither writes nor approves
        for name in ("news_author", "news_editor", "news_publisher"):
            self.assertFalse({p for p in perms_of(name) if p.startswith(("tasks.", "documents.", "organization.", "accounts.", "audit.", "reports."))}, name)

    def test_nobody_holds_the_approve_own_exception_by_default(self):
        for code in RoleCode.values:
            self.assertNotIn("content.approve_own_news", perms_of(code), code)

    def test_existing_roles_keep_their_news_rights_and_gain_only_the_notification_permission(self):
        cm, ad = perms_of("content_manager"), perms_of("admin")
        for perms in (cm, ad):
            self.assertTrue({"content.view_news", "content.add_news", "content.change_news", "content.review_news", "content.publish_news"} <= perms)
        # exactly the old sets plus the one permission that preserves access to the notifications page
        for code in ("employee", "department_head", "content_manager", "hr", "admin"):
            self.assertIn("tasks.view_task", perms_of(code))
            self.assertIn("notifications.view_notification", perms_of(code), code)
        self.assertNotIn("notifications.view_notification", perms_of("sysadmin"))     # never had tasks.view_task either

    def test_seeding_is_idempotent_deletes_nothing_and_does_not_touch_user_assignments(self):
        user = make_user("keeper", role="news_editor")
        before = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        call_command("seed_roles", verbosity=0)
        call_command("seed_roles", verbosity=0)
        after = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        self.assertEqual(before, after)
        self.assertEqual(set(RoleCode.values), {g for g in after if g in RoleCode.values})
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["news_editor"])

    def test_every_role_has_a_scope_and_the_new_roles_a_translated_hint(self):
        for code in RoleCode.values:
            self.assertIn(code, ROLE_PERMISSIONS)
            self.assertIn(code, ROLE_SCOPE)
        for code in ("news_author", "news_editor", "news_publisher"):
            self.assertTrue(str(ROLE_HINTS[code]))
            self.assertTrue(str(RoleCode(code).label))

    def test_the_role_screen_offers_and_explains_the_new_roles_in_every_language(self):
        w = World()
        target = w.users["emp"]
        for code, label, hint in (("uz", "Yangilik muallifi", "o‘z qoralamalarini"), ("ru", "Автор новостей", "собственные черновики"), ("en", "News author", "own drafts")):
            c = w.client("admin")
            c.cookies["django_language"] = code
            page = c.get(reverse("users:detail", args=[target.pk]))
            self.assertContains(page, f'value="news_author">{label}')
            self.assertContains(page, hint)
        r = w.client("admin").post(reverse("users:role_add", args=[target.pk]), {"role": "news_editor"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(target.groups.filter(name="news_editor").exists())


class RoleFlows(TestCase):
    """The whole cycle with people who hold ONLY the ready-made roles."""

    def setUp(self):
        self.w = World()
        self.cat = self.w.news_category
        self.author, self.editor, self.editor2 = make_user("au", role="news_author"), make_user("ed", role="news_editor"), make_user("ed2", role="news_editor")
        self.publisher = make_user("pu", role="news_publisher")
        self.au, self.ed, self.ed2, self.pu = (login(u) for u in (self.author, self.editor, self.editor2, self.publisher))
        self.body = {"title": "Rol yangiligi", "excerpt": "", "body": "Matn", "category": self.cat.pk}

    def step(self, client, n, step, **data):
        n.refresh_from_db()
        if step in ("approve", "request_changes"):
            data.setdefault("version", workflow.version_token(n))
        r = client.post(url("status", n.pk, step), data)
        n.refresh_from_db()
        return r

    def test_author_editor_publisher_cycle_with_the_ready_made_roles(self):
        self.assertEqual(self.au.post(url("create"), self.body).status_code, 302)
        n = News.objects.get(title="Rol yangiligi")
        self.assertEqual((n.status, n.author), ("draft", self.author))
        self.step(self.pu, n, "publish")                      # a publisher cannot publish a draft: not even visible
        self.assertEqual(n.status, "draft")
        self.step(self.au, n, "submit")
        self.assertEqual(n.status, "review")
        self.step(self.ed, n, "request_changes", comment="Aniqlashtiring")
        self.assertEqual(n.status, "changes_requested")
        self.step(self.au, n, "submit")
        self.step(self.ed2, n, "approve")
        self.assertEqual(n.status, "approved")
        self.step(self.ed, n, "publish")
        self.step(self.au, n, "publish")
        self.assertEqual(n.status, "approved")                # neither the editor nor the author can publish
        self.step(self.pu, n, "publish")
        self.assertEqual(n.status, "published")
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 200)
        self.step(self.pu, n, "unpublish")
        self.assertEqual(n.status, "draft")
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)

    def test_what_each_role_cannot_do(self):
        n = News.objects.create(title="T", slug="t", body="b", status="review", author=self.author, category=self.cat)
        for client, steps in ((self.au, ("approve", "request_changes", "publish", "archive")), (self.ed, ("publish", "archive", "submit", "withdraw")),
                              (self.pu, ("approve", "request_changes", "submit"))):
            for step in steps:
                self.step(client, n, step, comment="x")
                self.assertEqual(n.status, "review", step)
        self.assertEqual(self.ed.post(url("create"), self.body).status_code, 403)
        self.assertEqual(self.pu.post(url("create"), self.body).status_code, 403)
        self.assertEqual(self.ed.post(url("edit", n.pk), self.body).status_code, 403)

    def test_an_author_never_approves_their_own_item_even_with_every_other_right(self):
        both = make_user("both", role="news_author")
        both.groups.add(Group.objects.get(name="news_editor"))
        c = login(type(both).objects.get(pk=both.pk))
        n = News.objects.create(title="Own", slug="own", body="b", status="review", author=both, category=self.cat)
        self.step(c, n, "approve")
        self.assertEqual(n.status, "review")
        self.step(c, n, "request_changes", comment="x")
        self.assertEqual(n.status, "review")

    def test_visibility_follows_the_role(self):
        mine = News.objects.create(title="Mening", slug="m", body="b", status="draft", author=self.author, category=self.cat)
        other_draft = News.objects.create(title="Boshqaning qoralamasi", slug="od", body="b", status="draft", author=self.w.users["content"], category=self.cat)
        in_review = News.objects.create(title="Tekshiruvdagi", slug="ir", body="b", status="review", author=self.w.users["content"], category=self.cat)
        approved = News.objects.create(title="Tasdiqlangan-xabar", slug="ap", body="b", status="approved", author=self.w.users["content"], category=self.cat)
        listing = lambda c: c.get(url("list")).content.decode()  # noqa: E731
        page = listing(self.au)
        self.assertIn("Mening", page)
        for hidden in ("Boshqaning qoralamasi", "Tekshiruvdagi", "Tasdiqlangan-xabar"):
            self.assertNotIn(hidden, page)
        page = listing(self.ed)
        self.assertIn("Tekshiruvdagi", page)
        self.assertIn("Tasdiqlangan-xabar", page)
        self.assertNotIn("Boshqaning qoralamasi", page)
        page = listing(self.pu)
        self.assertIn("Tasdiqlangan-xabar", page)
        self.assertNotIn("Tekshiruvdagi", page)
        self.assertNotIn("Boshqaning qoralamasi", page)
        for client, n, code in ((self.au, other_draft, 404), (self.au, in_review, 404), (self.ed, other_draft, 404), (self.pu, in_review, 404), (self.pu, mine, 404),
                                (self.ed, in_review, 200), (self.pu, approved, 200), (self.au, mine, 200)):
            self.assertEqual(client.get(url("preview", n.pk)).status_code, code, (n.title, code))
        # and the manager sees everything
        self.assertIn("Boshqaning qoralamasi", listing(self.w.client("content")))

    def test_two_editors_with_the_ready_made_role_cannot_both_decide(self):
        n = News.objects.create(title="Race", slug="race", body="b", status="review", author=self.author, category=self.cat)
        version = workflow.version_token(n)
        self.step(self.ed, n, "approve", version=version)
        self.step(self.ed2, n, "request_changes", version=version, comment="Yo‘q")
        self.assertEqual(n.status, "approved")
        self.assertEqual(n.reviews.count(), 1)

    def test_direct_publication_of_a_draft_is_refused_for_every_role_including_a_superuser(self):
        n = News.objects.create(title="Draft", slug="dr", body="b", status="draft", author=self.author, category=self.cat)
        for client in (self.pu, self.w.client("content"), self.w.client("admin"), self.w.client("superuser")):
            self.step(client, n, "publish")
            self.assertEqual(n.status, "draft")
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)

    def test_a_superuser_cannot_approve_their_own_item_by_being_a_superuser(self):
        su = self.w.users["superuser"]
        n = News.objects.create(title="Su", slug="su", body="b", status="review", author=su, category=self.cat)
        self.step(self.w.client("superuser"), n, "approve")
        self.assertEqual(n.status, "review")


class NotificationAccess(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.cat = NewsCategory.objects.create(name="K", slug="k")
        self.editor = make_user("ed", role="news_editor")          # holds NO task permission
        self.employee = make_user("empl", role="employee")
        self.no_notify = make_user("nn")                           # has tasks.view_task but not the notification permission
        self.no_notify.user_permissions.add(Permission.objects.get(content_type__app_label="tasks", codename="view_task"))
        self.no_notify = type(self.no_notify).objects.get(pk=self.no_notify.pk)
        self.author = make_user("au", role="news_author")
        self.news = News.objects.create(title="Xabar", slug="xabar", body="b", status="review", author=self.author, category=self.cat)
        self.mine = Notification.objects.create(user=self.editor, kind="news_submitted", news=self.news, title=self.news.title)
        self.theirs = Notification.objects.create(user=self.employee, kind="news_submitted", news=self.news, title=self.news.title)

    def test_notifications_do_not_depend_on_tasks_in_either_direction(self):
        self.assertFalse(self.editor.has_perm("tasks.view_task"))
        self.assertEqual(login(self.editor).get(reverse("notifications:list")).status_code, 200)
        self.assertEqual(login(self.no_notify).get(reverse("notifications:list")).status_code, 403)
        self.assertEqual(login(self.no_notify).post(reverse("notifications:read_all")).status_code, 403)
        self.assertEqual(login(self.no_notify).post(reverse("notifications:read", args=[self.mine.pk])).status_code, 403)

    def test_anonymous_goes_to_login_and_only_post_changes_anything(self):
        for name, args in (("list", ()), ("read_all", ()), ("read", (self.mine.pk,)), ("open", (self.mine.pk,))):
            r = Client().get(reverse(f"notifications:{name}", args=args))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])
        c = login(self.editor)
        for name in ("read_all",):
            self.assertEqual(c.get(reverse(f"notifications:{name}")).status_code, 405)
        for name in ("read", "open"):
            self.assertEqual(c.get(reverse(f"notifications:{name}", args=[self.mine.pk])).status_code, 405)
        self.mine.refresh_from_db()
        self.assertIsNone(self.mine.read_at)

    def test_somebody_elses_notification_is_invisible_and_cannot_be_changed(self):
        c = login(self.editor)
        page = c.get(reverse("notifications:list")).content.decode()
        self.assertEqual(page.count('action="/portal/notifications/'), page.count(str(self.mine.pk)) + 1)   # only own rows (+ read-all form)
        self.assertNotIn(str(self.theirs.pk), page)
        for name in ("read", "open"):
            self.assertEqual(c.post(reverse(f"notifications:{name}", args=[self.theirs.pk])).status_code, 404)
        c.post(reverse("notifications:read_all"))
        self.theirs.refresh_from_db()
        self.mine.refresh_from_db()
        self.assertIsNone(self.theirs.read_at)
        self.assertIsNotNone(self.mine.read_at)

    def test_a_news_notification_opens_the_item_while_it_is_visible_and_stops_when_it_is_not(self):
        c = login(self.editor)
        r = c.post(reverse("notifications:open", args=[self.mine.pk]))
        self.assertRedirects(r, url("preview", self.news.pk), fetch_redirect_response=False)
        self.news.status = "draft"                          # withdrawn: an editor may not see someone's draft
        self.news.save()
        r = c.post(reverse("notifications:open", args=[self.mine.pk]), follow=True)
        self.assertRedirects(r, reverse("notifications:list"))
        page = c.get(reverse("notifications:list")).content.decode()
        self.assertNotIn(url("preview", self.news.pk), page)
        self.assertNotIn("Xabar", page.split('<main')[1])                  # the title of an item the person may not see is not shown

    def test_the_bell_follows_the_notification_permission_not_the_task_permission(self):
        self.assertContains(login(self.editor).get(reverse("portal:dashboard")), reverse("notifications:list"))
        self.assertNotContains(login(self.no_notify).get(reverse("portal:dashboard")), reverse("notifications:list"))

    def test_task_notifications_still_work_for_task_people(self):
        w = World()
        n = Notification.objects.create(user=w.users["emp"], kind="task_assigned", task=w.task, title=w.task.title)
        c = w.client("emp")
        self.assertContains(c.get(reverse("notifications:list")), w.task.title)
        self.assertEqual(c.post(reverse("notifications:open", args=[n.pk])).status_code, 302)

    def test_the_data_migration_keeps_access_for_everyone_who_had_tasks_view_task(self):
        migration = importlib.import_module("apps.notifications.migrations.0003_grant_view_notification_to_task_viewers")
        task_perm = Permission.objects.get(content_type__app_label="tasks", codename="view_task")
        notify_perm = Permission.objects.get(content_type__app_label="notifications", codename="view_notification")
        old_group, plain_group = Group.objects.create(name="old-with-tasks"), Group.objects.create(name="old-without")
        old_group.permissions.add(task_perm)
        direct = make_user("direct")
        direct.user_permissions.add(task_perm)
        nothing = make_user("nothing")
        migration.grant(django_apps, None)
        migration.grant(django_apps, None)                    # idempotent
        self.assertIn(notify_perm, old_group.permissions.all())
        self.assertNotIn(notify_perm, plain_group.permissions.all())
        self.assertIn(notify_perm, direct.user_permissions.all())
        self.assertFalse(nothing.user_permissions.exists())


class PrivateNotes(TestCase):
    def setUp(self):
        self.w = World()
        self.cat = self.w.news_category
        self.author = make_user("au", role="news_author")
        self.editor, self.editor2 = make_user("ed", role="news_editor"), make_user("ed2", role="news_editor")
        self.publisher = make_user("pu", role="news_publisher")
        self.au, self.ed, self.pu = login(self.author), login(self.editor), login(self.publisher)
        self.n = News.objects.create(title="Qayd", slug="qayd", body="b", status="review", author=self.author, category=self.cat)
        self.NOTE, self.COMMENT = "MAXFIY-qayd-uchun-tahrir", "Muallifga-ko‘rinadigan-izoh"

    def decide(self, client, step="request_changes", **extra):
        self.n.refresh_from_db()
        r = client.post(url("status", self.n.pk, step), {"version": workflow.version_token(self.n), "comment": self.COMMENT, "internal_note": self.NOTE, **extra})
        self.n.refresh_from_db()
        return r

    def test_the_author_sees_the_comment_meant_for_them_but_never_the_internal_note(self):
        self.decide(self.ed)
        self.assertEqual(self.n.status, "changes_requested")
        page = self.au.get(url("preview", self.n.pk)).content.decode()
        self.assertIn(self.COMMENT, page)
        self.assertNotIn(self.NOTE, page)
        self.assertNotIn("Ichki qayd", page)
        row = self.n.reviews.get()
        self.assertEqual((row.comment, row.internal_note), (self.COMMENT, self.NOTE))      # stored, just not shown
        self.assertEqual(workflow.history_for(self.n, self.author)[0].internal_note, "")   # blanked before it reaches any template

    def test_editorial_staff_see_the_note_but_the_item_author_who_is_also_staff_does_not(self):
        self.decide(self.ed)
        self.n.status = "approved"
        self.n.save()
        self.assertIn(self.NOTE, login(self.editor2).get(url("preview", self.n.pk)).content.decode())
        self.assertIn(self.NOTE, self.pu.get(url("preview", self.n.pk)).content.decode())        # a publisher is staff and sees approved items
        manager = self.w.users["content"]
        self.n.author = manager
        self.n.save()
        self.assertNotIn(self.NOTE, self.w.client("content").get(url("preview", self.n.pk)).content.decode())   # the manager wrote this one
        self.assertIn(self.NOTE, self.w.client("admin").get(url("preview", self.n.pk)).content.decode())

    def test_people_who_merely_hold_view_news_get_no_notes(self):
        self.decide(self.ed)
        viewer = make_user("viewer")
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="content", codename="view_news"))
        viewer = type(viewer).objects.get(pk=viewer.pk)
        self.assertFalse(workflow.can_see_internal(viewer, self.n))
        r = login(viewer).get(url("preview", self.n.pk))
        self.assertEqual(r.status_code, 404)                 # not even the item
        self.assertNotIn(self.NOTE, login(viewer).get(url("list")).content.decode())

    def test_the_note_never_reaches_notifications_audit_or_logs(self):
        with self.assertNoLogs(level="INFO"):
            self.decide(self.ed)
        for n in Notification.objects.all():
            self.assertNotIn(self.NOTE, n.title)
            self.assertNotIn(self.COMMENT, n.title)
        audit = AuditLog.objects.get(action="news_changes_requested")
        self.assertEqual(audit.meta, {"from": "review", "to": "changes_requested", "comment_length": len(self.COMMENT), "note_length": len(self.NOTE)})
        self.assertNotIn(self.NOTE, str(list(AuditLog.objects.values_list("meta", flat=True))))
        for c in (self.au, self.ed):
            self.assertNotIn(self.NOTE, c.get(reverse("notifications:list")).content.decode())
            self.assertNotIn(self.NOTE, c.get(url("list")).content.decode())

    def test_the_note_is_escaped_length_limited_and_only_for_decisions(self):
        self.decide(self.ed, internal_note="<script>alert(1)</script>")
        page = login(self.editor2).get(url("preview", self.n.pk)).content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        n2 = News.objects.create(title="Q2", slug="q2", body="b", status="review", author=self.author, category=self.cat)
        self.ed.post(url("status", n2.pk, "approve"), {"version": workflow.version_token(n2), "internal_note": "x" * 2001})
        n2.refresh_from_db()
        self.assertEqual(n2.status, "review")
        n3 = News.objects.create(title="Q3", slug="q3", body="b", status="draft", author=self.author, category=self.cat)
        self.au.post(url("status", n3.pk, "submit"), {"internal_note": "ignored", "comment": "ignored too"})
        self.assertEqual(n3.reviews.get().internal_note, "")

    def test_the_confirmation_page_explains_who_sees_what(self):
        n = News.objects.get(pk=self.n.pk)
        for code, comment, note in (("uz", "Muallif uchun izoh", "Faqat tahririyat xodimlari"), ("ru", "Комментарий для автора", "Видна только сотрудникам редакции"),
                                    ("en", "Comment for the author", "Visible to editorial staff only")):
            c = login(self.editor)
            c.cookies["django_language"] = code
            page = c.get(url("status", n.pk, "request_changes"))
            self.assertContains(page, comment)
            self.assertContains(page, note)
            self.assertContains(page, 'name="internal_note"')
        self.assertNotContains(self.ed.get(url("status", n.pk, "approve")), "MAXFIY")

    def test_an_old_comment_stays_an_author_facing_comment(self):
        NewsReview.objects.create(news=self.n, actor=self.editor, action="request_changes", from_status="review", to_status="changes_requested", comment="Eski izoh")
        self.n.status = "changes_requested"
        self.n.save()
        self.assertEqual(NewsReview.objects.get().internal_note, "")
        self.assertIn("Eski izoh", self.au.get(url("preview", self.n.pk)).content.decode())


class Migrations(TransactionTestCase):
    """History written before the internal-note column existed must survive the migration unchanged."""

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_old_history_rows_survive_with_their_comment_and_an_empty_internal_note(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("content", "0002_alter_news_options_alter_news_status_newsreview")])
        old = executor.loader.project_state([("content", "0002_alter_news_options_alter_news_status_newsreview")]).apps
        OldNews, OldReview = old.get_model("content", "News"), old.get_model("content", "NewsReview")
        news = OldNews.objects.create(title="Eski", slug="eski", body="b", status="changes_requested")
        OldReview.objects.create(news=news, action="request_changes", from_status="review", to_status="changes_requested", comment="Eski izoh")
        executor = MigrationExecutor(connection)
        executor.migrate([("content", "0003_newsreview_internal_note")])
        row = NewsReview.objects.get(news_id=news.pk)
        self.assertEqual((row.comment, row.internal_note, row.action), ("Eski izoh", "", "request_changes"))
        call_command("migrate", verbosity=0)  # the current News model has columns added later
        self.assertEqual(workflow.history_for(News.objects.get(pk=news.pk), make_user("anyone"))[0].comment, "Eski izoh")


class RaceWithReadyMadeRoles(TransactionTestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.author = make_user("au", role="news_author")
        self.a, self.b = make_user("e1", role="news_editor"), make_user("e2", role="news_editor")
        self.news = News.objects.create(title="T", slug="t", body="b", status="review", author=self.author)

    def test_exactly_one_of_two_simultaneous_editor_decisions_wins(self):
        version = workflow.version_token(self.news)
        barrier, results = threading.Barrier(2), []

        def run(user, step):
            try:
                barrier.wait(timeout=10)
                workflow.perform(step, self.news.pk, user, comment="izoh", version=version, note="ichki")
                results.append("ok")
            except workflow.WorkflowError:
                results.append("refused")
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(self.a, "approve")), threading.Thread(target=run, args=(self.b, "request_changes"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(sorted(results), ["ok", "refused"])
        self.assertEqual(NewsReview.objects.filter(news=self.news).count(), 1)
