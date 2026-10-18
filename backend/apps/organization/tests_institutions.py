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


class SchoolDirectorTests(TestCase):
    """The director of a school signs in alone: sees only their own institution's staff; one director account per institution."""

    def setUp(self):
        from django.contrib.auth.models import Group

        from apps.access.models import RoleAssignment
        from apps.accounts import services

        self.services = services
        self.Group, self.RoleAssignment = Group, RoleAssignment
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.dept = Department.objects.create(name="Bo‘lim")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        self.t1 = Employee.objects.create(last_name="Karimov", first_name="A", department=self.dept, institution=self.s1, status="active", work_phone="+998 90 111 22 33")
        self.t2 = Employee.objects.create(last_name="Saidov", first_name="B", department=self.dept, institution=self.s2, status="active", work_phone="+998 90 999 88 77")
        self.office = Employee.objects.create(last_name="Office", first_name="C", department=self.dept, status="active")

    def create_director(self, username="dir1", inst=None):
        class Req:  # services only pass the request on to the audit log
            META = {}
            user = None
        return self.services.create_user(
            self.admin, username=username, email=f"{username}@example.test", first_name="Dilshod", last_name="Direktor",
            role="school_director", department=None, institution=inst or self.s1, request=None,
        )

    def test_one_step_creates_account_card_and_role(self):
        u = self.create_director()
        a = self.RoleAssignment.objects.get(user=u)
        self.assertEqual((a.role.name, a.scope, a.department), ("school_director", "institution", None))
        card = Employee.objects.get(user=u)
        self.assertEqual(card.institution, self.s1)
        self.assertEqual(card.position.name, "Maktab direktori")
        self.assertFalse(u.has_usable_password())

    def test_institution_is_required_and_only_one_director_per_institution(self):
        with self.assertRaises(self.services.ActionNotAllowed):
            self.services.create_user(self.admin, username="x1", email="x1@example.test", first_name="A", last_name="B", role="school_director", department=None, request=None)
        self.create_director("dir1")
        with self.assertRaises(self.services.ActionNotAllowed):
            self.create_director("dir2")
        self.assertFalse(User_exists("dir2"))
        self.create_director("dir3", inst=self.s2)  # another institution is fine

    def test_director_sees_only_own_institution(self):
        u = self.create_director()
        c = Client()
        login_with_two_factor(c, u)
        listing = c.get(url("list")).content.decode()
        self.assertIn("Karimov", listing)
        self.assertIn("Dilshod", listing)  # own card
        self.assertNotIn("Saidov", listing)
        self.assertNotIn("Office", listing)
        own = c.get(url("detail", self.t1.pk))
        self.assertEqual(own.status_code, 200)
        self.assertContains(own, "+998 90 111 22 33")  # contacts of own staff
        self.assertEqual(c.get(url("detail", self.t2.pk)).status_code, 403)
        self.assertEqual(c.get(url("detail", self.office.pk)).status_code, 403)

    def test_director_cannot_manage_anything(self):
        u = self.create_director()
        c = Client()
        login_with_two_factor(c, u)
        for name, args in (("structure", ()), ("institution_create", ()), ("import", ())):
            self.assertEqual(c.get(url(name, *args)).status_code, 403, name)
        self.assertEqual(c.get(url("edit", self.t2.pk)).status_code, 404)  # another school's staff
        self.assertEqual(c.get(reverse("users:list")).status_code, 403)
        self.assertEqual(c.get(reverse("portal:admin_hub")).status_code, 403)

    def test_role_for_existing_user_needs_institution_and_links_the_card(self):
        u = make_user("plain")
        with self.assertRaises(self.services.ActionNotAllowed):
            self.services.assign_role(self.admin, u, role="school_director", department=None, request=None)
        self.services.assign_role(self.admin, u, role="school_director", department=None, institution=self.s2, request=None)
        self.assertEqual(Employee.objects.get(user=u).institution, self.s2)

    def test_user_with_card_of_another_institution_is_refused(self):
        u = make_user("moved")
        Employee.objects.create(last_name="M", first_name="M", department=self.dept, institution=self.s2, user=u, status="active")
        with self.assertRaises(self.services.ActionNotAllowed):
            self.services.assign_role(self.admin, u, role="school_director", department=None, institution=self.s1, request=None)


def User_exists(username):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(username=username).exists()


