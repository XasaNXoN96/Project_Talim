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
        body = self.client.get(reverse("portal:preview", args=["media"])).content.decode()
        for slug in PREVIEW_SECTIONS:
            self.assertIn(reverse("portal:preview", args=[slug]), body)
        self.assertRegex(body, r'href="/portal/maket/media/"[^>]*class="active"')


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

