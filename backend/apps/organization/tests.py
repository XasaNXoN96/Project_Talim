from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Department, Employee, Institution, Position


class OrganizationModelTests(TestCase):
    def test_top_level_department_names_are_unique(self):
        Department.objects.create(name="Rahbariyat")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Department.objects.create(name="Rahbariyat")

    def test_same_name_allowed_under_different_parents(self):
        a = Department.objects.create(name="A")
        b = Department.objects.create(name="B")
        Department.objects.create(name="Guruh", parent=a)
        Department.objects.create(name="Guruh", parent=b)
        self.assertEqual(Department.objects.filter(name="Guruh").count(), 2)

    def test_department_with_employees_cannot_be_deleted(self):
        d = Department.objects.create(name="IT")
        Employee.objects.create(last_name="Namunaviy", first_name="Xodim", department=d)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            d.delete()

    def test_position_name_unique(self):
        Position.objects.create(name="Metodist")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Position.objects.create(name="Metodist")

    def test_employee_defaults_and_str(self):
        d = Department.objects.create(name="IT")
        e = Employee.objects.create(last_name="Namunaviy", first_name="Xodim", department=d)
        self.assertEqual(e.status, Employee.Status.NEW)
        self.assertEqual(str(e), "Namunaviy Xodim")

    def test_institution_is_unpublished_by_default(self):
        self.assertFalse(Institution.objects.create(name="Namuna maktab", kind="school").is_published)
