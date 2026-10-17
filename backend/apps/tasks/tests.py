import datetime

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.organization.models import Department, Employee

from .models import Task, TaskComment, TaskEvent


def url(name, *args):
    return reverse(f"tasks:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.root = Department.objects.create(name="A")
        self.child = Department.objects.create(name="A1", parent=self.root)
        self.other = Department.objects.create(name="B")
        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=self.head, role=Group.objects.get(name="department_head"), scope="department", department=self.root)
        self.in_dept = self._person("indept", self.child)
        self.out_dept = self._person("outdept", self.other)
        self.stranger = self._person("stranger", self.other)
        self._employee(self.head, self.root)

    def _employee(self, user, dept):
        return Employee.objects.create(last_name=user.username.title(), first_name="X", department=dept, user=user, status="active")

    def _person(self, username, dept):
        user = make_user(username, role="employee")
        self._employee(user, dept)
        return user

    def task(self, creator=None, assignees=(), **kw):
        t = Task.objects.create(title=kw.pop("title", "Hisobot"), created_by=creator or self.head, **kw)
        t.assignees.set(assignees or [self.in_dept])
        return t

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c


class VisibilityTests(Base):
    def test_assignee_and_creator_see_it_others_do_not(self):
        t = self.task()
        for user, expected in ((self.in_dept, 200), (self.head, 200), (self.admin, 200), (self.stranger, 403), (self.out_dept, 403), (self.hr, 403)):
            self.assertEqual(self.client_for(user).get(url("detail", t.pk)).status_code, expected, user.username)

    def test_department_head_sees_tasks_of_people_in_the_branch_only(self):
        mine = self.task(creator=self.admin, assignees=[self.in_dept], title="Ichki")
        theirs = self.task(creator=self.admin, assignees=[self.out_dept], title="Tashqi")
        c = self.client_for(self.head)
        self.assertEqual(c.get(url("detail", mine.pk)).status_code, 200)
        self.assertEqual(c.get(url("detail", theirs.pk)).status_code, 403)
        body = c.get(url("list"), {"tab": "all"}).content.decode()
        self.assertIn("Ichki", body)
        self.assertNotIn("Tashqi", body)

    def test_list_tabs(self):
        self.task(creator=self.head, assignees=[self.in_dept], title="BerganMen")
        self.task(creator=self.admin, assignees=[self.head], title="MengaBerilgan")
        c = self.client_for(self.head)
        mine = c.get(url("list")).content.decode()
        self.assertIn("MengaBerilgan", mine)
        self.assertNotIn("BerganMen", mine)
        self.assertIn("BerganMen", c.get(url("list"), {"tab": "created"}).content.decode())

    def test_closed_tasks_hidden_on_personal_tabs_until_asked(self):
        self.task(assignees=[self.in_dept], title="Yopilgan", status="done")
        c = self.client_for(self.in_dept)
        self.assertNotIn("Yopilgan", c.get(url("list")).content.decode())
        self.assertIn("Yopilgan", c.get(url("list"), {"status": "done"}).content.decode())

    def test_anonymous_redirected_sysadmin_forbidden(self):
        t = self.task()
        self.assertEqual(Client().get(url("list")).status_code, 302)
        sysadm = make_user("sys", role="sysadmin")
        self.assertEqual(self.client_for(sysadm).get(url("list")).status_code, 403)
        self.assertEqual(self.client_for(sysadm).get(url("detail", t.pk)).status_code, 403)


