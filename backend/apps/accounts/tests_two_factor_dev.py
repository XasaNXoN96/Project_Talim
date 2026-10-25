from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.testing import PASSWORD, make_user


class DevSkipTests(TestCase):
    """DEV_SKIP_TWO_FACTOR lets a local walkthrough sign in as an administrator without a phone app; it is inert unless DEBUG is on."""

    def sign_in(self):
        call_command("seed_roles", verbosity=0)
        make_user("boss", role="admin")
        c = Client()
        c.post(reverse("accounts:login"), {"username": "boss", "password": PASSWORD})
        return c

    @override_settings(DEBUG=False, DEV_SKIP_TWO_FACTOR=True)
    def test_ignored_when_debug_is_off(self):
        self.assertNotEqual(self.sign_in().get(reverse("portal:dashboard")).status_code, 200)

    @override_settings(DEBUG=True, DEV_SKIP_TWO_FACTOR=False)
    def test_the_second_factor_is_required_by_default(self):
        self.assertNotEqual(self.sign_in().get(reverse("portal:dashboard")).status_code, 200)

    @override_settings(DEBUG=True, DEV_SKIP_TWO_FACTOR=True)
    def test_skipped_only_in_debug_with_the_flag(self):
        self.assertEqual(self.sign_in().get(reverse("portal:dashboard")).status_code, 200)
