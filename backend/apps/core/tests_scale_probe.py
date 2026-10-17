"""Day 22: N+1 and scaling probe on a synthetic data set (NOT a load test: one user, one process, a local database).

For every main list and the search the number of SQL queries is measured with a small and with a large data set. A page that issues
more queries when there is more data has an N+1 problem; the paging limit keeps one page small, so the count must stay (almost) flat.
Timings are printed for information only and are never asserted: they depend on the machine."""
import datetime
import time

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.content.models import News
from apps.core.acceptance import World
from apps.documents.models import Document, DocumentCategory, DocumentVersion
from apps.notifications.models import Notification
from apps.organization.models import Employee
from apps.tasks.models import Task

SMALL, LARGE = 30, 1500


def fill(w, n, tag):
    """n rows of every kind; everything is fictional."""
    admin, emp, hr = w.users["admin"], w.users["emp"], w.users["hr"]
    cat = DocumentCategory.objects.first()
    Employee.objects.bulk_create([Employee(last_name=f"Sinov{tag}{i}", first_name=f"Ism{i}", department=w.child, position=w.position, status="active") for i in range(n)])
    tasks = Task.objects.bulk_create([Task(title=f"Topshiriq {tag}{i}", description="d", created_by=admin, due_date=timezone.localdate() + datetime.timedelta(days=i % 30),
                                           status=["new", "in_progress", "review", "done"][i % 4]) for i in range(n)])
    through = Task.assignees.through
    through.objects.bulk_create([through(task_id=t.pk, user_id=emp.pk) for t in tasks])
    docs = Document.objects.bulk_create([Document(title=f"Hujjat {tag}{i}", category=cat, created_by=hr, access_level="general") for i in range(n)])
    DocumentVersion.objects.bulk_create([DocumentVersion(document=d, number=1, file=f"x/{tag}{i}.pdf", original_name="a.pdf", extension="pdf", size=10, sha256="0" * 64,
                                                         uploaded_by=hr, scan_status="clean") for i, d in enumerate(docs)])
    News.objects.bulk_create([News(title=f"Yangilik {tag}{i}", slug=f"y-{tag}-{i}", body="b", status=["draft", "review", "approved", "published"][i % 4], author=w.users["content"],
                                   category=w.news_category, publish_at=timezone.now() if i % 4 == 3 else None) for i in range(n)])
    Notification.objects.bulk_create([Notification(user=emp, kind="task_assigned", title=f"N {tag}{i}", task=tasks[i]) for i in range(n)])


class ScaleProbe(TestCase):
    URLS = [("tasks:list", {}), ("tasks:list", {"page": 2}), ("documents:list", {}), ("employees:list", {}), ("news_admin:list", {}), ("notifications:list", {}),
            ("portal:search", {"q": "Sinov"}), ("portal:search", {"q": "Topshiriq"}), ("portal:search", {"q": "Hujjat"}), ("portal:audit", {}), ("reports:index", {}),
            ("portal:dashboard", {}), ("content:news_list", {}), ("content:home", {})]
    ACTOR = {"news_admin:list": "content", "portal:audit": "admin", "reports:index": "hr", "employees:list": "hr", "documents:list": "hr", "content:news_list": "anon",
             "content:home": "anon", "tasks:list": "emp"}

    def measure(self, w, name, params):
        c = w.client(self.ACTOR.get(name, "emp"))
        with CaptureQueriesContext(connection) as ctx:
            start = time.perf_counter()
            r = c.get(reverse(name), params)
            took = time.perf_counter() - start
        self.assertEqual(r.status_code, 200, (name, params))
        return len(ctx), took

    def test_query_counts_do_not_grow_with_the_amount_of_data(self):
        w = World()
        fill(w, SMALL, "a")
        small = {(n, tuple(p.items())): self.measure(w, n, {k: v for k, v in p.items() if k != "page"})[0] for n, p in self.URLS}   # "page 2" needs the large set: compare with page 1
        fill(w, LARGE, "b")
        report = []
        for n, p in self.URLS:
            queries, took = self.measure(w, n, p)
            base = small[(n, tuple(p.items()))]
            report.append(f"{n:22s} {str(p):22s} queries {base:3d} -> {queries:3d}   {took * 1000:6.0f} ms (one page, {LARGE + SMALL} rows of each kind)")
            self.assertLessEqual(queries, base + 2, f"N+1 suspected on {n} {p}: {base} queries with {SMALL} rows, {queries} with {LARGE + SMALL}")
        print("\n" + "\n".join(report))

    def test_paging_and_errors_on_the_large_set(self):
        w = World()
        fill(w, LARGE, "c")
        c = w.client("emp")                                                                           # the "mine" tab: every task is assigned to this user
        self.assertEqual(c.get(reverse("tasks:list"), {"page": 9999}).status_code, 404)             # a page beyond the end: 404, not 500
        self.assertEqual(c.get(reverse("tasks:list"), {"page": "abc"}).status_code, 404)
        self.assertEqual(c.get(reverse("tasks:list"), {"page": "-1"}).status_code, 404)
        last = c.get(reverse("tasks:list"), {"page": "last"})
        self.assertEqual(last.status_code, 200)
        page = c.get(reverse("tasks:list"), {"page": 2})
        self.assertLessEqual(len(page.context["page_obj"].object_list), 25)                          # never more than one page of rows
        for q in ("a" * 5000, "%" * 200, "' OR 1=1 --", "\x00", "   "):
            self.assertLess(w.client("emp").get(reverse("portal:search"), {"q": q}).status_code, 500, repr(q)[:20])

    def test_report_exports_on_the_large_set_succeed_and_stay_bounded(self):
        w = World()
        fill(w, LARGE, "d")
        c = w.client("hr")
        for fmt in ("xlsx", "pdf", "csv"):
            start = time.perf_counter()
            r = c.get(reverse("reports:export", args=[fmt]))
            took = time.perf_counter() - start
            print(f"\nexport {fmt}: HTTP {r.status_code}, {len(r.content)} bytes, {took * 1000:.0f} ms ({LARGE} rows of each kind)")
            self.assertIn(r.status_code, (200, 404), fmt)                       # 404 only for a format the project does not offer
            if r.status_code == 200:
                self.assertLess(len(r.content), 5_000_000, fmt)                # reports are summaries, not row dumps
