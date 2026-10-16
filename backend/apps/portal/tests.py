from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.audit.models import AuditLog, ImmutableAuditError

User = get_user_model()
PASSWORD = "Namuna-Parol-12345"


def user_with_role(name, role=None, **extra):
    user = User.objects.create_user(name, f"{name}@example.test", PASSWORD, **extra)
    if role:
        RoleAssignment.objects.create(user=user, role=Group.objects.get(name=role), scope="all")
    return User.objects.get(pk=user.pk)


class DashboardAccessTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("portal:dashboard"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('portal:dashboard')}", fetch_redirect_response=False)

    def test_signed_in_user_sees_dashboard(self):
        self.client.force_login(user_with_role("erin", "employee"))
        response = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "erin@example.test")
        self.assertContains(response, "employee")
        self.assertContains(response, "Ishlab chiqish bosqichi")  # honest skeleton notice

    def test_dashboard_has_logout_form_with_csrf(self):
        self.client.force_login(user_with_role("erin"))
        html = self.client.get(reverse("portal:dashboard")).content.decode()
        self.assertIn(f'action="{reverse("accounts:logout")}"', html)
        self.assertIn("csrfmiddlewaretoken", html)


class AuditPageAuthorizationTests(TestCase):
    """Permissions are enforced on the server, regardless of what the menu shows or of is_staff."""

    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.url = reverse("portal:audit")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_user_without_role_gets_403(self):
        self.client.force_login(user_with_role("frank"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_employee_role_gets_403(self):
        self.client.force_login(user_with_role("gina", "employee"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_is_staff_alone_does_not_grant_access(self):
        self.client.force_login(user_with_role("hank", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_hr_role_gets_403(self):
        self.client.force_login(user_with_role("ivy", "hr"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_admin_and_sysadmin_roles_can_view(self):
        for name, role in (("jack", "admin"), ("kate", "sysadmin")):
            self.client.force_login(user_with_role(name, role))
            self.assertEqual(self.client.get(self.url).status_code, 200, msg=role)

    def test_page_lists_real_entries(self):
        admin = user_with_role("leo", "admin")
        self.client.post(reverse("accounts:login"), {"username": "leo", "password": PASSWORD})
        response = self.client.get(self.url)
        self.assertContains(response, "Tizimga kirish")
        self.assertContains(response, "leo")

    def test_menu_link_hidden_without_permission(self):
        self.client.force_login(user_with_role("mia", "employee"))
        self.assertNotContains(self.client.get(reverse("portal:dashboard")), self.url)
        self.client.force_login(user_with_role("ned", "admin"))
        self.assertContains(self.client.get(reverse("portal:dashboard")), self.url)

    def test_revoked_role_loses_access_immediately(self):
        user = user_with_role("oli", "admin")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        RoleAssignment.objects.get(user=user).delete()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_audit_page_cannot_modify_data(self):
        self.client.force_login(user_with_role("pat", "admin"))
        self.assertEqual(self.client.post(self.url).status_code, 405)


class AdminSiteTests(TestCase):
    def test_non_staff_cannot_open_admin(self):
        from django.conf import settings

        self.client.force_login(user_with_role("quinn"))
        response = self.client.get("/" + settings.ADMIN_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
