import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog

from .testing import PASSWORD, login_with_two_factor, make_user
from .tests_twofactor import code_at, enrol, password_step, pending_client, signed_in

User = get_user_model()
NEW = "Yangi-Kuchli-Parol-2026!"
CHANGE = reverse("accounts:password_change")


class MustChangePasswordTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.user = make_user("alice", role="employee", must_change_password=True)
        self.client = Client()
        password_step(self.client, "alice")

    def test_every_page_redirects_to_the_change_form(self):
        for url in (reverse("portal:dashboard"), reverse("accounts:security"), reverse("content:home"), reverse("content:news_list"), "/admin/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, msg=url)
            self.assertEqual(response["Location"], CHANGE, msg=url)

    def test_post_requests_are_blocked_too(self):
        self.assertEqual(self.client.post(reverse("accounts:two_factor_setup"), {}).status_code, 302)

    def test_the_change_form_logout_and_health_stay_reachable(self):
        self.assertEqual(self.client.get(CHANGE).status_code, 200)
        self.assertEqual(self.client.get(reverse("healthz")).status_code, 200)
        self.assertEqual(self.client.post(reverse("accounts:logout")).status_code, 302)
        self.assertFalse(signed_in(self.client))

    def test_changing_the_password_releases_the_user(self):
        response = self.client.post(CHANGE, {"old_password": PASSWORD, "new_password1": NEW, "new_password2": NEW})
        self.assertRedirects(response, reverse("accounts:password_change_done"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertEqual(self.client.get(reverse("portal:dashboard")).status_code, 200)

    def test_the_new_password_must_differ_from_the_current_one(self):
        response = self.client.post(CHANGE, {"old_password": PASSWORD, "new_password1": PASSWORD, "new_password2": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "farq qilishi kerak")
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_a_password_reset_also_clears_the_flag(self):
        Client().post(reverse("accounts:password_reset"), {"email": "alice@example.test"})
        link = re.search(r"(/accounts/reset/\S+/\S+/)", mail.outbox[0].body).group(1)
        fresh = Client()
        target = fresh.get(link, follow=True).redirect_chain[-1][0]
        fresh.post(target, {"new_password1": NEW, "new_password2": NEW})
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)

    def test_unflagged_users_are_unaffected(self):
        make_user("bob", role="employee")
        other = Client()
        password_step(other, "bob")
        self.assertEqual(other.get(reverse("portal:dashboard")).status_code, 200)

    def test_flag_is_enforced_for_a_signed_in_session_as_soon_as_it_is_set(self):
        make_user("carol", role="employee")
        client = Client()
        password_step(client, "carol")
        self.assertEqual(client.get(reverse("portal:dashboard")).status_code, 200)
        User.objects.filter(username="carol").update(must_change_password=True)
        self.assertEqual(client.get(reverse("portal:dashboard"))["Location"], CHANGE)


class TwoFactorThenPasswordChangeTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def test_an_administrator_first_proves_identity_then_changes_the_password(self):
        boss = make_user("boss", role="admin", must_change_password=True)
        secret, _ = enrol(boss)
        client = pending_client("boss")
        self.assertEqual(client.get(CHANGE).status_code, 302)  # not signed in yet: the second factor comes first
        self.assertFalse(signed_in(client))
        client.post(reverse("accounts:two_factor_verify"), {"code": code_at(secret)})
        self.assertTrue(signed_in(client))
        self.assertEqual(client.get(reverse("portal:audit"))["Location"], CHANGE)  # now forced to change it
        client.post(CHANGE, {"old_password": PASSWORD, "new_password1": NEW, "new_password2": NEW})
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 200)


class SecurityNoticeTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.user = make_user("alice", role="employee")
        self.client = Client()
        login = self.client.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD}, REMOTE_ADDR="198.51.100.9")
        self.assertEqual(login.status_code, 302)
        mail.outbox.clear()

    def assert_single_notice(self, subject_part):
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["alice@example.test"])
        self.assertIn(subject_part, message.subject)
        for secret in (PASSWORD, NEW):
            self.assertNotIn(secret, message.body)
        self.assertNotRegex(message.body, r"https?://")  # a notice never carries a link
        return message

    def test_password_change(self):
        self.client.post(CHANGE, {"old_password": PASSWORD, "new_password1": NEW, "new_password2": NEW}, REMOTE_ADDR="198.51.100.9")
        message = self.assert_single_notice("Parolingiz almashtirildi")
        self.assertIn("198.51.100.9", message.body)

    def test_password_reset(self):
        Client().post(reverse("accounts:password_reset"), {"email": "alice@example.test"})
        link = re.search(r"(/accounts/reset/\S+/\S+/)", mail.outbox[0].body).group(1)
        mail.outbox.clear()
        fresh = Client()
        target = fresh.get(link, follow=True).redirect_chain[-1][0]
        fresh.post(target, {"new_password1": NEW, "new_password2": NEW})
        self.assert_single_notice("Parolingiz tiklandi")

    def test_two_factor_enabled_regenerated_disabled(self):
        from .tests_twofactor import secret_of

        self.client.get(reverse("accounts:two_factor_setup"))
        self.client.post(reverse("accounts:two_factor_setup"), {"code": code_at(secret_of(self.user))})
        message = self.assert_single_notice("Ikki bosqichli himoya yoqildi")
        self.assertNotRegex(message.body, r"[A-Z2-9]{5}-[A-Z2-9]{5}")  # no backup codes in the mail
        mail.outbox.clear()
        self.client.post(reverse("accounts:backup_codes_regenerate"), {"password": PASSWORD})
        self.assert_single_notice("Zaxira kodlar yangilandi")
        mail.outbox.clear()
        self.client.post(reverse("accounts:two_factor_disable"), {"password": PASSWORD})
        self.assert_single_notice("Ikki bosqichli himoya o‘chirildi")

    def test_reset_command_notifies_the_user(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        mail.outbox.clear()
        call_command("reset_2fa", "boss", "--yes")
        self.assertEqual(mail.outbox[0].to, ["boss@example.test"])
        self.assertIn("administrator", mail.outbox[0].subject.lower() + mail.outbox[0].body.lower())

    def test_failed_delivery_never_breaks_the_action_and_logs_no_address(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("550 rejected alice@example.test")):
            with self.assertLogs("apps.accounts.notifications", level="ERROR") as logs:
                response = self.client.post(CHANGE, {"old_password": PASSWORD, "new_password1": NEW, "new_password2": NEW})
        self.assertEqual(response.status_code, 302)  # the change itself succeeded
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertNotIn("alice@example.test", "\n".join(logs.output))

    def test_a_failed_attempt_sends_nothing(self):
        self.client.post(CHANGE, {"old_password": "Noto-g-ri-parol-0000", "new_password1": NEW, "new_password2": NEW})
        self.assertEqual(len(mail.outbox), 0)
