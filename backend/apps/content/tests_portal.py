"""News management portal: what the content manager can do, what nobody else can, and what the public site then shows."""
import datetime

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.audit.models import AuditLog
from apps.core.acceptance import World

from . import workflow
from .models import News, NewsCategory

XSS = '<script>alert(1)</script><img src=x onerror=alert(2)>"\'&'


def url(name, *args):
    return reverse(f"news_admin:{name}", args=args)


def actions():
    return list(AuditLog.objects.filter(object_type__in=["News", "NewsCategory"]).values_list("action", flat=True))


class Base(TestCase):
    def setUp(self):
        self.w = World()
        self.cm = self.w.client("content")
        self.body = {"title": "Yangi maktab ochildi", "excerpt": "Qisqa", "body": "Birinchi abzats.\n\nIkkinchi abzats.", "category": self.w.news_category.pk}

    def create(self, **over):
        r = self.cm.post(url("create"), {**self.body, **over})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        return News.objects.filter(title=(over.get("title") or self.body["title"]).strip()).latest("created_at")

    def approve(self, news, author_client=None):
        """The real path: the author submits, a DIFFERENT person (the administrator) approves."""
        (author_client or self.cm).post(url("status", news.pk, "submit"))
        news.refresh_from_db()
        self.w.client("admin").post(url("status", news.pk, "approve"), {"version": workflow.version_token(news)})
        news.refresh_from_db()
        self.assertEqual(news.status, "approved")
        return news

    def publish(self, news):
        if news.status in ("draft", "changes_requested"):
            self.approve(news)
        self.assertEqual(self.cm.post(url("status", news.pk, "publish")).status_code, 302)
        news.refresh_from_db()
        return news

    def public_status(self, news):
        return Client().get(reverse("content:news_detail", args=[news.slug])).status_code


