"""News approval workflow: transitions, rights, bypass attempts, concurrency, history, notifications, public visibility."""
import threading
from datetime import timedelta

from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.core.acceptance import World
from apps.notifications.models import Notification

from . import workflow
from .models import News, NewsReview

ALL_STEPS = list(workflow.STEPS)
STATUSES = [s for s, _label in News.Status.choices]


def url(name, *args):
    return reverse(f"news_admin:{name}", args=args)


def give(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="content", codename=codename))
    return type(user).objects.get(pk=user.pk)  # drop the permission cache


def login(user):
    c = Client()
    login_with_two_factor(c, user)
    return c


class Base(TestCase):
    def setUp(self):
        self.w = World()
        self.author = self.w.users["content"]            # content_manager: holds review + publish, but NOT approve_own_news
        self.admin = self.w.users["admin"]
        self.cm = self.w.client("content")
        self.ad = self.w.client("admin")
        self.reviewer2 = make_user("cm2", role="content_manager")
        self.rv2 = login(self.reviewer2)
        self.writer = give(make_user("writer"), "view_news", "add_news", "change_news")   # may write and submit; nothing else
        self.wr = login(self.writer)
        self.editor = give(make_user("editor"), "view_news", "review_news")                # may review; cannot write or publish
        self.ed = login(self.editor)
        self.publisher = give(make_user("publisher"), "view_news", "publish_news")
        self.pub = login(self.publisher)

    def news(self, status="draft", author=None, **kw):
        n = News.objects.create(title=kw.pop("title", "Yangilik"), slug=kw.pop("slug", f"n-{News.objects.count()}-{status}"), body="Matn", status=status,
                                author=author if author is not None else self.author, category=self.w.news_category, **kw)
        return n

    def do(self, client, news, step, comment="", version="auto"):
        data = {"comment": comment}
        if version == "auto":
            news.refresh_from_db()
            version = workflow.version_token(news)
        if version is not None:
            data["version"] = version
        r = client.post(url("status", news.pk, step), data)
        news.refresh_from_db()
        return r

    def status_of(self, news):
        news.refresh_from_db()
        return news.status


