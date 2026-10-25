"""Design mock-up sections inside the portal: sample data only, signed-in users only, clearly marked, nothing stored."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user

from .views import PREVIEW_SECTIONS


class PreviewSectionTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for slug in PREVIEW_SECTIONS:
            response = self.client.get(reverse("portal:preview", args=[slug]))
            self.assertEqual(response.status_code, 302, slug)
            self.assertIn("/accounts/login/", response["Location"])

    def test_signed_in_users_see_each_section_marked_as_a_mock_up_with_the_sample_renderers(self):
        user = make_user("viewer", role="employee")
        login_with_two_factor(self.client, user)
        for slug in PREVIEW_SECTIONS:
            response = self.client.get(reverse("portal:preview", args=[slug]))
            self.assertEqual(response.status_code, 200, slug)
            body = response.content.decode()
            self.assertIn("Dizayn maketi.", body, slug)
            self.assertIn("assets/js/data.js", body)
            self.assertNotRegex(body, r'href="[\w-]+\.html')

    def test_unknown_sections_are_not_found(self):
        user = make_user("viewer2", role="employee")
        login_with_two_factor(self.client, user)
        self.assertEqual(self.client.get("/portal/maket/unknown/").status_code, 404)

    def test_the_menu_lists_the_sections_and_marks_the_current_one(self):
        user = make_user("viewer3", role="employee")
        login_with_two_factor(self.client, user)
        body = self.client.get(reverse("portal:preview", args=["sertifikatlar"])).content.decode()
        for slug in PREVIEW_SECTIONS:
            if slug == "chat":  # a real section for everybody with the chat right (an employee has it)
                self.assertIn(reverse("chat:inbox"), body)
                continue
            if slug == "media":  # the gallery is real for everybody who may view it (an employee may)
                self.assertIn(reverse("gallery:list"), body)
                continue
            self.assertIn(reverse("portal:preview", args=[slug]), body)
        self.assertRegex(body, r'href="/portal/maket/sertifikatlar/"[^>]*class="active"')


class DashboardTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def page(self, user):
        login_with_two_factor(self.client, user)
        response = self.client.get(reverse("portal:dashboard"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_old_placeholder_text_is_gone_and_the_mock_up_blocks_are_there(self):
        body = self.page(make_user("boss", role="admin"))
        self.assertNotIn("Ishlab chiqish bosqichi.", body)
        for marker in ('class="banner"', 'class="stat-grid"', "Mening topshiriqlarim", "Oxirgi bildirishnomalar", "So‘nggi yangiliklar"):
            self.assertIn(marker, body, marker)

    def test_numbers_and_lists_come_from_the_database(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.content.tests import news
        from apps.tasks.models import Task

        user = make_user("boss2", role="admin")
        news("Bosh sahifa yangiligi", slug="bosh-sahifa-yangiligi")
        task = Task.objects.create(title="Hisobot tayyorlash", created_by=user, due_date=timezone.localdate() - timedelta(days=1))
        task.assignees.add(user)
        body = self.page(user)
        self.assertIn("Bosh sahifa yangiligi", body)
        self.assertIn("Hisobot tayyorlash", body)
        self.assertIn("Muddati o‘tgan", body)

    def test_a_user_without_rights_sees_no_blocks_he_may_not_open(self):
        body = self.page(make_user("nobody"))
        for hidden in ("Mening topshiriqlarim", "Oxirgi bildirishnomalar", 'class="stat-grid"'):
            self.assertNotIn(hidden, body, hidden)
        self.assertIn('class="banner"', body)


class AdminHubAndMenuTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def get(self, user, name="portal:admin_hub"):
        login_with_two_factor(self.client, user)
        return self.client.get(reverse(name))

    def test_anonymous_goes_to_login_and_users_without_management_rights_get_403(self):
        self.assertEqual(self.client.get(reverse("portal:admin_hub")).status_code, 302)
        self.assertEqual(self.get(make_user("plain", role="employee")).status_code, 403)

    def test_an_administrator_sees_tiles_only_for_pages_the_role_may_open(self):
        response = self.get(make_user("boss3", role="admin"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for url in (reverse("employees:list"), reverse("news_admin:list"), reverse("tasks:list"), reverse("documents:list"), reverse("reports:index")):
            self.assertIn(f'href="{url}"', body, url)
        self.assertNotIn("Django admin", body)  # only for superusers

    def test_a_superuser_also_gets_the_technical_admin_tile(self):
        user = make_user("root1", is_superuser=True, is_staff=True)
        self.assertIn("Django admin", self.get(user).content.decode())

    def test_the_menu_follows_the_design_order_for_an_administrator(self):
        body = self.get(make_user("boss4", role="admin"), "portal:dashboard").content.decode()
        order = ["portal:dashboard", "news_admin:list", "employees:list"]
        positions = [body.index(f'href="{reverse(n)}"') for n in order]
        self.assertEqual(positions, sorted(positions))
        sidebar = body[body.index('class="sb-nav"'):body.index("</nav>", body.index('class="sb-nav"'))]
        self.assertIn(f'href="{reverse("gallery:list")}"', sidebar)  # Media is real now
        self.assertIn(f'href="{reverse("chat:inbox")}"', sidebar)  # Chat is real now
        # Yutuqlar and Sertifikatlar are real now (the achievements section); the mock pages stay for people without access to it
        self.assertIn(f'href="{reverse("achievements:list")}"', sidebar)
        self.assertIn(f'href="{reverse("achievements:list")}?kind=certificate"', sidebar)
        for name in ("tasks:list", "documents:list", "employees:structure", "notifications:list", "reports:index", "portal:admin_hub"):
            self.assertIn(f'href="{reverse(name)}"', sidebar, name)
        self.assertGreaterEqual(sidebar.count("<a "), 15)

    def test_employee_list_has_the_status_tabs_and_avatars(self):
        user = make_user("hr1", role="hr")
        login_with_two_factor(self.client, user)
        body = self.client.get(reverse("employees:list")).content.decode()
        for tab in ("Barcha xodimlar", "Faol xodimlar", "Yangi xodimlar"):
            self.assertIn(tab, body)
        self.assertIn("?status=active", body)

