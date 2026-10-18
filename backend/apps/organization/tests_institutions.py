from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog

from .models import Department, Employee, Institution


def url(name, *args):
    return reverse(f"employees:{name}", args=args)


class InstitutionTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.worker = make_user("worker", role="employee")
        self.dept = Department.objects.create(name="Bo‘lim")
        self.school = Institution.objects.create(name="1-sonli maktab", kind="school", head_name="Aliyev")
        self.other = Institution.objects.create(name="2-sonli maktab", kind="school")
        Employee.objects.create(last_name="Karimov", first_name="A", department=self.dept, institution=self.school, status="active")
        Employee.objects.create(last_name="Saidov", first_name="B", department=self.dept, institution=self.other, status="active")
        Employee.objects.create(last_name="Office", first_name="C", department=self.dept, status="active")

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def test_structure_lists_institutions_with_staff_counts(self):
        body = self.client_for(self.hr).get(url("structure")).content.decode()
        self.assertIn("1-sonli maktab", body)
        self.assertIn(url("institution_create"), body)

    def test_plain_employee_cannot_manage_institutions(self):
        c = self.client_for(self.worker)
        self.assertEqual(c.get(url("institution_create")).status_code, 403)
        self.assertEqual(c.get(url("institution_edit", self.school.pk)).status_code, 403)
        self.assertNotContains(c.get(url("structure")), url("institution_create"))

    def test_create_and_edit_with_audit_and_unique_name(self):
        c = self.client_for(self.hr)
        r = c.post(url("institution_create"), {"name": "3-sonli maktab", "kind": "school", "head_name": "", "is_published": "on"})
        self.assertEqual(r.status_code, 302)
        new = Institution.objects.get(name="3-sonli maktab")
        self.assertTrue(new.is_published)
        self.assertTrue(AuditLog.objects.filter(object_type="Institution", object_id=str(new.pk)).exists())
        dup = c.post(url("institution_create"), {"name": "3-SONLI MAKTAB", "kind": "school"})
        self.assertEqual(dup.status_code, 200)
        self.assertEqual(Institution.objects.filter(name__iexact="3-sonli maktab").count(), 1)

    def test_employee_list_filters_by_institution(self):
        c = self.client_for(self.hr)
        body = c.get(url("list"), {"institution": str(self.school.pk)}).content.decode()
        self.assertIn("Karimov", body)
        self.assertNotIn("Saidov", body)
        self.assertNotIn("Office", body)
        self.assertEqual(c.get(url("list"), {"institution": "not-a-uuid"}).status_code, 200)

    def test_employee_form_saves_institution(self):
        c = self.client_for(self.hr)
        e = Employee.objects.get(last_name="Office")
        data = {"last_name": "Office", "first_name": "C", "middle_name": "", "department": str(self.dept.pk), "position": "", "institution": str(self.other.pk), "status": "active"}
        self.assertEqual(c.post(url("edit", e.pk), data).status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.institution_id, self.other.pk)
