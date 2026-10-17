"""Global search: what it finds, what it must never reveal, and that every link it offers opens for the person who sees it."""
import datetime
import re

from django.test import Client
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.audit.models import AuditLog
from apps.content.models import News
from apps.core.acceptance import World
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import add_version
from apps.documents.testing import upload
from apps.documents.validation import validate_upload
from apps.organization.models import Employee
from apps.tasks.models import Task

SEARCH = reverse("portal:search")


def find(client, q, **extra):
    return client.get(SEARCH, {"q": q, **extra})


def titles(response):
    return [i["title"] for s in response.context["sections"] for i in s["items"]]


def without_query(response, q):
    """Page text minus the visitor's own query, which is echoed back in the search box."""
    from django.utils.html import escape

    return response.content.decode().replace(escape(q), "")


def kinds(response):
    return {s["kind"]: s["count"] for s in response.context["sections"] if s["count"]}


class Base(TestCase):
    def setUp(self):
        self.w = World()
        self.cat = DocumentCategory.objects.first()
        self.c = {a: self.w.client(a) for a in ("emp", "stranger", "content", "head", "hr", "admin", "sysadmin", "superuser")}

    def doc(self, title, **kw):
        d = Document.objects.create(title=title, category=self.cat, created_by=kw.pop("creator", self.w.users["hr"]), **kw)
        add_version(d, validate_upload(upload("a.pdf")), actor=d.created_by)
        return d


class EachSource(Base):
    def test_every_supported_kind_is_found_by_an_authorised_user(self):
        a = self.c["admin"]
        self.assertEqual(kinds(find(a, "Aliyev")), {"employees": 1})
        self.assertEqual(kinds(find(a, "A1")), {"departments": 1})
        self.assertEqual(kinds(find(a, "Hisobot")), {"tasks": 1})
        self.assertEqual(kinds(find(a, "Nizom")), {"documents": 1})
        self.assertEqual(kinds(find(a, "Yangilik")), {"news": 1})
        self.assertEqual(titles(find(a, "aliyev vali")), ["Aliyev Vali"])  # case-insensitive, every word must match
        self.assertEqual(titles(find(a, "aliyev zzzz")), [])
        self.assertEqual(titles(find(a, "Metodist")), ["Aliyev Vali"])  # position is a directory field

    def test_description_and_number_fields_are_searched_where_documented(self):
        Task.objects.filter(pk=self.w.task.pk).update(description="maxsus tavsif matni")
        self.doc("Boshqa", number="BR-77", description="yillik reja")
        self.assertEqual(titles(find(self.c["admin"], "maxsus tavsif")), ["Hisobot"])
        self.assertEqual(titles(find(self.c["admin"], "BR-77")), ["Boshqa"])
        self.assertEqual(titles(find(self.c["admin"], "yillik")), ["Boshqa"])

    def test_results_are_ordered_and_limited_with_a_count_and_a_link_to_all(self):
        for i in range(25):
            Task.objects.create(title=f"Reja {i:02d}", created_by=self.w.users["admin"]).assignees.set([self.w.users["emp"]])
        r = find(self.c["admin"], "Reja")
        s = [x for x in r.context["sections"] if x["items"]][0]
        self.assertEqual((s["kind"], s["count"], len(s["items"]), s["more"]), ("tasks", 25, 5, True))
        self.assertContains(r, "type=tasks")
        p1 = find(self.c["admin"], "Reja", type="tasks")
        self.assertEqual((len([x for x in p1.context["sections"] if x["items"]][0]["items"]), p1.context["paginator"].count), (20, 25))
        p2 = find(self.c["admin"], "Reja", type="tasks", page=2)
        self.assertEqual(len([x for x in p2.context["sections"] if x["items"]][0]["items"]), 5)
        self.assertEqual(find(self.c["admin"], "Reja", type="tasks", page=3).status_code, 404)
        self.assertEqual(find(self.c["admin"], "Reja", type="tasks", page="x").status_code, 404)
        self.assertEqual(find(self.c["admin"], "Reja", type="users").status_code, 404)


