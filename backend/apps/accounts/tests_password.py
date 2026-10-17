import logging
import re
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog

from .testing import PASSWORD, frozen_throttle_clock, make_user

User = get_user_model()
NEW_PASSWORD = "Yangi-Kuchli-Parol-2026!"
WRONG = "Noto-g-ri-parol-0000"
CHANGE = reverse("accounts:password_change")
RESET = reverse("accounts:password_reset")


def login(client, username="alice", password=PASSWORD):
    return client.post(reverse("accounts:login"), {"username": username, "password": password})


def signed_in(client):
    return "_auth_user_id" in client.session


def reset_link_from(message):
    match = re.search(r"https?://[^/\s]+(/accounts/reset/[^/\s]+/[^/\s]+/)", message.body)
    return match.group(1) if match else None


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        login(self.client)

    def change(self, old=PASSWORD, new=NEW_PASSWORD, confirm=None):
        return self.client.post(CHANGE, {"old_password": old, "new_password1": new, "new_password2": confirm or new})

    def test_requires_login(self):
        response = Client().get(CHANGE)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_wrong_current_password_is_rejected(self):
        response = self.change(old=WRONG)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_change_succeeds_and_keeps_this_session(self):
        response = self.change()
        self.assertRedirects(response, reverse("accounts:password_change_done"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertEqual(self.client.get(reverse("portal:dashboard")).status_code, 200)  # still signed in here

    def test_other_sessions_are_closed(self):
        other = Client()
        login(other)
        self.assertEqual(other.get(reverse("portal:dashboard")).status_code, 200)
        other_key = other.session.session_key
        self.change()
        # Checked BEFORE the other client makes another request (Django would also drop an invalid session on use):
        self.assertFalse(Session.objects.filter(session_key=other_key).exists())  # the row is gone, not merely invalid
        self.assertTrue(Session.objects.filter(session_key=self.client.session.session_key).exists())  # this one stays
        self.assertEqual(other.get(reverse("portal:dashboard")).status_code, 302)  # signed out everywhere else

    def test_weak_new_password_is_rejected(self):
        for weak in ("short1A!", "password12345", "123456789012", "alice@example.test"):  # short / common / numeric / equals own e-mail
            self.assertEqual(self.change(new=weak).status_code, 200, msg=weak)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_confirmation_must_match(self):
        self.assertEqual(self.change(confirm=NEW_PASSWORD + "x").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_current_password_guessing_is_rate_limited(self):
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                self.change(old=WRONG)
            self.assertEqual(self.change().status_code, 200)  # correct password, but locked
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password(PASSWORD))
            clock.advance(minutes=15, seconds=1)
            self.assertEqual(self.change().status_code, 302)

    def test_change_is_audited_and_clears_must_change_flag(self):
        self.user.must_change_password = True
        self.user.save()
        self.change()
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        entry = AuditLog.objects.get(action=AuditLog.Action.PASSWORD_CHANGED)
        self.assertNotIn(NEW_PASSWORD, str(entry.meta))


class PasswordResetRequestTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")

    def request(self, email, ip="10.0.0.1", client=None):
        return (client or self.client).post(RESET, {"email": email}, REMOTE_ADDR=ip)

    def test_same_response_for_existing_and_unknown_e_mail(self):
        known = self.request("alice@example.test")
        unknown = self.request("nobody@example.test", ip="10.0.0.2")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])
        def page():  # the language switcher form carries a per-render CSRF token; everything else must be identical
            return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]+"', b"", self.client.get(known["Location"]).content)

        self.assertEqual(page(), page())

    def test_e_mail_is_sent_only_to_an_existing_active_account(self):
        self.request("nobody@example.test")
        self.assertEqual(len(mail.outbox), 0)
        self.request("alice@example.test", ip="10.0.0.3")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.test"])

    def test_e_mail_match_is_case_insensitive(self):
        self.request("ALICE@Example.Test")
        self.assertEqual(len(mail.outbox), 1)

    def test_inactive_and_unusable_password_accounts_get_nothing(self):
        make_user("sleepy", is_active=False)
        ldap = make_user("ldapuser")
        ldap.set_unusable_password()
        ldap.save()
        self.request("sleepy@example.test", ip="10.0.1.1")
        self.request("ldapuser@example.test", ip="10.0.1.2")
        self.assertEqual(len(mail.outbox), 0)

    def test_link_in_mail_has_uid_and_token_and_states_the_validity(self):
        self.request("alice@example.test")
        message = mail.outbox[0]
        self.assertIsNotNone(reset_link_from(message))
        self.assertIn("30 daqiqa", message.body)
        self.assertNotIn(PASSWORD, message.body)

    def test_per_e_mail_limit_keeps_the_same_visible_response(self):
        statuses = [self.request("alice@example.test", ip=f"10.0.2.{i}").status_code for i in range(6)]
        self.assertEqual(set(statuses), {302})
        self.assertEqual(len(mail.outbox), 3)  # reset:email allows 3 per hour
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.PASSWORD_RESET_THROTTLED).exists())

    def test_per_ip_limit(self):
        for i in range(8):
            make_user(f"user{i}")
        for i in range(8):
            self.assertEqual(self.request(f"user{i}@example.test", ip="10.0.3.3").status_code, 302)
        self.assertEqual(len(mail.outbox), 5)  # reset:ip allows 5 per hour

    def test_limit_expires(self):
        with frozen_throttle_clock() as clock:
            for _ in range(4):
                self.request("alice@example.test")
            self.assertEqual(len(mail.outbox), 3)
            clock.advance(hours=1, minutes=1)
            self.request("alice@example.test")
            self.assertEqual(len(mail.outbox), 4)

    def test_mail_failure_does_not_reveal_the_account(self):
        failure = OSError("550 rejected alice@example.test")  # real SMTP errors can carry the address
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=failure):
            with self.assertLogs("apps.accounts.forms", level="ERROR") as logs, self.assertNoLogs("django.contrib.auth", level="DEBUG"):
                response = self.request("alice@example.test")
        self.assertEqual(response.status_code, 302)  # same as for an unknown address
        text = "\n".join(logs.output)
        self.assertIn("OSError", text)  # the error type is logged...
        self.assertNotIn("alice@example.test", text)  # ...never the address,
        self.assertNotIn("Traceback", text)  # ...and no traceback

    def test_invalid_e_mail_is_a_form_error_not_a_crash(self):
        self.assertEqual(self.client.post(RESET, {"email": "not-an-email"}).status_code, 200)

    def test_request_is_audited_with_a_hash_only(self):
        self.request("alice@example.test")
        entry = AuditLog.objects.get(action=AuditLog.Action.PASSWORD_RESET_REQUESTED)
        self.assertNotIn("alice@example.test", str(entry.meta))
        self.assertEqual(len(entry.meta["email_sha256_16"]), 16)


class PasswordResetConfirmTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.client.post(RESET, {"email": "alice@example.test"})
        self.link = reset_link_from(mail.outbox[0])

    def open_form(self, client=None, link=None):
        client = client or self.client
        response = client.get(link or self.link, follow=True)  # Django swaps the token for a session placeholder
        return client, response

    def set_password(self, client, password=NEW_PASSWORD, confirm=None, link=None):
        _, response = self.open_form(client, link)
        return client.post(response.redirect_chain[-1][0], {"new_password1": password, "new_password2": confirm or password})

    def test_valid_link_resets_the_password(self):
        client = Client()
        response = self.set_password(client)
        self.assertRedirects(response, reverse("accounts:password_reset_complete"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))

    def test_reset_never_signs_the_user_in(self):
        client = Client()
        self.set_password(client)
        self.assertFalse(signed_in(client))

    def test_link_works_only_once(self):
        self.set_password(Client())
        _, response = self.open_form(Client())
        self.assertFalse(response.context["validlink"])
        self.assertContains(response, "Havola yaroqsiz")

    def test_expired_link_is_rejected(self):
        later = datetime.now() + timedelta(minutes=31)  # Django compares with a naive local time
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
            _, response = self.open_form(Client())
        self.assertFalse(response.context["validlink"])

    def test_link_valid_just_before_expiry(self):
        almost = datetime.now() + timedelta(minutes=29)
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=almost):
            _, response = self.open_form(Client())
        self.assertTrue(response.context["validlink"])

    def test_tampered_token_is_rejected(self):
        uid, token = re.search(r"/accounts/reset/([^/]+)/([^/]+)/", self.link).groups()
        bad = f"/accounts/reset/{uid}/{token[:-3]}aaa/"
        self.assertFalse(Client().get(bad, follow=True).context["validlink"])
        self.assertFalse(Client().get(f"/accounts/reset/{uid[:-1]}x/{token}/", follow=True).context["validlink"])

    def test_link_dies_after_the_user_signs_in(self):
        login(Client())
        self.assertFalse(self.open_form(Client())[1].context["validlink"])

    def test_link_dies_when_the_password_changes_another_way(self):
        self.user.set_password("Boshqa-Parol-7788!")
        self.user.save()
        self.assertFalse(self.open_form(Client())[1].context["validlink"])

    def test_weak_password_is_rejected_and_link_stays_usable(self):
        client = Client()
        self.assertEqual(self.set_password(client, "short1A!").status_code, 200)
        self.assertEqual(self.set_password(client, NEW_PASSWORD, confirm="different-Value-1!").status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(self.set_password(client).status_code, 302)  # still the same link, now with a good password

    def test_all_existing_sessions_are_closed(self):
        victim_session = Client()
        login(victim_session)  # signing in changes last_login, which (correctly) kills links issued earlier
        self.assertEqual(victim_session.get(reverse("portal:dashboard")).status_code, 200)
        victim_key = victim_session.session.session_key
        Client().post(RESET, {"email": "alice@example.test"}, REMOTE_ADDR="10.7.7.7")
        self.set_password(Client(), link=reset_link_from(mail.outbox[-1]))
        self.assertFalse(Session.objects.filter(session_key=victim_key).exists())  # removed immediately
        self.assertEqual(victim_session.get(reverse("portal:dashboard")).status_code, 302)

    def test_reset_clears_login_lockout_and_is_audited(self):
        for _ in range(5):
            login(self.client, "alice", WRONG)
        self.set_password(Client())
        self.assertEqual(login(Client(), "alice", NEW_PASSWORD).status_code, 302)  # lock was lifted
        entry = AuditLog.objects.get(action=AuditLog.Action.PASSWORD_RESET_COMPLETED)
        self.assertNotIn(NEW_PASSWORD, str(entry.meta))

    def test_mail_link_has_the_two_part_path_and_no_query_string(self):
        self.assertRegex(self.link, r"^/accounts/reset/[^/]+/[^/?]+/$")


class NoSecretsInLogsTests(TestCase):
    def test_reset_flow_logs_neither_token_nor_passwords(self):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler, saved = Capture(), {}
        names = ("", "django", "django.request", "django.security", "apps")
        for name in names:
            logger = logging.getLogger(name)
            saved[name] = (logger.level, logger.propagate)
            logger.setLevel(logging.DEBUG)
            logger.addHandler(handler)
        try:
            make_user("alice")
            self.client.post(RESET, {"email": "alice@example.test"})
            link = reset_link_from(mail.outbox[0])
            token = link.strip("/").split("/")[-1]
            client = Client()
            response = client.get(link, follow=True)
            client.post(response.redirect_chain[-1][0], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
            login(client, "alice", WRONG)
        finally:
            for name in names:
                logger = logging.getLogger(name)
                logger.removeHandler(handler)
                logger.setLevel(saved[name][0])
        joined = "\n".join(records)
        for secret in (token, NEW_PASSWORD, PASSWORD, WRONG):
            self.assertNotIn(secret, joined)
