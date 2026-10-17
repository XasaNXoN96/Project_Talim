import datetime

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog

from . import access
from .models import Department, Employee, Position

User = get_user_model()
SECRET_PHONE, SECRET_BIRTH = "+998 90 000 11 22", datetime.date(1990, 5, 17)


def url(name, *args):
    return reverse(f"employees:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.root = Department.objects.create(name="Bo‘lim A")
        self.child = Department.objects.create(name="Guruh A1", parent=self.root)
        self.other = Department.objects.create(name="Bo‘lim B")
        pos = Position.objects.create(name="Metodist")
        self.target_a1 = self._emp("Aliyev", "Vali", self.child, pos)
        self.target_b = self._emp("Botirov", "Sher", self.other, pos)

        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.worker = make_user("worker", role="employee")
        self.head = make_user("head", role="employee")
        g = __import__("django.contrib.auth.models", fromlist=["Group"]).Group.objects.get(name="department_head")
        RoleAssignment.objects.create(user=self.head, role=g, scope="department", department=self.root)
        self.worker_card = self._emp("Ishchiyev", "Sodiq", self.other, pos, user=self.worker)

    def _emp(self, last, first, dept, pos, user=None):
        return Employee.objects.create(
            last_name=last, first_name=first, department=dept, position=pos, status="active", user=user,
            work_phone="+998 71 111 22 33", work_email=f"{first.lower()}@work.example.test",
            hired_at=datetime.date(2020, 1, 1), personal_phone=SECRET_PHONE, birth_date=SECRET_BIRTH,
        )

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c


class TierTests(Base):
    def test_plain_employee_sees_only_directory_of_others(self):
        self.assertEqual(access.visible_tiers(self.worker, self.target_a1), {"directory"})

    def test_own_record_is_fully_visible(self):
        self.assertEqual(access.visible_tiers(self.worker, self.worker_card), {"directory", "contacts", "private"})

    def test_department_head_sees_contacts_in_own_branch_only(self):
        self.assertEqual(access.visible_tiers(self.head, self.target_a1), {"directory", "contacts"})  # child department
        self.assertEqual(access.visible_tiers(self.head, self.target_b), {"directory"})

    def test_hr_and_admin_see_everything(self):
        for u in (self.hr, self.admin):
            self.assertEqual(access.visible_tiers(u, self.target_b), {"directory", "contacts", "private"})

    def test_sysadmin_and_anonymous_see_nothing(self):
        sys_ = make_user("sys", role="sysadmin")
        self.assertEqual(access.visible_tiers(sys_, self.target_b), set())
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(access.visible_tiers(AnonymousUser(), self.target_b), set())

    def test_inactive_user_sees_nothing(self):
        self.hr.is_active = False
        self.hr.save()
        self.assertEqual(access.visible_tiers(User.objects.get(pk=self.hr.pk), self.target_b), set())


class ReadingTests(Base):
    def test_list_shows_directory_only(self):
        body = self.client_for(self.hr).get(url("list")).content.decode()
        self.assertIn("Aliyev", body)
        self.assertNotIn("+998 71 111 22 33", body)
        self.assertNotIn(SECRET_PHONE, body)

    def test_anonymous_redirected_and_sysadmin_forbidden(self):
        self.assertEqual(Client().get(url("list")).status_code, 302)
        self.assertEqual(self.client_for(make_user("sys", role="sysadmin")).get(url("list")).status_code, 403)

    def test_card_hides_fields_above_the_viewers_tier(self):
        body = self.client_for(self.worker).get(url("detail", self.target_a1.pk)).content.decode()
        self.assertIn("Aliyev", body)
        for secret in ("+998 71 111 22 33", "vali@work.example.test", SECRET_PHONE, "17.05.1990"):
            self.assertNotIn(secret, body)

    def test_head_sees_contacts_not_private(self):
        body = self.client_for(self.head).get(url("detail", self.target_a1.pk)).content.decode()
        self.assertIn("+998 71 111 22 33", body)
        self.assertNotIn(SECRET_PHONE, body)
        self.assertNotIn("17.05.1990", body)

    def test_hr_sees_private_and_reading_is_audited(self):
        body = self.client_for(self.hr).get(url("detail", self.target_a1.pk)).content.decode()
        self.assertIn(SECRET_PHONE, body)
        entry = AuditLog.objects.get(action=AuditLog.Action.EMPLOYEE_VIEWED)
        self.assertEqual((entry.user, entry.object_id), (self.hr, str(self.target_a1.pk)))
        self.assertEqual(entry.meta["tiers"], ["contacts", "private"])
        self.assertNotIn(SECRET_PHONE, str(entry.meta))

    def test_directory_only_reading_is_not_audited(self):
        self.client_for(self.worker).get(url("detail", self.target_a1.pk))
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_VIEWED).exists())

    def test_reading_own_card_is_not_audited(self):
        body = self.client_for(self.worker).get(url("detail", self.worker_card.pk)).content.decode()
        self.assertIn(SECRET_PHONE, body)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_VIEWED).exists())

    def test_me_redirects_to_own_card(self):
        self.assertRedirects(self.client_for(self.worker).get(url("me")), url("detail", self.worker_card.pk), fetch_redirect_response=False)

    def test_me_without_card_goes_to_list(self):
        self.assertRedirects(self.client_for(self.head).get(url("me")), url("list"), fetch_redirect_response=False)

    def test_archived_hidden_from_ordinary_users_but_not_from_hr(self):
        self.target_b.status = "archived"
        self.target_b.save()
        self.assertNotContains(self.client_for(self.worker).get(url("list")), "Botirov")
        self.assertEqual(self.client_for(self.worker).get(url("detail", self.target_b.pk)).status_code, 403)
        self.assertContains(self.client_for(self.hr).get(url("list")), "Botirov")

    def test_filters(self):
        c = self.client_for(self.hr)
        self.assertContains(c.get(url("list"), {"department": self.root.pk}), "Aliyev")  # includes sub-department
        self.assertNotContains(c.get(url("list"), {"department": self.root.pk}), "Botirov")
        self.assertContains(c.get(url("list"), {"q": "botir"}), "Botirov")
        self.assertEqual(c.get(url("list"), {"department": "not-a-uuid"}).status_code, 200)