class NoLeaks(Base):
    def test_confidential_closed_archived_and_other_department_documents_do_not_appear(self):
        from apps.organization.models import Department

        self.doc("Yopiq bo‘lim hujjati", access_level="department", department=Department.objects.create(name="Bo‘lim C"))
        archived = self.doc("Arxivdagi hujjat", status="archived")
        for actor in ("emp", "stranger", "head", "content", "sysadmin"):
            for q in ("Maxfiy", "Yopiq bo‘lim", "Arxivdagi"):
                r = find(self.c[actor], q)
                self.assertEqual(titles(r), [], (actor, q))
                body = without_query(r, q)
                for secret in ("Maxfiy", "Yopiq bo‘lim hujjati", "Arxivdagi hujjat"):
                    self.assertNotIn(secret, body, (actor, q))
        for actor in ("hr", "admin", "superuser"):
            self.assertEqual(titles(find(self.c[actor], "Maxfiy")), ["Maxfiy"], actor)
        self.assertEqual(titles(find(self.c["hr"], "Arxivdagi")), [])  # search shows active documents only, for everybody
        self.assertEqual(Document.objects.filter(pk=archived.pk).count(), 1)
        self.assertEqual(titles(find(self.c["emp"], "Yopiq")), [])
        # the same person with the right department DOES find a department document
        dept_own = self.doc("Bo‘lim ichki", access_level="department", department=self.w.root)
        self.assertEqual(titles(find(self.c["emp"], "Bo‘lim ichki")), ["Bo‘lim ichki"])
        self.assertEqual(titles(find(self.c["stranger"], "Bo‘lim ichki")), [])
        self.assertTrue(dept_own.pk)

    def test_counts_do_not_reveal_hidden_items_either(self):
        for i in range(3):
            self.doc(f"Maxfiy hisobot {i}", access_level="confidential")
        r = find(self.c["emp"], "Maxfiy")
        self.assertEqual((r.context["total"], [x for x in r.context["sections"] if x["items"]]), (0, []))
        self.assertEqual(find(self.c["hr"], "Maxfiy").context["total"], 4)

    def test_contact_and_private_employee_fields_are_never_searched_or_shown(self):
        for actor in self.c:
            for q in ("+998 71 111 22 33", "998 90 555", "555 66 77", "1990", "17.05.1990", "vali@work", "work.example", "emp@example.test"):
                r = find(self.c[actor], q)
                self.assertNotIn("employees", kinds(r), (actor, q))
                body = without_query(r, q)
                for secret in ("+998 71 111 22 33", "+998 90 555 66 77", "17.05.1990", "vali@work.example.test"):
                    self.assertNotIn(secret, body, (actor, q))
        body = find(self.c["hr"], "Aliyev").content.decode()  # even HR, who may open the card, gets directory fields only in the results
        for secret in ("+998", "1990", "@work"):
            self.assertNotIn(secret, body)

    def test_employees_are_listed_like_the_directory_and_links_follow_the_card_rules(self):
        arch = Employee.objects.create(last_name="Arxivov", first_name="Asad", department=self.w.child, status="archived")
        self.assertEqual(titles(find(self.c["emp"], "Arxivov")), [])  # archived: only people who can edit employees
        self.assertEqual(titles(find(self.c["hr"], "Arxivov")), ["Arxivov Asad"])
        card = reverse("employees:detail", args=[self.w.card.pk])
        for actor, opens in (("hr", True), ("admin", True), ("emp", True), ("stranger", True)):
            r = find(self.c[actor], "Aliyev")
            self.assertEqual(titles(r), ["Aliyev Vali"], actor)
            self.assertEqual(card in r.content.decode(), opens, actor)  # the card opens for everybody who is offered the link
        self.assertTrue(arch.pk)

    def test_only_published_and_already_due_news_is_found_by_anyone(self):
        now = timezone.now()
        mk = lambda t, **kw: News.objects.create(title=t, slug=t.lower().replace(" ", "-"), body="m", **kw)  # noqa: E731
        mk("Qoralama yangilik", status="draft")
        mk("Arxiv yangilik", status="archived", publish_at=now)
        mk("Kelajak yangilik", status="published", publish_at=now + datetime.timedelta(days=3))
        mk("Ochiq yangilik", status="published", publish_at=now - datetime.timedelta(days=1))
        for actor in self.c:
            self.assertEqual(sorted(titles(find(self.c[actor], "yangilik"))), ["Ochiq yangilik", "Yangilik"], actor)

    def test_tasks_follow_the_task_visibility_rules(self):
        hidden = Task.objects.create(title="Yashirin topshiriq", created_by=self.w.users["admin"])
        hidden.assignees.set([self.w.users["stranger"]])
        self.assertEqual(titles(find(self.c["emp"], "Yashirin")), [])
        self.assertEqual(titles(find(self.c["stranger"], "Yashirin")), ["Yashirin topshiriq"])
        self.assertEqual(titles(find(self.c["admin"], "Yashirin")), ["Yashirin topshiriq"])
        self.assertEqual(titles(find(self.c["hr"], "Yashirin")), [])

    def test_users_audit_and_notifications_are_not_searchable_here(self):
        for q in ("boss", "sysadm", "emp@example.test", "login", "task_assigned"):
            for actor in ("admin", "superuser", "sysadmin"):
                r = find(self.c[actor], q)
                self.assertEqual({k for k in kinds(r)} - {"news", "employees", "departments", "tasks", "documents"}, set())
                self.assertEqual(titles(r), [], (actor, q))

    def test_a_user_without_rights_gets_only_public_news(self):
        r = find(self.c["sysadmin"], "Aliyev")
        self.assertEqual(titles(r), [])
        r = find(self.c["sysadmin"], "Yangilik")
        self.assertEqual(kinds(r), {"news": 1})

    def test_losing_a_role_changes_the_results_on_the_next_request(self):
        self.assertEqual(titles(find(self.c["hr"], "Maxfiy")), ["Maxfiy"])
        RoleAssignment.objects.filter(user=self.w.users["hr"]).delete()
        r = find(self.c["hr"], "Maxfiy")
        self.assertEqual(titles(r), [])
        self.assertEqual(find(self.c["hr"], "Aliyev").context["total"], 0)

    def test_every_link_offered_opens_for_the_person_who_sees_it(self):
        self.doc("Nizom ikkinchi")
        pool = ("Aliyev", "Botirov", "A1", "Bo‘lim", "Hisobot", "Nizom", "Maxfiy", "Yangilik", "Head")
        for actor, client in self.c.items():
            for q in pool:
                for href in re.findall(r'<li><a href="([^"]+)"', find(client, q).content.decode()):
                    self.assertEqual(client.get(href).status_code, 200, (actor, q, href))


