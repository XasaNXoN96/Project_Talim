import datetime
from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.organization.models import Department, Employee
from apps.tasks.models import Task

from .models import Notification
from .services import notify, send_email_copy, unread_count

K = Notification.Kind


def tu(name, *args):
    return reverse(f"tasks:{name}", args=args)


def nu(name, *args):
    return reverse(f"notifications:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.dept = Department.objects.create(name="A")
        self.other = Department.objects.create(name="B")
        self.head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=self.head, role=Group.objects.get(name="department_head"), scope="department", department=self.dept)
        Employee.objects.create(last_name="Head", first_name="H", department=self.dept, user=self.head, status="active")
        self.worker = self._person("worker", self.dept)
        self.worker2 = self._person("worker2", self.dept)
        self.stranger = self._person("stranger", self.other)

    def _person(self, name, dept):
        u = make_user(name, role="employee")
        Employee.objects.create(last_name=name.title(), first_name="X", department=dept, user=u, status="active")
        return u

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def task(self, assignees=None, **kw):
        t = Task.objects.create(title=kw.pop("title", "Hisobot"), created_by=self.head, **kw)
        t.assignees.set(assignees or [self.worker])
        return t

    def kinds(self, user):
        return list(Notification.objects.filter(user=user).order_by("created_at").values_list("kind", flat=True))


class EventTests(Base):
    def test_assignment_notifies_assignees_but_not_the_creator(self):
        self.client_for(self.head).post(tu("create"), {"title": "Yangi", "description": "", "priority": "normal", "due_date": "", "assignees": [self.worker.pk, self.head.pk]})
        self.assertEqual(self.kinds(self.worker), [K.TASK_ASSIGNED])
        self.assertEqual(self.kinds(self.head), [])
        self.assertEqual(self.kinds(self.worker2), [])

    def test_adding_an_assignee_on_edit_notifies_only_the_new_one(self):
        t = self.task()
        data = {"title": "Hisobot", "description": "", "priority": "normal", "due_date": "", "assignees": [self.worker.pk, self.worker2.pk]}
        self.client_for(self.head).post(tu("edit", t.pk), data)
        self.assertEqual(self.kinds(self.worker2), [K.TASK_ASSIGNED])
        self.assertEqual(self.kinds(self.worker), [])

    def test_full_cycle(self):
        t = self.task()
        w, h = self.client_for(self.worker), self.client_for(self.head)
        w.post(tu("transition", t.pk, "in_progress"))
        w.post(tu("transition", t.pk, "review"))
        self.assertEqual(self.kinds(self.head), [K.TASK_SUBMITTED])
        h.post(tu("transition", t.pk, "in_progress"))
        self.assertEqual(self.kinds(self.worker), [K.TASK_RETURNED])
        w.post(tu("transition", t.pk, "review"))
        h.post(tu("transition", t.pk, "done"))
        self.assertEqual(self.kinds(self.worker), [K.TASK_RETURNED, K.TASK_ACCEPTED])

    def test_cancellation_notifies_assignees_and_creator_when_someone_else_cancels(self):
        t = self.task(assignees=[self.worker, self.worker2])
        self.client_for(self.head).post(tu("transition", t.pk, "cancelled"))
        self.assertEqual(self.kinds(self.worker), [K.TASK_CANCELLED])
        self.assertEqual(self.kinds(self.worker2), [K.TASK_CANCELLED])
        self.assertEqual(self.kinds(self.head), [])  # the actor

    def test_refused_transition_creates_nothing(self):
        t = self.task()
        self.client_for(self.worker).post(tu("transition", t.pk, "done"))
        self.assertEqual(Notification.objects.count(), 0)

    def test_refreshing_pages_never_creates_notifications(self):
        t = self.task()
        notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        c = self.client_for(self.worker)
        for _ in range(5):
            c.get(nu("list"))
            c.get(tu("detail", t.pk))
            c.get(reverse("portal:dashboard"))
        self.assertEqual(Notification.objects.count(), 1)

    def test_inactive_user_gets_nothing(self):
        self.worker.is_active = False
        self.worker.save()
        self.assertIsNone(notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head))


class ReminderTests(Base):
    def run_cmd(self):
        out = StringIO()
        call_command("send_task_reminders", stdout=out)
        return out.getvalue().strip()

    def test_due_soon_and_overdue_are_created_once_per_assignee(self):
        today = timezone.localdate()
        self.task(assignees=[self.worker, self.worker2], title="Ertaga", due_date=today + datetime.timedelta(days=1))
        self.task(title="Bugun", due_date=today)
        self.task(title="Kechikkan", due_date=today - datetime.timedelta(days=3))
        self.task(title="Uzoq", due_date=today + datetime.timedelta(days=10))
        self.task(title="Muddatsiz")
        self.assertEqual(self.run_cmd(), "due_soon=3 overdue=1")
        self.assertEqual(sorted(self.kinds(self.worker)), sorted([K.TASK_DUE_SOON, K.TASK_DUE_SOON, K.TASK_OVERDUE]))

    def test_running_again_creates_no_duplicates(self):
        self.task(due_date=timezone.localdate())
        self.run_cmd()
        for _ in range(3):
            self.assertEqual(self.run_cmd(), "due_soon=0 overdue=0")
        self.assertEqual(Notification.objects.count(), 1)

    def test_closed_tasks_are_skipped(self):
        for st in ("done", "cancelled"):
            self.task(status=st, due_date=timezone.localdate() - datetime.timedelta(days=1))
        self.run_cmd()
        self.assertEqual(Notification.objects.count(), 0)

    def test_overdue_is_sent_once_not_every_day(self):
        t = self.task(due_date=timezone.localdate() - datetime.timedelta(days=1))
        self.run_cmd()
        with mock.patch("django.utils.timezone.localdate", return_value=timezone.localdate() + datetime.timedelta(days=5)):
            self.run_cmd()
        self.assertEqual(Notification.objects.filter(task=t, kind=K.TASK_OVERDUE).count(), 1)

    def test_changing_the_due_date_allows_a_new_reminder(self):
        t = self.task(due_date=timezone.localdate())
        self.run_cmd()
        t.due_date = timezone.localdate() + datetime.timedelta(days=1)
        t.save()
        self.assertEqual(self.run_cmd(), "due_soon=1 overdue=0")

    def test_inactive_assignee_skipped(self):
        self.worker.is_active = False
        self.worker.save()
        self.task(due_date=timezone.localdate())
        self.run_cmd()
        self.assertEqual(Notification.objects.count(), 0)

    def test_same_dedupe_key_is_idempotent_at_the_service_level(self):
        t = self.task()
        self.assertIsNotNone(notify(self.worker, K.TASK_DUE_SOON, t, dedupe_key="k1"))
        self.assertIsNone(notify(self.worker, K.TASK_DUE_SOON, t, dedupe_key="k1"))
        self.assertIsNotNone(notify(self.worker2, K.TASK_DUE_SOON, t, dedupe_key="k1"))  # key is per user