class ContentManagerJourney(Base):
    def test_draft_preview_publish_unpublish_archive_restore_and_the_public_site_follows(self):
        before = News.objects.count()
        n = self.create()
        self.assertEqual(News.objects.count(), before + 1)
        self.assertEqual((n.status, n.author, n.publish_at), ("draft", self.w.users["content"], None))
        self.assertTrue(n.slug)
        # a draft is invisible on the public site, by list and by direct URL
        self.assertEqual(self.public_status(n), 404)
        self.assertNotIn(n.title, Client().get(reverse("content:news_list")).content.decode())
        # but the author can preview it in the portal
        page = self.cm.get(url("preview", n.pk))
        self.assertContains(page, n.title)
        self.assertContains(page, "Ikkinchi abzats.")
        # asking only shows the question: nothing changes yet (a draft cannot be published directly any more: it must be approved first)
        ask = self.cm.get(url("status", n.pk, "submit"))
        self.assertContains(ask, n.title)
        n.refresh_from_db()
        self.assertEqual(n.status, "draft")
        self.assertEqual(self.cm.get(url("status", n.pk, "publish")).status_code, 302)  # refused: not approved
        # confirming publishes with a date
        self.publish(n)
        self.assertEqual(n.status, "published")
        self.assertLessEqual(n.publish_at, timezone.now())
        self.assertEqual(self.public_status(n), 200)
        self.assertContains(Client().get(reverse("content:news_list")), n.title)
        self.assertContains(Client().get(reverse("content:home")), n.title)
        # unpublish -> gone from the public site, back to draft
        self.assertEqual(self.cm.post(url("status", n.pk, "unpublish")).status_code, 302)
        n.refresh_from_db()
        self.assertEqual(n.status, "draft")
        self.assertEqual(self.public_status(n), 404)
        self.assertNotContains(Client().get(reverse("content:news_list")), n.title)
        # republish, then archive -> gone again; restore -> draft only (never silently public)
        self.publish(n)
        self.assertEqual(self.public_status(n), 200)
        self.cm.post(url("status", n.pk, "archive"))
        n.refresh_from_db()
        self.assertEqual((n.status, self.public_status(n)), ("archived", 404))
        self.cm.post(url("status", n.pk, "restore"))
        n.refresh_from_db()
        self.assertEqual((n.status, self.public_status(n)), ("draft", 404))
        self.assertEqual(sorted(actions()), sorted(["news_created", "news_submitted", "news_approved", "news_published", "news_unpublished", "news_submitted", "news_approved", "news_published", "news_archived", "news_restored"]))

    def test_edit_a_published_news_changes_the_public_page_and_is_audited_without_content(self):
        n = self.publish(self.create())
        r = self.cm.post(url("edit", n.pk), {**self.body, "title": "Tuzatilgan sarlavha", "body": "Yangi matn"})
        self.assertEqual(r.status_code, 302)
        n.refresh_from_db()
        self.assertEqual((n.title, n.body, n.status), ("Tuzatilgan sarlavha", "Yangi matn", "published"))
        self.assertContains(Client().get(reverse("content:news_detail", args=[n.slug])), "Tuzatilgan sarlavha")
        upd = AuditLog.objects.get(action="news_updated")
        self.assertEqual(upd.object_id, str(n.pk))
        self.assertEqual(sorted(upd.meta["fields"]), ["body", "title"])
        for e in AuditLog.objects.filter(object_type="News"):
            blob = str(e.meta) + e.object_id
            self.assertNotIn("sarlavha", blob)
            self.assertNotIn("Yangi matn", blob)
        self.assertEqual(AuditLog.objects.get(action="news_created").user, self.w.users["content"])

    def test_the_slug_is_stable_unique_and_url_safe(self):
        a = self.create(title="Bir xil sarlavha")
        b = self.create(title="Bir xil sarlavha ")  # same title, different row
        c = self.create(title="Кириллица без латиницы")
        self.assertEqual(len({a.slug, b.slug, c.slug}), 3)
        for n in (a, b, c):
            self.assertRegex(n.slug, r"^[a-z0-9-]+$")
        old = a.slug
        self.cm.post(url("edit", a.pk), {**self.body, "title": "Boshqa nom"})
        a.refresh_from_db()
        self.assertEqual(a.slug, old)

    def test_scheduled_publication_is_published_but_not_visible_until_due(self):
        n = self.create()
        future = timezone.localtime(timezone.now() + datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.cm.post(url("edit", n.pk), {**self.body, "publish_at": future})
        n = self.publish(n)
        self.assertEqual(n.status, "published")
        self.assertGreater(n.publish_at, timezone.now() + datetime.timedelta(days=1))  # the schedule survives publishing
        self.assertEqual(self.public_status(n), 404)
        page = self.cm.get(url("preview", n.pk)).content.decode()
        self.assertIn("Rejalashtirilgan", page)
        News.objects.filter(pk=n.pk).update(publish_at=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(self.public_status(n), 200)


class ValidationKeepsInput(Base):
    def test_errors_keep_what_was_typed_and_save_nothing(self):
        before = News.objects.count()
        r = self.cm.post(url("create"), {"title": "Faqat sarlavha", "excerpt": "Tavsif saqlanadi", "body": "   ", "category": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(News.objects.count(), before)
        html = r.content.decode()
        self.assertIn("Faqat sarlavha", html)
        self.assertIn("Tavsif saqlanadi", html)
        self.assertIn("err-text", html)
        self.assertEqual(actions(), [])

    def test_too_long_and_invalid_values_are_refused_without_a_server_error(self):
        for bad in ({"title": "x" * 301}, {"body": "y" * 20001}, {"excerpt": "z" * 501}, {"publish_at": "tomorrow"}, {"category": "00000000-0000-0000-0000-000000000000"}, {"title": ""}):
            r = self.cm.post(url("create"), {**self.body, **bad})
            self.assertEqual(r.status_code, 200, bad)
        self.assertEqual(News.objects.filter(title__startswith="x").count(), 0)

    def test_edit_errors_keep_input_and_leave_the_row_untouched(self):
        n = self.create()
        r = self.cm.post(url("edit", n.pk), {**self.body, "title": "Yarim tahrir", "body": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Yarim tahrir", r.content.decode())
        n.refresh_from_db()
        self.assertEqual(n.title, self.body["title"])


class Permissions(Base):
    def setUp(self):
        super().setUp()
        self.n = self.create()
        self.pub = self.publish(self.create(title="Ochiq yangilik"))

    def all_routes(self):
        n, p = self.n.pk, self.pub.pk
        cat = self.w.news_category.pk
        return [("get", url("list")), ("get", url("create")), ("get", url("categories")), ("get", url("category_create")), ("get", url("category_edit", cat)),
                ("get", url("preview", n)), ("get", url("edit", n)), ("get", url("status", n, "publish")), ("get", url("status", p, "archive"))]

    def test_people_without_the_news_rights_get_403_and_anonymous_is_sent_to_login(self):
        for actor in ("emp", "stranger", "head", "hr", "sysadmin"):
            c = self.w.client(actor)
            for method, u in self.all_routes():
                self.assertEqual(getattr(c, method)(u).status_code, 403, (actor, u))
        for method, u in self.all_routes():
            r = Client().get(u)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])

    def test_direct_posts_by_unauthorised_people_change_nothing(self):
        snapshot = list(News.objects.order_by("pk").values_list("pk", "status", "title", "body"))
        cats = NewsCategory.objects.count()
        for actor in ("emp", "stranger", "head", "hr", "sysadmin", "anon"):
            c = self.w.client(actor)
            for action in ("publish", "unpublish", "archive", "restore"):
                for news in (self.n, self.pub):
                    c.post(url("status", news.pk, action))
            c.post(url("create"), self.body | {"title": "Yashirin"})
            c.post(url("edit", self.pub.pk), self.body | {"title": "Buzilgan"})
            c.post(url("category_create"), {"name": "Soxta"})
        self.assertEqual(list(News.objects.order_by("pk").values_list("pk", "status", "title", "body")), snapshot)
        self.assertEqual(NewsCategory.objects.count(), cats)

    def test_admin_also_manages_news_but_the_django_admin_stays_closed_to_the_content_manager(self):
        self.assertEqual(self.w.client("admin").get(url("list")).status_code, 200)
        cm = self.w.users["content"]
        self.assertFalse(cm.is_staff or cm.is_superuser)
        r = self.cm.get("/" + __import__("django.conf", fromlist=["settings"]).settings.ADMIN_URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r["Location"])
        # creating news does not promote anyone
        self.create(title="Admin tekshiruvi")
        cm.refresh_from_db()
        self.assertFalse(cm.is_staff)

    def test_a_user_who_may_write_but_not_publish_is_held_at_the_publish_step(self):
        from django.contrib.auth.models import Permission

        u = self.w.users["stranger"]
        u.user_permissions.add(*Permission.objects.filter(content_type__app_label="content", codename__in=["view_news", "add_news", "change_news"]))
        c = self.w.client("stranger")
        self.assertEqual(c.get(url("list")).status_code, 200)
        self.assertEqual(c.post(url("create"), self.body | {"title": "Qoralama"}).status_code, 302)
        d = News.objects.get(title="Qoralama")
        self.assertEqual(c.post(url("edit", d.pk), self.body | {"title": "Qoralama 2"}).status_code, 302)
        self.assertEqual(c.get(url("status", d.pk, "publish")).status_code, 403)
        self.assertEqual(c.post(url("status", d.pk, "publish")).status_code, 403)
        # someone else's published item: a writer-only person does not even see it (404), and nothing changes
        self.assertEqual(c.get(url("edit", self.pub.pk)).status_code, 404)
        self.assertEqual(c.post(url("edit", self.pub.pk), self.body | {"title": "Buzildi"}).status_code, 404)
        d.refresh_from_db()
        self.pub.refresh_from_db()
        self.assertEqual((d.status, self.pub.title), ("draft", "Ochiq yangilik"))

    def test_changing_the_role_takes_effect_on_the_very_next_request(self):
        admin = self.w.client("admin")
        self.assertEqual(self.cm.get(url("list")).status_code, 200)
        assignment = RoleAssignment.objects.get(user=self.w.users["content"])
        r = admin.post(reverse("users:role_remove", args=[self.w.users["content"].pk, assignment.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.cm.get(url("list")).status_code, 403)  # same session, no re-login
        self.assertEqual(self.cm.post(url("status", self.n.pk, "publish")).status_code, 403)
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, "draft")
        # and it comes back the same way
        admin.post(reverse("users:role_add", args=[self.w.users["content"].pk]), {"role": "content_manager"})
        self.assertEqual(self.cm.get(url("list")).status_code, 200)

    def test_csrf_is_enforced_on_every_changing_request(self):
        c = self.w.client("content", csrf=True)
        before = list(News.objects.order_by("pk").values_list("pk", "status", "title"))
        for u in (url("create"), url("edit", self.n.pk), url("status", self.n.pk, "publish"), url("status", self.pub.pk, "archive"), url("category_create")):
            self.assertEqual(c.post(u, self.body).status_code, 403, u)
        self.assertEqual(list(News.objects.order_by("pk").values_list("pk", "status", "title")), before)

    def test_only_get_head_options_post_are_accepted_and_get_never_changes_state(self):
        before = list(News.objects.order_by("pk").values_list("pk", "status", "title"))
        for u in (url("list"), url("preview", self.n.pk), url("status", self.n.pk, "submit"), url("edit", self.n.pk)):
            for m in ("put", "patch", "delete"):
                self.assertEqual(getattr(self.cm, m)(u).status_code, 405, (m, u))
            self.assertEqual(self.cm.head(u).status_code, 200)
            self.assertEqual(self.cm.options(u).status_code, 200)
            self.cm.get(u)
        self.assertEqual(list(News.objects.order_by("pk").values_list("pk", "status", "title")), before)

    def test_impossible_transitions_and_unknown_actions_are_refused_without_changes(self):
        # archived cannot be published directly; a draft cannot be unpublished
        self.cm.post(url("status", self.n.pk, "archive"))
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, "archived")
        self.cm.post(url("status", self.n.pk, "publish"))
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, "archived")
        self.cm.post(url("status", self.n.pk, "archive"))  # twice: second is a no-op
        self.assertEqual(actions().count("news_archived"), 1)
        self.assertEqual(self.cm.post(url("status", self.n.pk, "delete")).status_code, 404)
        self.assertEqual(self.cm.post(url("status", "11111111-1111-1111-1111-111111111111".replace("1", "2"), "publish")).status_code, 404)
        self.assertTrue(News.objects.filter(pk=self.n.pk).exists())  # nothing in the portal deletes news


class UserContent(Base):
    def test_xss_in_every_field_is_escaped_in_portal_and_public_pages(self):
        n = self.create(title="T " + XSS, excerpt=XSS, body=XSS + "\n" + XSS)
        self.publish(n)
        pages = [self.cm.get(url("list")), self.cm.get(url("preview", n.pk)), self.cm.get(url("edit", n.pk)),
                 Client().get(reverse("content:news_list")), Client().get(reverse("content:news_detail", args=[n.slug])), Client().get(reverse("content:home"))]
        for p in pages:
            html = p.content.decode()
            self.assertNotIn("<script>alert(1)", html)
            self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", pages[1].content.decode())

    def test_xss_in_a_category_name_and_a_search_term_is_escaped(self):
        self.cm.post(url("category_create"), {"name": XSS})
        self.assertTrue(NewsCategory.objects.filter(name=XSS).exists())
        for p in (self.cm.get(url("categories")), self.cm.get(url("list")), self.cm.get(url("list") + "?q=" + XSS)):
            self.assertNotIn("<script>alert(1)", p.content.decode())

    def test_links_in_the_text_are_plain_text_not_anchors(self):
        n = self.publish(self.create(body="Qarang: https://evil.test/x va javascript:alert(1) <a href=\"https://evil.test\">bos</a>"))
        html = Client().get(reverse("content:news_detail", args=[n.slug])).content.decode()
        self.assertNotIn('<a href="https://evil.test', html)
        self.assertNotIn('href="javascript:', html)


class ListAndCategories(Base):
    def test_search_status_filter_and_pagination(self):
        for i in range(23):
            News.objects.create(title=f"Ommaviy {i:02d}", slug=f"ommaviy-{i}", body="m", status="draft")
        arch = News.objects.create(title="Eski xabar", slug="eski", body="m", status="archived")
        first = self.cm.get(url("list"))
        self.assertEqual(len(first.context["items"]), 20)
        second = self.cm.get(url("list") + "?page=2")
        self.assertEqual(len(second.context["items"]), 5)  # 23 + 1 archived + the world's published one = 25
        self.assertEqual([n.title for n in self.cm.get(url("list") + "?q=eski").context["items"]], ["Eski xabar"])
        self.assertEqual([n.pk for n in self.cm.get(url("list") + "?status=archived").context["items"]], [arch.pk])
        self.assertEqual(self.cm.get(url("list") + "?page=999").status_code, 404)
        self.assertEqual(self.cm.get(url("list") + "?status=nonsense&category=not-a-uuid").status_code, 200)

    def test_category_create_rename_duplicate_and_audit(self):
        self.assertEqual(self.cm.post(url("category_create"), {"name": "Sport"}).status_code, 302)
        c = NewsCategory.objects.get(name="Sport")
        self.assertRegex(c.slug, r"^[a-z0-9-]+$")
        dup = self.cm.post(url("category_create"), {"name": " sport "})
        self.assertEqual(dup.status_code, 200)
        self.assertEqual(NewsCategory.objects.filter(name__iexact="sport").count(), 1)
        self.assertEqual(self.cm.post(url("category_edit", c.pk), {"name": "Sport va salomatlik"}).status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.name, "Sport va salomatlik")
        self.assertEqual(actions().count("news_category_changed"), 2)
        self.assertEqual(c.slug, NewsCategory.objects.get(pk=c.pk).slug)

    def test_public_behaviour_of_published_news_is_unchanged(self):
        self.assertEqual(Client().get(reverse("content:news_detail", args=["yangilik"])).status_code, 200)
        self.assertContains(Client().get(reverse("content:news_list")), "Yangilik")


class Languages(Base):
    def lang(self, code):
        c = self.w.client("content")
        c.cookies["django_language"] = code
        return c

    def test_messages_errors_statuses_and_confirmations_follow_the_language(self):
        for code, err, ok, ask, status in (
            ("ru", "Краткое описание слишком длинное (не более 500 символов).", "Новость опубликована.", "Опубликовать новость?", "Черновик"),
            ("en", "The summary is too long (at most 500 characters).", "News item published.", "Publish this news item?", "Draft"),
            ("uz", "Qisqa tavsif juda uzun (ko‘pi bilan 500 belgi).", "Yangilik nashr etildi.", "Yangilikni nashr etasizmi?", "Qoralama"),
        ):
            c = self.lang(code)
            bad = c.post(url("create"), {**self.body, "excerpt": "z" * 501})
            self.assertContains(bad, err)
            title = f"Til {code}"
            c.post(url("create"), {**self.body, "title": title})
            n = News.objects.get(title=title)
            self.assertContains(c.get(url("preview", n.pk)), status)
            self.approve(n, author_client=c)
            self.assertContains(c.get(url("status", n.pk, "publish")), ask)
            done = c.post(url("status", n.pk, "publish"), follow=True)
            self.assertContains(done, ok)
            self.assertContains(done, f'<html lang="{code}">')
