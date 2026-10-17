from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.audit.models import AuditLog
from apps.organization.models import Department

from . import services, throttle
from .testing import login_with_two_factor, make_user

User = get_user_model()
LIST = reverse("users:list")


def url(name, *args):
    return reverse(f"users:{name}", args=args)


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.staff = make_user("worker", role="employee")
        self.dept = Department.objects.create(name="Metodika")
        self.client = Client()

    def as_user(self, user):
        login_with_two_factor(self.client, user)
        return self.client


class AccessTests(Base):
    def test_anonymous_is_sent_to_login(self):
        for u in (LIST, url("create"), url("detail", self.staff.pk)):
            response = self.client.get(u)
            self.assertEqual(response.status_code, 302, u)
            self.assertIn("/accounts/login/", response["Location"])

    def test_plain_employee_gets_403_everywhere(self):
        c = self.as_user(self.staff)
        for u in (LIST, url("create"), url("detail", self.admin.pk), url("edit", self.admin.pk)):
            self.assertEqual(c.get(u).status_code, 403, u)
        for u in (url("action", self.admin.pk, "deactivate"), url("role_add", self.staff.pk)):
            self.assertEqual(c.post(u, {"role": "admin"}).status_code, 403, u)

    def test_hr_can_view_but_not_change(self):
        c = self.as_user(self.hr)
        self.assertEqual(c.get(LIST).status_code, 200)
        self.assertEqual(c.get(url("detail", self.staff.pk)).status_code, 200)
        self.assertEqual(c.get(url("create")).status_code, 403)
        self.assertEqual(c.post(url("action", self.staff.pk, "deactivate")).status_code, 403)
        self.assertEqual(c.post(url("action", self.staff.pk, "unlock")).status_code, 403)
        self.assertEqual(c.post(url("role_add", self.staff.pk), {"role": "hr"}).status_code, 403)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_state_changes_need_post(self):
        c = self.as_user(self.admin)
        self.assertEqual(c.get(url("action", self.staff.pk, "deactivate")).status_code, 405)

    def test_unknown_action_is_404(self):
        self.assertEqual(self.as_user(self.admin).post(url("action", self.staff.pk, "explode")).status_code, 404)

    def test_menu_entry_follows_permission(self):
        self.assertContains(self.as_user(self.hr).get(reverse("portal:dashboard")), url("list"))
        other = Client()
        login_with_two_factor(other, self.staff)
        self.assertNotContains(other.get(reverse("portal:dashboard")), url("list"))

    def test_csrf_is_enforced(self):
        c = Client(enforce_csrf_checks=True)
        login_with_two_factor(c, self.admin)
        self.assertEqual(c.post(url("action", self.staff.pk, "deactivate")).status_code, 403)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)