class SchoolStaffTests(TestCase):
    """Stage B: the director maintains the staff of their own school, and only that."""

    def setUp(self):
        from apps.accounts import services

        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.dept = Department.objects.create(name="Bo‘lim")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        self.mine = Employee.objects.create(last_name="Karimov", first_name="A", department=self.dept, institution=self.s1, status="active", birth_date="1990-01-01", personal_phone="+998 90 000 00 00")
        self.theirs = Employee.objects.create(last_name="Saidov", first_name="B", department=self.dept, institution=self.s2, status="active")
        self.office = Employee.objects.create(last_name="Office", first_name="C", department=self.dept, status="active")
        self.director = services.create_user(self.admin, username="dir1", email="d1@example.test", first_name="Dilshod", last_name="Direktor",
                                             role="school_director", department=None, institution=self.s1, request=None)
        self.c = Client()
        login_with_two_factor(self.c, self.director)

    def form(self, **extra):
        data = {"last_name": "Yangi", "first_name": "Xodim", "middle_name": "", "position": "", "work_phone": "+998 90 123 45 67", "work_email": "x@example.test", "status": "active"}
        data.update(extra)
        return data

    def test_add_button_yes_import_button_no(self):
        body = self.c.get(url("list")).content.decode()
        self.assertIn(url("create"), body)
        self.assertNotIn(url("import"), body)

    def test_create_forces_own_institution_and_office_department(self):
        # even if the client tries to smuggle department/institution/account/private values
        r = self.c.post(url("create"), self.form(institution=str(self.s2.pk), department=str(self.dept.pk), user=str(self.admin.pk), birth_date="2000-02-02", personal_phone="+998 1"))
        self.assertEqual(r.status_code, 302)
        e = Employee.objects.get(last_name="Yangi")
        self.assertEqual(e.institution, self.s1)
        self.assertEqual(e.department.name, "Ta’lim muassasalari")
        self.assertIsNone(e.user)
        self.assertIsNone(e.birth_date)
        self.assertEqual(e.personal_phone, "")

    def test_form_has_no_office_account_or_private_fields(self):
        body = self.c.get(url("create")).content.decode()
        for hidden in ('name="department"', 'name="institution"', 'name="user"', 'name="birth_date"', 'name="personal_phone"', 'name="hired_at"'):
            self.assertNotIn(hidden, body, hidden)
        self.assertIn('name="work_phone"', body)

    def test_edit_and_archive_only_own_staff_without_account(self):
        self.assertEqual(self.c.post(url("edit", self.mine.pk), self.form(last_name="Karimov2", first_name="A")).status_code, 302)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.last_name, "Karimov2")
        self.assertEqual(self.mine.birth_date.isoformat(), "1990-01-01")  # private tier untouched
        self.assertEqual(self.c.post(url("archive", self.mine.pk)).status_code, 302)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, "archived")
        self.assertEqual(self.c.post(url("restore", self.mine.pk)).status_code, 302)
        for other in (self.theirs, self.office, Employee.objects.get(user=self.director)):  # other school, office, own account card
            for name in ("edit", "archive", "restore"):
                self.assertEqual(self.c.get(url(name, other.pk)).status_code if name == "edit" else self.c.post(url(name, other.pk)).status_code, 404, (other, name))
            self.assertEqual(self.c.post(url("edit", other.pk), self.form()).status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.last_name, "Saidov")

    def test_detail_shows_edit_only_for_own_staff(self):
        self.assertContains(self.c.get(url("detail", self.mine.pk)), url("edit", self.mine.pk))
        own_card = Employee.objects.get(user=self.director)
        self.assertNotContains(self.c.get(url("detail", own_card.pk)), url("edit", own_card.pk))

    def test_import_is_closed_to_the_director(self):
        for name in ("import", "import_template"):
            self.assertEqual(self.c.get(url(name)).status_code, 403, name)

    def test_director_without_an_institution_cannot_maintain_staff(self):
        card = Employee.objects.get(user=self.director)
        Employee.objects.filter(pk=card.pk).update(institution=None)
        self.assertEqual(self.c.get(url("create")).status_code, 403)

    def test_hr_is_not_affected(self):
        hr = make_user("hrista", role="hr")
        c = Client()
        login_with_two_factor(c, hr)
        self.assertEqual(c.get(url("import")).status_code, 200)
        self.assertEqual(c.post(url("edit", self.theirs.pk), {"last_name": "Saidov", "first_name": "B", "middle_name": "", "department": str(self.dept.pk), "position": "", "institution": str(self.s2.pk), "status": "active"}).status_code, 302)
