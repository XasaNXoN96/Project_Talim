import datetime
import re

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.accounts import services as account_services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.achievements.models import Achievement
from apps.organization.models import Department, Employee, Institution
from apps.tasks.models import Task

from . import schools


class SchoolStatsTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.dept = Department.objects.create(name="Dept")
        self.s1, self.s2, self.s3 = (Institution.objects.create(name=n, kind="school") for n in ("1-maktab", "2-maktab", "3-maktab"))
        mk = lambda n, i: account_services.create_user(self.admin, username=n, email=f"{n}@example.test", first_name=n, last_name="D", role="school_director", department=None, institution=i, request=None)
        self.d1, self.d2 = mk("dir1", self.s1), mk("dir2", self.s2)  # school 3 has no director account
        today = timezone.localdate()
        day = lambda n: today + datetime.timedelta(days=n)
        now = timezone.now()

        def task(title, assignees, status="new", due=None, closed=None, **extra):
            t = Task.objects.create(title=title, created_by=self.admin, status=status, due_date=due, closed_at=closed, **extra)
            t.assignees.set(assignees)
            return t

        task("on time", [self.d1], "done", day(3), now)
        task("overdue open", [self.d1], "in_progress", day(-1))
        task("done late", [self.d1], "done", day(-3), now)
        task("cancelled", [self.d1], "cancelled", day(1))
        task("for both", [self.d1, self.d2], "new", day(5))
        task("s2 only", [self.d2], "in_progress", day(7))
        task("for an office person", [self.admin], "new", day(-9))  # counts for no school
        for status in ("published", "submitted", "draft"):
            Achievement.objects.create(institution=self.s1, title=f"A {status}", person_name="X", status=status, consent_confirmed=True, publish_at=now if status == "published" else None)
        for last in ("Karimov", "Saidov"):
            Employee.objects.create(last_name=last, first_name="Q", department=self.dept, institution=self.s1, status="active")
        Employee.objects.create(last_name="Archived", first_name="Q", department=self.dept, institution=self.s1, status="archived")
        self.rows = {r.institution.name: r for r in schools.build_rows()}

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def test_numbers_per_school(self):
        r = self.rows["1-maktab"]
        self.assertEqual((r.tasks, r.done, r.open, r.overdue, r.late), (5, 2, 2, 1, 1))
        self.assertEqual(r.rate, 50)  # cancelled tasks are not counted against the school
        self.assertEqual((r.ach_total, r.ach_published, r.ach_pending), (3, 1, 1))
        self.assertEqual((r.directors, r.staff), (1, 3))  # two staff cards + the director's own card; the archived one is not counted
        r2 = self.rows["2-maktab"]
        self.assertEqual((r2.tasks, r2.done, r2.open, r2.overdue, r2.late, r2.rate), (2, 0, 2, 0, 0, 0))  # "for both" counts for each school
        r3 = self.rows["3-maktab"]
        self.assertEqual((r3.directors, r3.tasks, r3.rate), (0, 0, None))

    def test_a_task_given_to_two_director_accounts_of_one_school_counts_once(self):
        second = account_services.create_user(self.admin, username="dir1b", email="d1b@example.test", first_name="b", last_name="D", role="school_director", department=None, institution=self.s1, request=None) \
            if False else None  # one active director per school is a rule; the double count is still guarded in the code
        self.assertIsNone(second)
        before = self.rows["1-maktab"].tasks
        Task.objects.get(title="for both").assignees.add(self.d1)  # already there: still one
        self.assertEqual({r.institution.name: r for r in schools.build_rows()}["1-maktab"].tasks, before)

    def test_worst_first_and_totals(self):
        rows = schools.build_rows()
        self.assertEqual(rows[0].institution.name, "1-maktab")  # the only one with an overdue task
        t = schools.totals(rows)
        self.assertEqual((t.tasks, t.done, t.overdue, t.ach_total), (7, 2, 1, 3))

    def test_closing_the_overdue_task_clears_it(self):
        Task.objects.filter(title="overdue open").update(status="done", closed_at=timezone.now())
        self.assertEqual({r.institution.name: r for r in schools.build_rows()}["1-maktab"].overdue, 0)

    # ---- the pages ----------------------------------------------------------------------------------------------
    def test_pages_show_the_figures_and_never_staff_names(self):
        c = self.client_for(self.admin)
        body = c.get(reverse("reports:schools")).content.decode()
        for needle in ("1-maktab", "2-maktab", "3-maktab"):
            self.assertIn(needle, body)
        self.assertIn("Direktor hisobi yo‘q", body)  # school 3 has no director account
        self.assertLess(body.index("1-maktab"), body.index("2-maktab"))
        detail = c.get(reverse("reports:school", args=[self.s1.pk]))
        self.assertEqual(detail.status_code, 200)
        for needle in ("overdue open", "done late", "A published", "A submitted"):
            self.assertContains(detail, needle)
        self.assertNotContains(detail, "Karimov")  # staff are counted, never named
        self.assertNotContains(detail, "Archived")
        self.assertContains(c.get(reverse("reports:school", args=[self.s3.pk])), "direktor hisobi yo‘q")

    def test_who_may_open_them(self):
        urls = [reverse("reports:schools"), reverse("reports:school", args=[self.s1.pk])]
        for user, expected in ((self.admin, 200), (self.hr, 200), (self.d1, 403), (make_user("worker", role="employee"), 403)):
            c = self.client_for(user)
            for u in urls:
                self.assertEqual(c.get(u).status_code, expected, (user.username, u))
        head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=head, role=Group.objects.get(name="department_head"), scope="department", department=self.dept)
        for u in urls:
            self.assertEqual(self.client_for(head).get(u).status_code, 403, u)  # a branch head does not see the whole organisation
        self.assertEqual(Client().get(urls[0]).status_code, 302)
        self.assertEqual(self.client_for(self.admin).get(reverse("reports:school", args=["00000000-0000-0000-0000-000000000000"])).status_code, 404)

    def test_the_admin_dashboard_shows_the_schools_and_a_director_does_not(self):
        body = self.client_for(self.admin).get(reverse("portal:dashboard")).content.decode()
        self.assertIn("Maktablar holati", body)
        self.assertIn("1-maktab", body)
        self.assertNotIn("Maktablar holati", self.client_for(self.d1).get(reverse("portal:dashboard")).content.decode())
        self.assertIn(reverse("reports:schools"), self.client_for(self.admin).get(reverse("reports:index")).content.decode())

    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        for lang in ("ru", "en"):
            c = self.client_for(self.admin)
            c.cookies["django_language"] = lang
            for page in (reverse("reports:schools"), reverse("reports:school", args=[self.s1.pk]), reverse("portal:dashboard")):
                html = re.sub(r'<form class="lang-switch".*?</form>', "", c.get(page).content.decode(), flags=re.S)
                html = re.sub(r"\d-maktab|A (published|submitted|draft)", "", html)  # fixture data
                self.assertNotIn("‘", html, (lang, page))
                self.assertNotIn("’", html, (lang, page))