class HappyPath(Base):
    def test_full_cycle_with_history_comments_audit_and_notifications(self):
        n = self.news()
        self.assertEqual(self.do(self.cm, n, "submit").status_code, 302)
        self.assertEqual(n.status, "review")
        # editors are told; the author (the actor) is not
        got = set(Notification.objects.filter(kind="news_submitted", news=n).values_list("user__username", flat=True))
        self.assertIn("boss", got)
        self.assertIn("cm2", got)
        self.assertIn("editor", got)
        self.assertNotIn("content", got)
        self.assertNotIn("writer", got)
        # the editor sends it back with a comment
        self.do(self.ad, n, "request_changes", comment="Sarlavhani aniqlashtiring")
        self.assertEqual(n.status, "changes_requested")
        note = Notification.objects.get(user=self.author, kind="news_changes_requested")
        self.assertEqual((note.news_id, note.title), (n.pk, n.title))
        self.assertNotIn("aniqlashtiring", note.title)           # the comment is not copied into the notification
        self.assertContains(self.cm.get(url("preview", n.pk)), "Sarlavhani aniqlashtiring")   # the author sees it on the item
        # the author corrects and resubmits; a different editor approves
        self.assertEqual(self.cm.post(url("edit", n.pk), {"title": "Tuzatilgan", "excerpt": "", "body": "Yangi matn", "category": self.w.news_category.pk}).status_code, 302)
        self.assertEqual(self.status_of(n), "changes_requested")
        self.do(self.cm, n, "submit")
        self.do(self.rv2, n, "approve", comment="Yaxshi")
        self.assertEqual(n.status, "approved")
        self.assertTrue(Notification.objects.filter(user=self.author, kind="news_approved", news=n).exists())
        # not public until it is published
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
        self.do(self.cm, n, "publish")
        self.assertEqual(n.status, "published")
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 200)
        # history: who, what, when, comment
        rows = list(n.reviews.values_list("action", "actor__username", "from_status", "to_status", "comment"))
        self.assertEqual(rows, [("submit", "content", "draft", "review", ""), ("request_changes", "boss", "review", "changes_requested", "Sarlavhani aniqlashtiring"),
                                ("submit", "content", "changes_requested", "review", ""), ("approve", "cm2", "review", "approved", "Yaxshi"),
                                ("publish", "content", "approved", "published", "")])
        self.assertTrue(all(r.created_at for r in n.reviews.all()))
        actions = list(AuditLog.objects.filter(object_id=str(n.pk)).order_by("at").values_list("action", flat=True))
        self.assertEqual([a for a in actions if a != "news_updated"], ["news_submitted", "news_changes_requested", "news_submitted", "news_approved", "news_published"])
        # the audit log carries the decision but not the comment text
        rec = AuditLog.objects.get(action="news_changes_requested")
        self.assertEqual(rec.meta, {"from": "review", "to": "changes_requested", "comment_length": len("Sarlavhani aniqlashtiring")})
        self.assertEqual(AuditLog.objects.get(action="news_changes_requested").user, self.admin)

    def test_notification_opens_the_item_for_someone_allowed_and_not_for_others(self):
        n = self.news()
        self.do(self.cm, n, "submit")
        note = Notification.objects.get(user=self.admin, kind="news_submitted")
        page = self.ad.get(reverse("notifications:list"))
        self.assertContains(page, n.title)
        r = self.ad.post(reverse("notifications:open", args=[note.pk]))
        self.assertRedirects(r, url("preview", n.pk), fetch_redirect_response=False)
        # someone else's notification is a 404, never a leak
        self.assertEqual(self.rv2.post(reverse("notifications:open", args=[note.pk])).status_code, 404)

    def test_inactive_reviewers_and_the_actor_are_not_notified(self):
        self.reviewer2.is_active = False
        self.reviewer2.save()
        n = self.news()
        self.do(self.cm, n, "submit")
        self.assertFalse(Notification.objects.filter(user=self.reviewer2).exists())
        self.assertFalse(Notification.objects.filter(user=self.author).exists())

    def test_the_author_is_not_told_to_review_their_own_item_but_an_explicit_grant_changes_that(self):
        give(self.author, "approve_own_news")
        n = self.news()
        self.do(self.cm, n, "submit")
        self.assertFalse(Notification.objects.filter(user=self.author).exists())   # the actor is never notified of their own action


class Transitions(Base):
    def test_every_status_times_every_step_changes_state_only_where_allowed(self):
        for status in STATUSES:
            for step in ALL_STEPS:
                n = self.news(status=status, publish_at=timezone.now() if status == "published" else None, slug=f"s-{status}-{step}")
                reviewer = self.ad                                   # holds every permission and is not the author
                before = NewsReview.objects.count()
                self.do(reviewer, n, step, comment="izoh")
                if status in workflow.STEPS[step].sources:
                    self.assertEqual(n.status, workflow.STEPS[step].target, (status, step))
                    self.assertEqual(NewsReview.objects.count(), before + 1, (status, step))
                else:
                    self.assertEqual(n.status, status, (status, step))
                    self.assertEqual(NewsReview.objects.count(), before, (status, step))

    def test_publish_needs_approval_a_draft_or_a_review_item_cannot_be_published_directly(self):
        for status in ("draft", "review", "changes_requested", "archived"):
            n = self.news(status=status, slug=f"p-{status}")
            self.do(self.ad, n, "publish")
            self.assertEqual(n.status, status)
            self.assertIsNone(n.publish_at)
            self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)

    def test_unknown_action_is_404_and_get_never_changes_anything(self):
        n = self.news(status="review")
        self.assertEqual(self.ad.post(url("status", n.pk, "teleport")).status_code, 404)
        for step in ALL_STEPS:
            self.ad.get(url("status", n.pk, step))
        self.assertEqual(self.status_of(n), "review")
        self.assertEqual(NewsReview.objects.count(), 0)

    def test_a_double_submit_creates_one_history_row_and_one_set_of_notifications(self):
        n = self.news()
        self.do(self.cm, n, "submit")
        count = Notification.objects.count()
        r = self.cm.post(url("status", n.pk, "submit"), {})   # the browser sent the form again
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.status_of(n), "review")
        self.assertEqual((n.reviews.count(), Notification.objects.count()), (1, count))
        self.assertEqual(AuditLog.objects.filter(action="news_submitted").count(), 1)

    def test_archive_and_restore_still_work_from_every_state_that_allows_them(self):
        for status in ("draft", "review", "changes_requested", "approved", "published"):
            n = self.news(status=status, publish_at=timezone.now() if status == "published" else None, slug=f"a-{status}")
            self.do(self.ad, n, "archive")
            self.assertEqual(n.status, "archived")
            self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
            self.do(self.ad, n, "restore")
            self.assertEqual(n.status, "draft")