class CreateTests(Base):
    def payload(self, **kw):
        d = {"title": "Yangi", "description": "Matn", "priority": "normal", "due_date": "2030-01-01", "assignees": [self.in_dept.pk]}
        d.update(kw)
        return d

    def test_plain_employee_cannot_create(self):
        c = self.client_for(self.in_dept)
        self.assertEqual(c.get(url("create")).status_code, 403)
        self.assertEqual(c.post(url("create"), self.payload()).status_code, 403)
        self.assertEqual(Task.objects.count(), 0)

    def test_head_creates_for_own_branch_with_history(self):
        r = self.client_for(self.head).post(url("create"), self.payload())
        t = Task.objects.get()
        self.assertRedirects(r, url("detail", t.pk), fetch_redirect_response=False)
        self.assertEqual((t.created_by, t.status), (self.head, "new"))
        self.assertEqual(list(t.assignees.all()), [self.in_dept])
        self.assertEqual(t.events.get().kind, "created")

    def test_head_cannot_assign_outside_the_branch_even_with_a_forged_id(self):
        r = self.client_for(self.head).post(url("create"), self.payload(assignees=[self.out_dept.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Task.objects.count(), 0)

    def test_hr_and_admin_can_assign_anyone(self):
        for user in (self.hr, self.admin):
            self.client_for(user).post(url("create"), self.payload(assignees=[self.out_dept.pk], title=f"T-{user.username}"))
        self.assertEqual(Task.objects.count(), 2)

    def test_at_least_one_assignee(self):
        self.assertContains(self.client_for(self.head).post(url("create"), self.payload(assignees=[])), "to&#x27;ldirilishi shart")

    def test_inactive_user_cannot_be_assigned(self):
        self.in_dept.is_active = False
        self.in_dept.save()
        self.assertEqual(self.client_for(self.head).post(url("create"), self.payload()).status_code, 200)
        self.assertEqual(Task.objects.count(), 0)

    def test_html_in_text_is_escaped(self):
        self.client_for(self.head).post(url("create"), self.payload(title="<script>alert(1)</script>"))
        t = Task.objects.get()
        body = self.client_for(self.head).get(url("detail", t.pk)).content.decode()
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)


class TransitionTests(Base):
    def move(self, user, task, status):
        return self.client_for(user).post(url("transition", task.pk, status))

    def test_assignee_flow_and_creator_acceptance(self):
        t = self.task()
        self.move(self.in_dept, t, "in_progress")
        self.move(self.in_dept, t, "review")
        t.refresh_from_db()
        self.assertEqual(t.status, "review")
        self.move(self.in_dept, t, "done")  # assignee cannot accept own work
        t.refresh_from_db()
        self.assertEqual(t.status, "review")
        self.move(self.head, t, "done")
        t.refresh_from_db()
        self.assertEqual(t.status, "done")
        self.assertIsNotNone(t.closed_at)
        self.assertEqual([e.kind for e in t.events.all()], ["status", "status", "status"])

    def test_creator_can_return_from_review(self):
        t = self.task(status="review")
        self.move(self.head, t, "in_progress")
        t.refresh_from_db()
        self.assertEqual(t.status, "in_progress")

    def test_final_states_are_final(self):
        for final in ("done", "cancelled"):
            t = self.task(status=final)
            for target in ("new", "in_progress", "review", "done", "cancelled"):
                self.move(self.head, t, target)
                self.move(self.admin, t, target)
            t.refresh_from_db()
            self.assertEqual(t.status, final)

    def test_outsiders_and_unrelated_roles_cannot_move(self):
        t = self.task()
        for user in (self.stranger, self.out_dept, self.hr):
            self.assertEqual(self.move(user, t, "cancelled").status_code, 403, user.username)
        t.refresh_from_db()
        self.assertEqual(t.status, "new")

    def test_assignee_cannot_cancel_or_skip_to_done(self):
        t = self.task()
        for target in ("cancelled", "done"):
            self.move(self.in_dept, t, target)
        t.refresh_from_db()
        self.assertEqual(t.status, "new")

    def test_unknown_status_is_refused_without_change(self):
        t = self.task()
        self.move(self.head, t, "weird")
        t.refresh_from_db()
        self.assertEqual(t.status, "new")

    def test_get_not_allowed(self):
        t = self.task()
        self.assertEqual(self.client_for(self.head).get(url("transition", t.pk, "cancelled")).status_code, 405)

    def test_admin_sees_and_can_cancel_anything(self):
        t = self.task()
        self.move(self.admin, t, "cancelled")
        t.refresh_from_db()
        self.assertEqual(t.status, "cancelled")


class EditAndCommentTests(Base):
    def edit_payload(self, **kw):
        d = {"title": "Yangilandi", "description": "", "priority": "high", "due_date": "", "assignees": [self.in_dept.pk]}
        d.update(kw)
        return d

    def test_creator_edits_and_only_changed_field_names_are_recorded(self):
        t = self.task(title="Eski", priority="normal")
        self.client_for(self.head).post(url("edit", t.pk), self.edit_payload())
        t.refresh_from_db()
        self.assertEqual((t.title, t.priority), ("Yangilandi", "high"))
        ev = t.events.get(kind="edited")
        self.assertEqual(ev.meta["fields"], ["priority", "title"])
        self.assertNotIn("Yangilandi", str(ev.meta))

    def test_assignee_and_strangers_cannot_edit(self):
        t = self.task()
        for user in (self.in_dept, self.stranger, self.hr):
            c = self.client_for(user)
            self.assertEqual(c.get(url("edit", t.pk)).status_code, 403, user.username)
            self.assertEqual(c.post(url("edit", t.pk), self.edit_payload()).status_code, 403, user.username)
        t.refresh_from_db()
        self.assertEqual(t.title, "Hisobot")

    def test_closed_task_cannot_be_edited(self):
        t = self.task(status="done")
        self.assertEqual(self.client_for(self.head).get(url("edit", t.pk)).status_code, 403)

    def test_existing_assignee_outside_scope_is_kept_on_edit(self):
        t = self.task(creator=self.admin, assignees=[self.in_dept, self.out_dept])
        # a department head may not edit tasks of people outside the branch... but coverage through in_dept allows edit
        r = self.client_for(self.head).post(url("edit", t.pk), self.edit_payload(assignees=[self.in_dept.pk, self.out_dept.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(t.assignees.count(), 2)

    def test_head_cannot_add_new_outside_assignee_on_edit(self):
        t = self.task()
        r = self.client_for(self.head).post(url("edit", t.pk), self.edit_payload(assignees=[self.in_dept.pk, self.out_dept.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(t.assignees.count(), 1)

    def test_comment_by_participant_recorded_without_text_in_history(self):
        t = self.task()
        self.client_for(self.in_dept).post(url("comment", t.pk), {"body": "Tayyor, maxfiy-matn"})
        self.assertEqual(TaskComment.objects.get().author, self.in_dept)
        ev = t.events.get(kind="commented")
        self.assertNotIn("maxfiy-matn", str(ev.meta))
        self.assertContains(self.client_for(self.head).get(url("detail", t.pk)), "maxfiy-matn")

    def test_stranger_cannot_comment_and_empty_comment_is_refused(self):
        t = self.task()
        self.assertEqual(self.client_for(self.stranger).post(url("comment", t.pk), {"body": "x"}).status_code, 403)
        self.client_for(self.in_dept).post(url("comment", t.pk), {"body": "   "})
        self.client_for(self.in_dept).post(url("comment", t.pk), {"body": "a" * 4001})
        self.assertEqual(TaskComment.objects.count(), 0)

    def test_menu_entry_depends_on_permission(self):
        self.assertContains(self.client_for(self.in_dept).get(reverse("portal:dashboard")), url("list"))
        sysadm = make_user("sys", role="sysadmin")
        self.assertNotContains(self.client_for(sysadm).get(reverse("portal:dashboard")), url("list"))

    def test_overdue_marker(self):
        self.task(title="Kechikkan", due_date=datetime.date(2000, 1, 1))
        self.assertContains(self.client_for(self.in_dept).get(url("list")), "Muddati o‘tgan")