class ListAndAccessTests(Base):
    def test_counter_and_mark_read(self):
        t = self.task()
        a = notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        notify(self.worker, K.TASK_ACCEPTED, t, actor=self.head)
        c = self.client_for(self.worker)
        self.assertEqual(unread_count(self.worker), 2)
        self.assertContains(c.get(reverse("portal:dashboard")), 'id="unreadCount">2<')
        c.post(nu("read", a.pk))
        self.assertEqual(unread_count(self.worker), 1)
        c.post(nu("read_all"))
        self.assertEqual(unread_count(self.worker), 0)
        self.assertNotContains(c.get(reverse("portal:dashboard")), "unreadCount")

    def test_open_marks_read_and_goes_to_the_task(self):
        t = self.task()
        n = notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        r = self.client_for(self.worker).post(nu("open", n.pk))
        self.assertRedirects(r, tu("detail", t.pk), fetch_redirect_response=False)
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_cannot_touch_someone_elses_notification(self):
        n = notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head)
        c = self.client_for(self.stranger)
        for name in ("open", "read"):
            self.assertEqual(c.post(nu(name, n.pk)).status_code, 404)
        n.refresh_from_db()
        self.assertIsNone(n.read_at)
        self.assertNotContains(c.get(nu("list")), "Hisobot")

    def test_read_all_only_touches_own(self):
        t = self.task(assignees=[self.worker, self.worker2])
        notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        notify(self.worker2, K.TASK_ASSIGNED, t, actor=self.head)
        self.client_for(self.worker).post(nu("read_all"))
        self.assertEqual((unread_count(self.worker), unread_count(self.worker2)), (0, 1))

    def test_target_is_rechecked_when_access_was_lost(self):
        t = self.task()
        n = notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        t.assignees.set([self.worker2])  # worker is no longer on the task
        c = self.client_for(self.worker)
        page = c.get(nu("list")).content.decode()
        self.assertNotIn("Hisobot", page)  # title hidden
        self.assertNotIn(nu("open", n.pk), page)  # no link offered
        r = c.post(nu("open", n.pk))
        self.assertRedirects(r, nu("list"), fetch_redirect_response=False)
        self.assertEqual(c.get(tu("detail", t.pk)).status_code, 403)

    def test_methods_and_anonymous(self):
        n = notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head)
        c = self.client_for(self.worker)
        for name in ("open", "read"):
            self.assertEqual(c.get(nu(name, n.pk)).status_code, 405)
        self.assertEqual(c.get(nu("read_all")).status_code, 405)
        self.assertEqual(Client().get(nu("list")).status_code, 302)
        self.assertEqual(Client().post(nu("read_all")).status_code, 302)

    def test_csrf_enforced(self):
        n = notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head)
        c = Client(enforce_csrf_checks=True)
        login_with_two_factor(c, self.worker)
        self.assertEqual(c.post(nu("read", n.pk)).status_code, 403)

    def test_sysadmin_without_tasks_has_no_bell(self):
        sysadm = make_user("sys", role="sysadmin")
        self.assertNotContains(self.client_for(sysadm).get(reverse("portal:dashboard")), nu("list"))
        self.assertEqual(self.client_for(sysadm).get(nu("list")).status_code, 403)

    def test_html_in_task_title_is_escaped_in_the_list(self):
        t = self.task(title="<img src=x onerror=alert(1)>")
        notify(self.worker, K.TASK_ASSIGNED, t, actor=self.head)
        self.assertNotContains(self.client_for(self.worker).get(nu("list")), "<img src=x")


class EmailLayerTests(Base):
    def test_off_by_default_nothing_is_sent(self):
        with self.captureOnCommitCallbacks(execute=True):
            notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NOTIFICATION_EMAILS_ENABLED=True)
    def test_when_enabled_a_minimal_mail_is_sent_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            notify(self.worker, K.TASK_ASSIGNED, self.task(title="Hisobot"), actor=self.head)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, [self.worker.email])
        self.assertNotIn("http", m.body)

    @override_settings(NOTIFICATION_EMAILS_ENABLED=True)
    def test_a_mail_failure_does_not_break_the_action(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("smtp down")):
            with self.captureOnCommitCallbacks(execute=True):
                n = notify(self.worker, K.TASK_ASSIGNED, self.task(), actor=self.head)
            self.assertFalse(send_email_copy(n))
        self.assertIsNotNone(n)

    def test_default_setting_is_off(self):
        from django.conf import settings

        self.assertFalse(settings.NOTIFICATION_EMAILS_ENABLED)
