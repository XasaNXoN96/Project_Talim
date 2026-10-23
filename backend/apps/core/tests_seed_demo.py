"""seed_demo makes accounts with a KNOWN password: it must work for the hand-made walkthrough and must be impossible to run on a server."""
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor
from apps.achievements.models import Achievement
from apps.gallery.models import MediaItem
from apps.organization.models import Institution
from apps.tasks.models import Task

User = get_user_model()
ROLES = {"demo_admin": "admin", "demo_sysadmin": "sysadmin", "demo_content": "content_manager", "demo_hr": "hr", "demo_head": "department_head",
         "demo_employee": "employee", "demo_director1": "school_director", "demo_director2": "school_director"}


class SeedDemoTests(TestCase):
    def run_it(self):
        with override_settings(DEBUG=True):
            call_command("seed_demo", "--yes", verbosity=0)

    def test_it_refuses_on_a_server_and_without_confirmation(self):
        with override_settings(DEBUG=False), self.assertRaisesMessage(CommandError, "DEBUG is off"):
            call_command("seed_demo", "--yes", verbosity=0)
        with override_settings(DEBUG=True), self.assertRaisesMessage(CommandError, "--yes"):
            call_command("seed_demo", verbosity=0)
        self.assertFalse(User.objects.filter(username__startswith="demo_").exists())

    def test_every_documented_account_exists_with_its_role_and_the_documented_password(self):
        from apps.core.management.commands.seed_demo import PASSWORD

        self.run_it()
        self.assertEqual(PASSWORD, "Demo-Parol-2026!")  # docs/WALKTHROUGH.md names exactly this password
        for username, role in ROLES.items():
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(PASSWORD), username)
            self.assertEqual(list(user.groups.values_list("name", flat=True)), [role], username)
            self.assertTrue(user.email.endswith("@example.test"))

    def test_it_is_idempotent_and_makes_the_data_the_walkthrough_describes(self):
        self.run_it()
        counts = (User.objects.count(), Institution.objects.count(), Task.objects.count(), Achievement.objects.count(), MediaItem.objects.count())
        self.run_it()
        self.assertEqual(counts, (User.objects.count(), Institution.objects.count(), Task.objects.count(), Achievement.objects.count(), MediaItem.objects.count()))
        self.assertEqual(Institution.objects.filter(name__startswith="DEMO").count(), 3)
        self.assertEqual(sorted(Achievement.objects.values_list("status", flat=True)), ["draft", "published", "submitted"])
        self.assertEqual(sorted(MediaItem.objects.values_list("status", flat=True)), ["draft", "published", "published"])
        self.assertTrue(any(t.is_overdue for t in Task.objects.all()))  # the walkthrough relies on one overdue task

    def test_the_demo_world_behaves_as_the_walkthrough_says(self):
        self.run_it()
        director = Client()
        login_with_two_factor(director, User.objects.get(username="demo_director1"))
        listing = director.get(reverse("employees:list")).content.decode()
        self.assertIn("Namunaviy", listing)
        self.assertNotIn("Namuna Administrator", listing)  # only his own school
        for name in ("employees:structure", "users:list", "reports:schools", "portal:audit", "portal:admin_hub", "chat:archive"):
            self.assertEqual(director.get(reverse(name)).status_code, 403, name)
        guest = Client()
        self.assertEqual(guest.get(reverse("gallery_public:list")).content.decode().count("data-lbx"), 2)
        page = guest.get(reverse("achievements_public:list")).content.decode()
        self.assertIn("Tuman olimpiadasi", page)
        self.assertNotIn("Respublika tanlovi", page)
        self.assertNotIn("Qoralama yutuq", page)