class QueryHandling(Base):
    def test_short_empty_long_and_odd_queries_are_handled_calmly(self):
        a = self.c["admin"]
        self.assertTrue(find(a, "A").context["too_short"])
        self.assertContains(find(a, "A"), "alert warn")
        r = a.get(SEARCH)
        self.assertEqual((r.status_code, r.context["searched"]), (200, False))
        self.assertEqual(find(a, "   ").context["searched"], False)
        long_q = "Hisobot " * 40
        r = find(a, long_q)
        self.assertLessEqual(len(r.context["q"]), 100)
        self.assertEqual(find(a, "a b c d e f g h Hisobot").context["total"], 0)  # at most 5 words are used; the rest is ignored
        for q in ("%%", "__", "\\", "'; DROP TABLE tasks_task; --", "a\x00b", "‮evil", "😀😀", "Hisobot\n\r\t"):
            r = find(a, q)
            self.assertEqual(r.status_code, 200, repr(q))
        self.assertEqual(find(a, "%%").context["total"], 0)  # wildcards are literal characters
        self.assertEqual(find(a, "__").context["total"], 0)
        self.assertTrue(Task.objects.exists())
        self.assertEqual(titles(find(a, "Hisobot\n\r\t")), ["Hisobot"])

    def test_the_query_is_escaped_everywhere_it_is_echoed(self):
        q = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
        for params in ({}, {"type": "tasks"}):
            html = find(self.c["admin"], q, **params).content.decode()
            self.assertNotIn("<script>alert(1)", html)
            self.assertNotIn("<img src=x", html)
        Task.objects.filter(pk=self.w.task.pk).update(title="T <script>alert(1)</script>")
        html = find(self.c["admin"], "script").content.decode()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)

    def test_pagination_links_carry_the_query_safely(self):
        for i in range(21):
            Task.objects.create(title=f"Reja & «{i}»", created_by=self.w.users["admin"])
        html = find(self.c["admin"], "Reja &", type="tasks").content.decode()
        self.assertIn("q=Reja%20%26&amp;type=tasks&amp;page=2", html)

    def test_searching_leaves_no_trace_in_the_audit_log(self):
        before = AuditLog.objects.count()
        for q in ("Aliyev", "Maxfiy", "zzzz"):
            find(self.c["hr"], q)
        self.assertEqual(AuditLog.objects.count(), before)