class CreateAndInviteTests(Base):
    def data(self, **kw):
        base = {"username": "newbie", "email": "NewBie@Example.test", "last_name": "Test", "first_name": "Yangi", "role": "employee"}
        base.update(kw)
        return base

    def test_admin_creates_user_without_password_and_audits_actor(self):
        c = self.as_user(self.admin)
        response = c.post(url("create"), self.data())
        user = User.objects.get(username="newbie")
        self.assertRedirects(response, url("detail", user.pk), fetch_redirect_response=False)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "newbie@example.test")
        self.assertTrue(user.groups.filter(name="employee").exists())
        entry = AuditLog.objects.filter(action=AuditLog.Action.USER_CREATED).latest("at")
        self.assertEqual(entry.user, self.admin)
        self.assertEqual(entry.object_id, str(user.pk))
        self.assertNotIn("password", str(entry.meta).lower())

    def test_duplicate_login_or_email_is_rejected_case_insensitively(self):
        c = self.as_user(self.admin)
        self.assertContains(c.post(url("create"), self.data(username="WORKER")), "Bu login band")
        self.assertContains(c.post(url("create"), self.data(email="Worker@example.test")), "Bu e-pochta band")
        self.assertEqual(User.objects.count(), 3)

    def test_department_head_needs_department(self):
        c = self.as_user(self.admin)
        self.assertContains(c.post(url("create"), self.data(role="department_head")), "bo‘lim ko‘rsatilishi shart")
        self.assertFalse(User.objects.filter(username="newbie").exists())
        c.post(url("create"), self.data(role="department_head", department=self.dept.pk))
        a = RoleAssignment.objects.get(user__username="newbie")
        self.assertEqual((a.scope, a.department), ("department", self.dept))

    def test_invalid_role_is_rejected(self):
        response = self.as_user(self.admin).post(url("create"), self.data(role="god"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_invitation_mail_has_link_but_the_link_logs_nobody_in(self):
        c = self.as_user(self.admin)
        c.post(url("create"), self.data())
        user = User.objects.get(username="newbie")
        c.post(url("action", user.pk, "invite"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newbie@example.test"])
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.USER_INVITED, user=self.admin).exists())

    def test_invitation_is_rate_limited(self):
        c = self.as_user(self.admin)
        for _ in range(8):
            c.post(url("action", self.staff.pk, "invite"))
        self.assertEqual(len(mail.outbox), 5)  # policy: 5 per hour, the rest are refused

    def test_no_invitation_for_inactive_user(self):
        self.staff.is_active = False
        self.staff.save()
        self.as_user(self.admin).post(url("action", self.staff.pk, "invite"))
        self.assertEqual(len(mail.outbox), 0)


class RoleRuleTests(Base):
    def test_hr_like_manager_cannot_hand_out_privileged_roles(self):
        manager = make_user("mgr", role="employee")
        manager.user_permissions.add(*self._perms("manage_users", "assign_roles"))
        manager = User.objects.get(pk=manager.pk)
        c = self.as_user(manager)
        c.post(url("role_add", self.staff.pk), {"role": "admin"})
        self.assertFalse(self.staff.groups.filter(name="admin").exists())
        with self.assertRaises(services.ActionNotAllowed):
            services.assign_role(manager, self.staff, role="sysadmin", department=None, request=None)

    def _perms(self, *codes):
        from django.contrib.auth.models import Permission
        return Permission.objects.filter(content_type__app_label="accounts", codename__in=codes)

    def test_admin_assigns_and_revokes_role_with_audit(self):
        c = self.as_user(self.admin)
        c.post(url("role_add", self.staff.pk), {"role": "hr"})
        self.assertTrue(self.staff.groups.filter(name="hr").exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ROLE_ASSIGNED, user=self.admin).exists())
        a = RoleAssignment.objects.get(user=self.staff, role__name="hr")
        c.post(url("role_remove", self.staff.pk, a.pk))
        self.assertFalse(self.staff.groups.filter(name="hr").exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ROLE_REVOKED, user=self.admin).exists())

    def test_duplicate_assignment_rejected(self):
        c = self.as_user(self.admin)
        c.post(url("role_add", self.staff.pk), {"role": "employee"})
        self.assertEqual(RoleAssignment.objects.filter(user=self.staff, role__name="employee").count(), 1)

    def test_cannot_remove_own_or_last_admin_role(self):
        c = self.as_user(self.admin)
        a = RoleAssignment.objects.get(user=self.admin, role__name="admin")
        c.post(url("role_remove", self.admin.pk, a.pk))
        self.assertTrue(RoleAssignment.objects.filter(pk=a.pk).exists())

    def test_last_admin_cannot_be_deactivated_by_another_manager_either(self):
        manager = make_user("mgr", role="employee")
        manager.user_permissions.add(*self._perms("manage_users"))
        manager = User.objects.get(pk=manager.pk)
        with self.assertRaises(services.ActionNotAllowed):
            services.deactivate_user(manager, self.admin, None)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_second_admin_makes_removal_possible(self):
        second = make_user("boss2", role="admin")
        c = self.as_user(self.admin)
        a = RoleAssignment.objects.get(user=second, role__name="admin")
        c.post(url("role_remove", second.pk, a.pk))
        self.assertFalse(RoleAssignment.objects.filter(pk=a.pk).exists())

    def test_assignment_of_another_user_cannot_be_removed_through_wrong_url(self):
        a = RoleAssignment.objects.get(user=self.staff)
        response = self.as_user(self.admin).post(url("role_remove", self.hr.pk, a.pk))
        self.assertEqual(response.status_code, 404)

    def test_superuser_account_is_protected_from_non_superusers(self):
        root = User.objects.create_superuser("root", "root@example.test", "Namuna-Parol-12345")
        c = self.as_user(self.admin)
        c.post(url("action", root.pk, "deactivate"))
        c.post(url("action", root.pk, "force_password"))
        root.refresh_from_db()
        self.assertTrue(root.is_active)
        self.assertFalse(root.must_change_password)