class Rights(Base):
    def test_anonymous_goes_to_login_and_a_plain_employee_gets_403_on_every_step(self):
        n = self.news(status="review")
        for step in ALL_STEPS:
            r = Client().post(url("status", n.pk, step))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])
            self.assertEqual(self.w.client("emp").post(url("status", n.pk, step), {"version": workflow.version_token(n)}).status_code, 403, step)
            self.assertEqual(self.w.client("emp").get(url("status", n.pk, step)).status_code, 403, step)
        self.assertEqual(self.status_of(n), "review")
        self.assertEqual(self.w.client("emp").get(url("preview", n.pk)).status_code, 403)

    def test_a_writer_can_submit_but_not_approve_return_or_publish(self):
        n = self.news(author=self.writer)
        self.assertEqual(self.do(self.wr, n, "submit").status_code, 302)
        self.assertEqual(n.status, "review")
        for step in ("approve", "request_changes", "publish", "archive"):
            self.assertEqual(self.wr.post(url("status", n.pk, step), {"comment": "x", "version": workflow.version_token(n)}).status_code, 403, step)
        self.assertEqual(self.status_of(n), "review")

    def test_a_reviewer_who_cannot_publish_decides_but_does_not_publish(self):
        n = self.news(status="review")
        self.do(self.ed, n, "approve")
        self.assertEqual(n.status, "approved")
        self.assertEqual(self.ed.post(url("status", n.pk, "publish")).status_code, 403)
        self.assertEqual(self.status_of(n), "approved")

    def test_a_publisher_who_cannot_review_cannot_approve_even_by_direct_post(self):
        n = self.news(status="review")
        self.assertEqual(self.pub.post(url("status", n.pk, "approve"), {"version": workflow.version_token(n)}).status_code, 403)
        self.assertEqual(self.status_of(n), "review")

    def test_nobody_approves_or_returns_their_own_item(self):
        notes = Notification.objects.count()
        for who, client in (("content_manager", self.cm), ("superuser", self.w.client("superuser"))):
            author = self.author if who == "content_manager" else self.w.users["superuser"]
            for step in ("approve", "request_changes"):
                n = self.news(status="review", author=author, slug=f"own-{who}-{step}")
                self.do(client, n, step, comment="x")
                self.assertEqual(n.status, "review", (who, step))
                self.assertEqual(n.reviews.count(), 0)
        self.assertEqual(Notification.objects.count(), notes)

    def test_the_explicit_permission_allows_it_and_the_history_shows_who_did_it(self):
        give(self.author, "approve_own_news")
        n = self.news(status="review")
        self.do(login(self.author), n, "approve")
        self.assertEqual(n.status, "approved")
        self.assertEqual(n.reviews.get().actor, self.author)
        self.assertFalse(Permission.objects.filter(group__name__in=["content_manager", "admin", "sysadmin", "employee", "hr", "department_head"],
                                                   codename="approve_own_news").exists())   # no default role holds it

    def test_only_the_author_or_staff_may_submit_someone_elses_draft(self):
        n = self.news(author=self.author)
        self.assertEqual(self.wr.post(url("status", n.pk, "submit")).status_code, 404)   # someone else's draft is invisible to a writer
        self.assertEqual(self.status_of(n), "draft")
        self.assertEqual(self.wr.get(url("edit", n.pk)).status_code, 404)
        self.do(self.ad, n, "submit")                                                    # staff may
        self.assertEqual(n.status, "review")

    def test_csrf_is_enforced_on_every_new_step(self):
        n = self.news(status="review")
        c = self.w.client("admin", csrf=True)
        for step in ALL_STEPS:
            self.assertEqual(c.post(url("status", n.pk, step), {"version": workflow.version_token(n), "comment": "x"}).status_code, 403, step)
        self.assertEqual(self.status_of(n), "review")

    def test_only_the_news_row_named_in_the_url_is_touched(self):
        a, b = self.news(status="review", slug="a"), self.news(status="review", slug="b")
        self.do(self.ad, a, "approve")
        self.assertEqual((self.status_of(a), self.status_of(b)), ("approved", "review"))