class WritingTests(Base):
    def payload(self, **kw):
        d = {"last_name": "Yangiyev", "first_name": "Anvar", "department": self.root.pk, "status": "new"}
        d.update(kw)
        return d

    def test_ordinary_users_and_department_heads_cannot_write(self):
        for u in (self.worker, self.head):
            c = self.client_for(u)
            self.assertEqual(c.get(url("create")).status_code, 403)
            self.assertEqual(c.post(url("create"), self.payload()).status_code, 403)
            self.assertEqual(c.get(url("edit", self.target_b.pk)).status_code, 403)
            self.assertEqual(c.post(url("archive", self.target_b.pk)).status_code, 403)
        self.assertEqual(Employee.objects.count(), 3)

    def test_hr_creates_and_audits_field_names_without_values(self):
        r = self.client_for(self.hr).post(url("create"), self.payload(personal_phone=SECRET_PHONE))
        e = Employee.objects.get(last_name="Yangiyev")
        self.assertRedirects(r, url("detail", e.pk), fetch_redirect_response=False)
        entry = AuditLog.objects.get(action=AuditLog.Action.EMPLOYEE_CREATED)
        self.assertIn("personal_phone", entry.meta["fields"])
        self.assertNotIn(SECRET_PHONE, str(entry.meta))

    def test_edit_records_only_changed_fields(self):
        data = self.payload(last_name="Aliyev", first_name="Vali", department=self.child.pk, status="active", position=self.target_a1.position_id,
                            work_phone="+998 71 999 99 99", work_email=self.target_a1.work_email, hired_at="2020-01-01",
                            personal_phone=SECRET_PHONE, birth_date="1990-05-17")
        self.client_for(self.hr).post(url("edit", self.target_a1.pk), data)
        self.target_a1.refresh_from_db()
        self.assertEqual(self.target_a1.work_phone, "+998 71 999 99 99")
        entry = AuditLog.objects.get(action=AuditLog.Action.EMPLOYEE_UPDATED)
        self.assertEqual(entry.meta["fields"], ["work_phone"])

    def test_user_link_offered_only_to_account_managers(self):
        hr_form = self.client_for(self.hr).get(url("create")).content.decode()
        admin_form = self.client_for(self.admin).get(url("create")).content.decode()
        self.assertNotIn('name="user"', hr_form)
        self.assertIn('name="user"', admin_form)
        # forging the field as HR must not link anything
        self.client_for(self.hr).post(url("create"), self.payload(user=self.hr.pk))
        self.assertIsNone(Employee.objects.get(last_name="Yangiyev").user)

    def test_one_account_cannot_belong_to_two_employees(self):
        r = self.client_for(self.admin).post(url("create"), self.payload(user=self.worker.pk))
        self.assertContains(r, "boshqa xodimga biriktirilgan")

    def test_archive_and_restore_with_audit(self):
        c = self.client_for(self.hr)
        c.post(url("archive", self.target_b.pk))
        self.target_b.refresh_from_db()
        self.assertEqual(self.target_b.status, "archived")
        c.post(url("restore", self.target_b.pk))
        self.target_b.refresh_from_db()
        self.assertEqual(self.target_b.status, "active")
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_ARCHIVED).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.EMPLOYEE_RESTORED).exists())

    def test_archive_requires_post(self):
        self.assertEqual(self.client_for(self.hr).get(url("archive", self.target_b.pk)).status_code, 405)