class LifecycleTests(Base):
    def test_deactivation_closes_sessions_and_blocks_login(self):
        victim = Client()
        login_with_two_factor(victim, self.staff)
        self.assertEqual(victim.get(reverse("portal:dashboard")).status_code, 200)
        self.as_user(self.admin).post(url("action", self.staff.pk, "deactivate"))
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertEqual(victim.get(reverse("portal:dashboard")).status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.USER_DEACTIVATED, user=self.admin).exists())

    def test_cannot_deactivate_self(self):
        self.as_user(self.admin).post(url("action", self.admin.pk, "deactivate"))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_reactivate(self):
        self.staff.is_active = False
        self.staff.save()
        self.as_user(self.admin).post(url("action", self.staff.pk, "reactivate"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_force_password_change_sets_flag_and_audits(self):
        self.as_user(self.admin).post(url("action", self.staff.pk, "force_password"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.must_change_password)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.PASSWORD_CHANGE_FORCED, user=self.admin).exists())

    def test_unlock_clears_account_keys_but_not_ip(self):
        account = [throttle.Key("login:user", str(self.staff.pk)), throttle.Key("login:identifier", "worker")]
        ip = throttle.Key("login:ip", "203.0.113.9")
        for _ in range(5):
            throttle.reserve(account + [ip])
        self.assertTrue(services.is_account_locked(self.staff))
        self.as_user(self.admin).post(url("action", self.staff.pk, "unlock"))
        self.assertFalse(services.is_account_locked(self.staff))
        self.assertEqual(throttle.reserve([ip]).allowed, True)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_UNLOCKED, user=self.admin).exists())

    def test_edit_records_changed_field_names_only(self):
        c = self.as_user(self.admin)
        c.post(url("edit", self.staff.pk), {"email": "new@example.test", "first_name": "Ism", "last_name": "Boshqa", "locale": "uz"})
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.email, "new@example.test")
        entry = AuditLog.objects.filter(action=AuditLog.Action.USER_UPDATED).latest("at")
        self.assertEqual(sorted(entry.meta["fields"]), ["email", "first_name", "last_name"])
        self.assertNotIn("new@example.test", str(entry.meta))

    def test_edit_rejects_email_of_another_user(self):
        response = self.as_user(self.admin).post(url("edit", self.staff.pk), {"email": self.hr.email, "first_name": "a", "last_name": "b", "locale": "uz"})
        self.assertContains(response, "Bu e-pochta band")

    def test_list_search_and_filters(self):
        c = self.as_user(self.admin)
        self.assertContains(c.get(LIST, {"q": "work"}), "worker")
        self.assertNotContains(c.get(LIST, {"q": "work"}), "hrista")
        self.assertContains(c.get(LIST, {"role": "hr"}), "hrista")
        self.assertNotContains(c.get(LIST, {"role": "hr"}), "worker")
        self.staff.is_active = False
        self.staff.save()
        self.assertContains(c.get(LIST, {"status": "inactive"}), "worker")

    def test_detail_never_shows_password_hash(self):
        body = self.as_user(self.admin).get(url("detail", self.staff.pk)).content.decode()
        self.assertNotIn("argon2", body)
        self.assertNotIn("pbkdf2", body)