class Decisions(Base):
    def test_returning_needs_a_comment_and_a_too_long_comment_is_refused(self):
        n = self.news(status="review")
        self.do(self.ad, n, "request_changes", comment="   ")
        self.assertEqual(n.status, "review")
        self.do(self.ad, n, "request_changes", comment="x" * 2001)
        self.assertEqual(n.status, "review")
        self.do(self.ad, n, "request_changes", comment="x" * 2000)
        self.assertEqual(n.status, "changes_requested")

    def test_a_decision_without_the_version_or_with_a_stale_one_is_refused(self):
        n = self.news(status="review")
        self.do(self.ad, n, "approve", version=None)            # crafted request without the version
        self.assertEqual(n.status, "review")
        self.do(self.ad, n, "approve", version="1")
        self.assertEqual(n.status, "review")

    def test_a_decision_on_text_that_changed_after_the_reviewer_opened_it_is_refused(self):
        n = self.news()
        self.do(self.cm, n, "submit")
        shown = workflow.version_token(News.objects.get(pk=n.pk))     # the reviewer opens the confirmation page
        self.do(self.cm, n, "withdraw")                               # the author pulls it back, edits and resubmits
        self.cm.post(url("edit", n.pk), {"title": n.title, "excerpt": "", "body": "Boshqa matn", "category": self.w.news_category.pk})
        self.do(self.cm, n, "submit")
        self.do(self.ad, n, "approve", version=shown)
        self.assertEqual(n.status, "review")                          # the old page cannot approve the new text
        self.do(self.ad, n, "approve")
        self.assertEqual(n.status, "approved")

    def test_two_editors_deciding_one_after_the_other_only_the_first_counts(self):
        n = self.news(status="review")
        version = workflow.version_token(n)
        self.do(self.ad, n, "approve", version=version)
        self.do(self.rv2, n, "request_changes", comment="Yo‘q", version=version)
        self.assertEqual(n.status, "approved")
        self.assertEqual(list(n.reviews.values_list("actor__username", "action")), [("boss", "approve")])

    def test_comment_is_escaped_where_it_is_shown(self):
        n = self.news(status="review")
        self.do(self.ad, n, "request_changes", comment='<script>alert(1)</script>')
        self.assertEqual(n.status, "changes_requested")
        page = self.cm.get(url("preview", n.pk)).content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class Editing(Base):
    BODY = {"title": "T", "excerpt": "", "body": "Boshqa", "category": None}

    def body(self, **over):
        return {"title": "Yangi sarlavha", "excerpt": "", "body": "Boshqa matn", "category": self.w.news_category.pk, **over}

    def test_editing_after_approval_returns_the_item_to_draft_and_records_it(self):
        n = self.news(status="approved")
        self.assertEqual(self.cm.post(url("edit", n.pk), self.body()).status_code, 302)
        self.assertEqual(self.status_of(n), "draft")
        self.assertEqual(n.reviews.get().action, "edit_reset")
        self.assertEqual(AuditLog.objects.get(action="news_updated").meta["approval_reset"], True)
        self.do(self.cm, n, "publish")                      # the old approval is gone
        self.assertEqual(n.status, "draft")

    def test_saving_an_approved_item_without_changes_keeps_the_approval(self):
        n = self.news(status="approved", title="Yangi sarlavha")
        n.body = "Boshqa matn"
        n.excerpt = ""
        n.save()
        self.cm.post(url("edit", n.pk), self.body())
        self.assertEqual(self.status_of(n), "approved")

    def test_an_item_under_review_cannot_be_edited_by_anyone(self):
        n = self.news(status="review")
        for client in (self.cm, self.ad, self.w.client("superuser")):
            self.assertEqual(client.get(url("edit", n.pk)).status_code, 403)
            self.assertEqual(client.post(url("edit", n.pk), self.body()).status_code, 403)
        self.assertEqual(News.objects.get(pk=n.pk).title, "Yangilik")

    def test_a_writer_edits_only_their_own_drafts(self):
        mine, theirs = self.news(author=self.writer, slug="m"), self.news(author=self.author, slug="t")
        self.assertEqual(self.wr.post(url("edit", mine.pk), self.body()).status_code, 302)
        self.assertEqual(self.wr.post(url("edit", theirs.pk), self.body()).status_code, 404)   # not even visible to a writer-only person
        self.assertEqual(News.objects.get(pk=theirs.pk).title, "Yangilik")

    def test_published_content_is_edited_only_with_the_publishing_right_and_stays_published(self):
        n = self.news(status="published", publish_at=timezone.now(), author=self.writer)
        self.assertEqual(self.wr.post(url("edit", n.pk), self.body()).status_code, 403)
        self.assertEqual(self.cm.post(url("edit", n.pk), self.body()).status_code, 302)
        self.assertEqual(self.status_of(n), "published")

    def test_editing_a_returned_item_keeps_it_returned_until_it_is_submitted_again(self):
        n = self.news(status="changes_requested")
        self.cm.post(url("edit", n.pk), self.body())
        self.assertEqual(self.status_of(n), "changes_requested")