class Access(Base):
    def test_anonymous_goes_to_login_and_the_page_only_reads(self):
        r = Client().get(SEARCH, {"q": "Aliyev"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        c = self.c["admin"]
        self.assertEqual(c.post(SEARCH, {"q": "x"}).status_code, 405)
        for m in ("put", "patch", "delete"):
            self.assertEqual(getattr(c, m)(SEARCH).status_code, 405)
        self.assertEqual(c.head(SEARCH + "?q=Aliyev").status_code, 200)

    def test_csrf_is_not_needed_because_nothing_changes_and_nothing_is_stored(self):
        c = self.w.client("admin", csrf=True)
        self.assertEqual(c.get(SEARCH, {"q": "Aliyev"}).status_code, 200)

    def test_direct_urls_of_hidden_results_stay_closed(self):
        secret = self.w.secret_doc
        for actor in ("emp", "stranger", "head", "content"):
            self.assertEqual(self.c[actor].get(reverse("documents:detail", args=[secret.pk])).status_code, 403, actor)
        hidden = Task.objects.create(title="Yashirin", created_by=self.w.users["admin"])
        hidden.assignees.set([self.w.users["stranger"]])
        self.assertEqual(self.c["emp"].get(reverse("tasks:detail", args=[hidden.pk])).status_code, 403)


class Languages(Base):
    def test_page_texts_and_empty_state_follow_the_language(self):
        for lang, heading, empty in (("ru", "Поиск", "Ничего не найдено"), ("en", "Search", "Nothing found"), ("uz", "Qidiruv", "Hech narsa topilmadi")):
            c = self.w.client("admin")
            c.cookies["django_language"] = lang
            page = find(c, "zzzzzz")
            self.assertContains(page, f'<html lang="{lang}">')
            self.assertContains(page, heading)
            self.assertContains(page, empty)
            body = find(c, "Aliyev").content.decode()
            if lang != "uz":
                for word in ("Xodimlar", "Qidirish", "Topshiriqlar", "Barchasini"):
                    self.assertNotIn(word, body, (lang, word))
        c = self.w.client("admin")
        c.cookies["django_language"] = "ru"
        self.assertContains(find(c, "A"), "Введите не менее 2 символов.")

    def test_the_top_bar_offers_search_on_every_portal_page(self):
        html = self.c["emp"].get(reverse("portal:dashboard")).content.decode()
        self.assertIn(f'action="{SEARCH}"', html)
        self.assertIn("topsearch-link", html)
