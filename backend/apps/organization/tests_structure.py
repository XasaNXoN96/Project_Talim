from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog

from .models import Department, Employee, Position


def url(name, *args):
    return reverse(f"employees:{name}", args=args)


class StructureTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.worker = make_user("worker", role="employee")
        self.a = Department.objects.create(name="A")
        self.a1 = Department.objects.create(name="A1", parent=self.a)
        self.a11 = Department.objects.create(name="A11", parent=self.a1)
        Employee.objects.create(last_name="X", first_name="Y", department=self.a1, status="active")
        Employee.objects.create(last_name="Z", first_name="W", department=self.a1, status="archived")

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def test_everyone_signed_in_with_org_view_sees_tree_with_active_counts(self):
        body = self.client_for(self.worker).get(url("structure")).content.decode()
        self.assertLess(body.index(">A<"), body.index(">A1<"))
        self.assertLess(body.index(">A1<"), body.index(">A11<"))
        self.assertIn("<td>1</td>", body)  # archived employee is not counted

    def test_edit_controls_only_for_editors(self):
        self.assertNotContains(self.client_for(self.worker).get(url("structure")), url("department_create"))
        self.assertContains(self.client_for(self.hr).get(url("structure")), url("department_create"))

    def test_employee_cannot_write(self):
        c = self.client_for(self.worker)
        self.assertEqual(c.get(url("department_create")).status_code, 403)
        self.assertEqual(c.post(url("department_create"), {"name": "Hack", "is_active": "on"}).status_code, 403)
        self.assertEqual(c.post(url("department_edit", self.a.pk), {"name": "Hack"}).status_code, 403)
        self.assertEqual(c.post(url("position_create"), {"name": "Hack"}).status_code, 403)
        self.assertFalse(Department.objects.filter(name="Hack").exists())

    def test_hr_creates_department_with_audit(self):
        r = self.client_for(self.hr).post(url("department_create"), {"name": "B", "is_active": "on"})
        self.assertRedirects(r, url("structure"), fetch_redirect_response=False)
        self.assertTrue(Department.objects.filter(name="B").exists())
        entry = AuditLog.objects.get(action=AuditLog.Action.ORG_CHANGED)
        self.assertTrue(entry.meta["created"])
        self.assertEqual(entry.user, self.hr)

    def test_department_cannot_move_under_its_own_descendant(self):
        r = self.client_for(self.hr).post(url("department_edit", self.a.pk), {"name": "A", "parent": self.a11.pk, "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.parent)

    def test_department_cannot_be_its_own_parent(self):
        r = self.client_for(self.hr).post(url("department_edit", self.a.pk), {"name": "A", "parent": self.a.pk, "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.parent)

    def test_duplicate_name_under_same_parent_is_rejected_case_insensitively(self):
        r = self.client_for(self.hr).post(url("department_create"), {"name": "a", "is_active": "on"})
        self.assertContains(r, "allaqachon bor")

    def test_department_with_active_staff_cannot_be_deactivated(self):
        r = self.client_for(self.hr).post(url("department_edit", self.a1.pk), {"name": "A1", "parent": self.a.pk})
        self.assertContains(r, "o‘chirib bo‘lmaydi")
        self.a1.refresh_from_db()
        self.assertTrue(self.a1.is_active)

    def test_empty_department_can_be_deactivated(self):
        self.client_for(self.hr).post(url("department_edit", self.a11.pk), {"name": "A11", "parent": self.a1.pk})
        self.a11.refresh_from_db()
        self.assertFalse(self.a11.is_active)

    def test_positions(self):
        c = self.client_for(self.hr)
        c.post(url("position_create"), {"name": "Metodist"})
        p = Position.objects.get(name="Metodist")
        c.post(url("position_edit", p.pk), {"name": "Katta metodist"})
        p.refresh_from_db()
        self.assertEqual(p.name, "Katta metodist")
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.ORG_CHANGED).count(), 2)
        self.assertContains(c.post(url("position_create"), {"name": "Katta metodist"}), "allaqachon mavjud")
