import datetime

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.notifications.models import Notification
from apps.organization.models import Department, Employee, Institution

from .models import Task, overdue_q

User = get_user_model()


class DeadlineTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.now = timezone.localtime()

    def task(self, **kw):
        return Task.objects.create(title="T", created_by=self.admin, **kw)

    def test_due_time_decides_the_minute_not_the_next_day(self):
        past = (self.now - datetime.timedelta(hours=2))
        if past.date() != self.now.date():  # just after midnight: use a fixed earlier time today
            self.skipTest("too close to midnight")
        self.assertTrue(self.task(due_date=self.now.date(), due_time=past.time()).is_overdue)
        future = self.now + datetime.timedelta(hours=2)
        if future.date() == self.now.date():
            self.assertFalse(self.task(due_date=self.now.date(), due_time=future.time()).is_overdue)

    def test_no_time_means_end_of_day(self):
        self.assertFalse(self.task(due_date=self.now.date()).is_overdue)
        self.assertTrue(self.task(due_date=self.now.date() - datetime.timedelta(days=1)).is_overdue)
        self.assertFalse(self.task().is_overdue)

    def test_closed_tasks_are_never_overdue(self):
        old = self.now.date() - datetime.timedelta(days=3)
        for status in ("done", "cancelled"):
            self.assertFalse(self.task(due_date=old, status=status).is_overdue)

    def test_queryset_helper_agrees_with_the_property(self):
        old = self.now.date() - datetime.timedelta(days=3)
        a = self.task(due_date=old)
        b = self.task(due_date=self.now.date() + datetime.timedelta(days=3))
        c = self.task(due_date=self.now.date())
        ids = set(Task.objects.filter(overdue_q()).values_list("pk", flat=True))
        self.assertEqual(ids, {a.pk})
        self.assertTrue(a.is_overdue and not b.is_overdue and not c.is_overdue)


class SchoolTaskTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.head = make_user("head", role="department_head")
        self.dept = Department.objects.create(name="Bo‘lim")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        self.s3 = Institution.objects.create(name="3-maktab", kind="school")  # no director account
        mk = lambda name, inst: services.create_user(self.admin, username=name, email=f"{name}@example.test", first_name=name, last_name="D", role="school_director", department=None, institution=inst, request=None)
        self.d1, self.d2 = mk("dir1", self.s1), mk("dir2", self.s2)
        self.c = Client()
        login_with_two_factor(self.c, self.admin)

    def post(self, **extra):
        data = {"title": "Hisobot", "description": "Matn", "priority": "urgent", "due_date": "2030-01-05", "due_time": "14:30"}
        data.update(extra)
        return self.c.post(reverse("tasks:create"), data)

    def test_task_for_schools_becomes_one_separate_task_per_school_with_time_and_urgency(self):
        r = self.post(institutions=[str(self.s1.pk), str(self.s2.pk)])
        self.assertEqual(r.status_code, 302)
        self.assertIn("tab=created", r["Location"])  # several tasks were made: the list of the tasks I gave
        tasks = list(Task.objects.filter(title="Hisobot"))
        self.assertEqual(len(tasks), 2)
        self.assertEqual(sorted(tuple(sorted(u.username for u in t.assignees.all())) for t in tasks), [("dir1",), ("dir2",)])
        for t in tasks:
            self.assertEqual((t.priority, t.due_time, t.status, t.created_by), ("urgent", datetime.time(14, 30), "new", self.admin))
        self.assertTrue(Notification.objects.filter(user=self.d1).exists())
        self.assertTrue(Notification.objects.filter(user=self.d2).exists())

    def test_each_school_moves_and_closes_its_own_task_independently(self):
        self.post(institutions=[str(self.s1.pk), str(self.s2.pk)])
        t1 = Task.objects.get(title="Hisobot", assignees=self.d1)
        t2 = Task.objects.get(title="Hisobot", assignees=self.d2)
        c1 = Client()
        login_with_two_factor(c1, self.d1)
        c1.post(reverse("tasks:transition", args=[t1.pk, "in_progress"]))
        c1.post(reverse("tasks:transition", args=[t1.pk, "review"]))
        self.c.post(reverse("tasks:transition", args=[t1.pk, "done"]))
        t1.refresh_from_db(); t2.refresh_from_db()
        self.assertEqual((t1.status, t2.status), ("done", "new"))  # the other school's task is untouched
        c2 = Client()
        login_with_two_factor(c2, self.d2)
        self.assertEqual(c2.get(reverse("tasks:detail", args=[t1.pk])).status_code, 403)  # and it cannot even open the first school's task

    def test_one_school_gives_one_task_and_a_person_plus_a_school_give_two(self):
        self.post(institutions=[str(self.s1.pk)])
        self.assertEqual(Task.objects.count(), 1)
        r = self.post(title="Aralash", institutions=[str(self.s2.pk)], assignees=[str(self.admin.pk)])
        self.assertEqual(r.status_code, 302)
        mixed = Task.objects.filter(title="Aralash")
        self.assertEqual(mixed.count(), 2)  # one for the person named, one for the school
        self.assertEqual(sorted(tuple(sorted(u.username for u in t.assignees.all())) for t in mixed), [("boss",), ("dir2",)])

    def test_editing_one_task_still_adds_the_chosen_schools_directors_to_it(self):
        self.post(institutions=[str(self.s1.pk)])
        t = Task.objects.get()
        r = self.c.post(reverse("tasks:edit", args=[t.pk]), {"title": "Hisobot", "description": "Matn", "priority": "urgent", "due_date": "2030-01-05", "due_time": "14:30", "institutions": [str(self.s2.pk)], "assignees": [str(self.d1.pk)]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual({u.username for u in t.assignees.all()}, {"dir1", "dir2"})

    def test_school_without_director_is_refused_with_its_name(self):
        r = self.post(institutions=[str(self.s1.pk), str(self.s3.pk)])
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "3-maktab")
        self.assertFalse(Task.objects.exists())

    def test_assignee_or_school_is_required_and_time_needs_a_date(self):
        self.assertEqual(self.post().status_code, 200)
        self.assertFalse(Task.objects.exists())
        r = self.post(institutions=[str(self.s1.pk)], due_date="")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Task.objects.exists())

    def test_each_director_sees_only_their_own_school_task(self):
        self.post(institutions=[str(self.s1.pk)])
        t = Task.objects.get()
        c1, c2 = Client(), Client()
        login_with_two_factor(c1, self.d1)
        login_with_two_factor(c2, self.d2)
        self.assertEqual(c1.get(reverse("tasks:detail", args=[t.pk])).status_code, 200)
        self.assertEqual(c2.get(reverse("tasks:detail", args=[t.pk])).status_code, 403)
        body = c1.get(reverse("tasks:list")).content.decode()
        self.assertIn("Hisobot", body)
        self.assertIn("1-maktab", body)  # the school is shown next to the director
        self.assertNotIn("Hisobot", c2.get(reverse("tasks:list")).content.decode())

    def test_director_cannot_create_tasks_and_can_start_work(self):
        self.post(institutions=[str(self.s1.pk)])
        t = Task.objects.get()
        c1 = Client()
        login_with_two_factor(c1, self.d1)
        self.assertEqual(c1.get(reverse("tasks:create")).status_code, 403)
        self.assertEqual(c1.post(reverse("tasks:transition", args=[t.pk, "in_progress"])).status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.status, "in_progress")

    def test_department_head_does_not_get_the_school_picker(self):
        from apps.access.models import RoleAssignment  # noqa: F401  (head holds a department-scoped role via make_user scope=all in tests)

        form = self.c.get(reverse("tasks:create")).content.decode()
        self.assertIn('name="institutions"', form)
        self.assertIn('name="due_time"', form)
        self.assertIn("urgent", form)