class ScheduledAndPublic(Base):
    def test_an_approved_item_published_with_a_future_date_waits_for_that_date(self):
        future = timezone.now() + timedelta(days=2)
        n = self.news(status="approved", publish_at=future, title="Rejalashtirilgan maqola", slug="rejalashtirilgan")
        self.do(self.cm, n, "publish")
        self.assertEqual(n.status, "published")
        self.assertEqual(n.publish_at, future)                       # a schedule stays
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404)
        self.assertNotIn(n.title, Client().get(reverse("content:news_list")).content.decode())
        News.objects.filter(pk=n.pk).update(publish_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 200)

    def test_nothing_before_published_is_visible_to_the_public_or_to_search(self):
        for status in ("draft", "review", "changes_requested", "approved", "archived"):
            n = self.news(status=status, title=f"Maxfiy {status}", slug=f"v-{status}", publish_at=timezone.now() - timedelta(days=1))
            self.assertEqual(Client().get(reverse("content:news_detail", args=[n.slug])).status_code, 404, status)
            self.assertNotIn(n.title, Client().get(reverse("content:news_list")).content.decode(), status)
            self.assertNotIn(n.title, Client().get(reverse("content:home")).content.decode(), status)
            found = self.w.client("emp").get(reverse("portal:search"), {"q": n.title}).content.decode()
            self.assertIn("Hech narsa topilmadi", found, status)
            self.assertNotIn(reverse("content:news_detail", args=[n.slug]), found, status)
        self.assertEqual(Client().get(url("list")).status_code, 302)

    def test_the_published_database_rule_still_holds(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            News.objects.create(title="x", slug="x", body="b", status="published")


class Interface(Base):
    def test_buttons_follow_the_status_and_the_rights(self):
        n = self.news(status="review")
        admin_page = self.ad.get(url("preview", n.pk)).content.decode()
        self.assertIn(url("status", n.pk, "approve"), admin_page)
        self.assertIn(url("status", n.pk, "request_changes"), admin_page)
        self.assertNotIn(url("status", n.pk, "publish"), admin_page)
        self.assertNotIn(url("edit", n.pk), admin_page)
        own_page = self.cm.get(url("preview", n.pk)).content.decode()       # the author: may withdraw, may not decide
        self.assertIn(url("status", n.pk, "withdraw"), own_page)
        self.assertNotIn(url("status", n.pk, "approve"), own_page)
        self.assertNotIn(url("status", n.pk, "approve"), self.wr.get(url("preview", n.pk)).content.decode())

    def test_the_history_table_shows_who_when_what_and_the_comment_inside_the_page_body(self):
        n = self.news(status="review")
        self.do(self.ad, n, "request_changes", comment="Rasm manbasini ko‘rsating")
        html = self.cm.get(url("preview", n.pk)).content.decode()
        title_end = html.index("</title>")
        self.assertNotIn("Rasm manbasini", html[:title_end])           # not inside <head>
        body = html[html.index("<main"):]
        self.assertIn("Rasm manbasini ko‘rsating", body)
        self.assertIn("boss", body)
        self.assertIn("Tuzatishga qaytarildi", body)
        self.assertIn("Tekshiruv tarixi", body)

    def test_list_filters_by_the_new_statuses_and_shows_the_review_queue_to_reviewers(self):
        self.news(status="review", title="Navbatda", slug="q1")
        self.news(status="changes_requested", title="Qaytarilgan", slug="q2")
        self.news(status="approved", title="Ma’qullangan", slug="q3")
        page = self.ad.get(url("list"), {"status": "changes_requested"})
        self.assertContains(page, "Qaytarilgan")
        self.assertNotContains(page, "Navbatda")
        self.assertContains(self.ad.get(url("list")), "?status=review")
        self.assertNotContains(self.wr.get(url("list")), "?status=review")

    def test_confirmation_page_asks_for_a_comment_only_where_it_applies(self):
        n = self.news(status="review")
        self.assertContains(self.ad.get(url("status", n.pk, "request_changes")), 'name="comment"')
        self.assertContains(self.ad.get(url("status", n.pk, "request_changes")), "required")
        self.assertContains(self.ad.get(url("status", n.pk, "approve")), 'name="version"')
        self.assertNotContains(self.cm.get(url("status", n.pk, "withdraw")), 'name="comment"')

    def test_statuses_and_actions_follow_the_language(self):
        n = self.news(status="changes_requested")
        for code, text in (("ru", "Требуется доработка"), ("en", "Changes requested"), ("uz", "Tuzatish talab etiladi")):
            c = self.w.client("content")
            c.cookies["django_language"] = code
            self.assertContains(c.get(url("preview", n.pk)), text)
            self.assertContains(c.get(url("list")), text)


class Race(TransactionTestCase):
    """Two editors press the button at the same moment, on separate database connections."""

    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.author = make_user("auth", role="content_manager")
        self.a, self.b = make_user("ed1", role="content_manager"), make_user("ed2", role="content_manager")
        self.news = News.objects.create(title="T", slug="t", body="b", status="review", author=self.author)

    def test_exactly_one_of_two_simultaneous_decisions_wins(self):
        version = workflow.version_token(self.news)
        barrier, results = threading.Barrier(2), []

        def run(user, step):
            try:
                barrier.wait(timeout=10)
                workflow.perform(step, self.news.pk, user, comment="izoh", version=version)
                results.append((step, "ok"))
            except workflow.WorkflowError:
                results.append((step, "refused"))
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(self.a, "approve")), threading.Thread(target=run, args=(self.b, "request_changes"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(sorted(r for _s, r in results), ["ok", "refused"], results)
        self.assertEqual(NewsReview.objects.filter(news=self.news).count(), 1)
        winner = NewsReview.objects.get(news=self.news)
        self.assertEqual(News.objects.get(pk=self.news.pk).status, winner.to_status)
        self.assertEqual(AuditLog.objects.filter(object_id=str(self.news.pk)).count(), 1)
