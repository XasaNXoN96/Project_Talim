import re
import time
from io import StringIO
from unittest import mock

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command
from django.core.management import call_command as run
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.audit.models import AuditLog

from . import otp, twofactor
from .models import BackupCode, TotpDevice
from .testing import PASSWORD, frozen_throttle_clock, login_with_two_factor, make_user
from .twofactor import VERIFIED_KEY, has_confirmed_device, requires_two_factor

User = get_user_model()
LOGIN = reverse("accounts:login")
VERIFY = reverse("accounts:two_factor_verify")
SETUP = reverse("accounts:two_factor_setup")
SECURITY = reverse("accounts:security")
WRONG_PASSWORD = "Noto-g-ri-parol-0000"


def password_step(client, username, password=PASSWORD, **extra):
    return client.post(LOGIN, {"username": username, "password": password, **extra})


def signed_in(client):
    return "_auth_user_id" in client.session


def secret_of(user):
    return otp.decrypt_secret(TotpDevice.objects.get(user=user).secret_encrypted)


def enrol(user):
    """Programmatic enrolment (fast path for tests that are not about enrolment itself). Returns (secret, backup codes)."""
    device = otp.get_or_create_pending_device(user)
    otp.confirm_device(device)
    return otp.decrypt_secret(device.secret_encrypted), otp.generate_backup_codes(user)


def code_at(secret, offset_steps=0):
    return pyotp.TOTP(secret).at(int(time.time()) + offset_steps * 30)


def pending_client(username, password=PASSWORD):
    client = Client()
    password_step(client, username, password)
    return client


class SeededTestCase(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)


class RequiredRolesTests(SeededTestCase):
    def test_policy(self):
        self.assertTrue(requires_two_factor(make_user("a1", role="admin")))
        self.assertTrue(requires_two_factor(make_user("a2", role="sysadmin")))
        self.assertTrue(requires_two_factor(User.objects.create_superuser("root", "root@example.test", PASSWORD)))
        for name, role in (("e1", "employee"), ("h1", "hr"), ("d1", "department_head"), ("c1", "content_manager"), ("n1", None)):
            self.assertFalse(requires_two_factor(make_user(name, role=role)), msg=name)

    def test_inactive_admin_does_not_require_it(self):
        self.assertFalse(requires_two_factor(make_user("gone", role="admin", is_active=False)))

    def test_revoking_the_role_removes_the_requirement(self):
        user = make_user("tmp", role="admin")
        RoleAssignment.objects.get(user=user).delete()
        self.assertFalse(requires_two_factor(User.objects.get(pk=user.pk)))


class FirstTimeSetupTests(SeededTestCase):
    """An administrator without a device is NOT locked out: the first sign-in walks through enrolment."""

    def setUp(self):
        super().setUp()
        self.boss = make_user("boss", role="admin")

    def test_password_step_leads_to_setup_and_does_not_sign_in(self):
        client = Client()
        response = password_step(client, "boss")
        self.assertRedirects(response, SETUP, fetch_redirect_response=False)
        self.assertFalse(signed_in(client))
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.LOGIN).exists())  # nothing signed in yet

    def test_every_protected_url_stays_closed_while_the_second_step_is_pending(self):
        client = pending_client("boss")
        for url in (reverse("portal:dashboard"), reverse("portal:audit"), "/" + settings.ADMIN_URL, SECURITY, reverse("accounts:password_change")):
            response = client.get(url, follow=True)  # /admin/ takes one extra hop through /admin/login/
            self.assertEqual(response.redirect_chain[0][1], 302, msg=url)
            self.assertEqual(response.request["PATH_INFO"], LOGIN, msg=url)  # always ends at the sign-in page
            self.assertEqual(response.status_code, 200, msg=url)
        self.assertFalse(signed_in(client))

    def test_setup_page_shows_qr_and_manual_key(self):
        client = pending_client("boss")
        response = client.get(SETUP)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")
        secret = secret_of(self.boss)
        self.assertContains(response, " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)))

    def test_wrong_code_does_not_complete_enrolment_or_login(self):
        client = pending_client("boss")
        client.get(SETUP)
        response = client.post(SETUP, {"code": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(signed_in(client))
        self.assertFalse(has_confirmed_device(self.boss))  # an unconfirmed device does not count

    def test_valid_code_confirms_signs_in_and_shows_ten_backup_codes_once(self):
        client = pending_client("boss")
        client.get(SETUP)
        response = client.post(SETUP, {"code": code_at(secret_of(self.boss))})
        self.assertEqual(response.status_code, 200)
        codes = response.context["codes"]
        self.assertEqual(len(codes), 10)
        self.assertTrue(all(re.fullmatch(r"[A-Z2-9]{5}-[A-Z2-9]{5}", c) for c in codes))
        self.assertTrue(signed_in(client))
        self.assertTrue(client.session[VERIFIED_KEY])
        self.assertTrue(has_confirmed_device(self.boss))
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 200)  # now really signed in
        page = client.get(SECURITY).content.decode()
        self.assertTrue(all(c not in page for c in codes))  # not retrievable afterwards
        self.assertEqual(client.get(SETUP).status_code, 302)  # nothing left to enrol
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_ENABLED, user=self.boss).exists())
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.LOGIN).count(), 1)

    def test_secret_is_stable_until_the_user_asks_for_a_new_one(self):
        client = pending_client("boss")
        client.get(SETUP)
        first = secret_of(self.boss)
        client.get(SETUP)
        self.assertEqual(first, secret_of(self.boss))
        client.post(SETUP, {"restart": "1"})
        self.assertNotEqual(first, secret_of(self.boss))

    def test_pending_state_expires(self):
        client = Client()
        with mock.patch("apps.accounts.twofactor._ts", return_value=1_000_000):
            password_step(client, "boss")
            self.assertEqual(client.get(SETUP).status_code, 200)
        with mock.patch("apps.accounts.twofactor._ts", return_value=1_000_000 + settings.TWO_FACTOR_PENDING_SECONDS + 1):
            self.assertRedirects(client.get(SETUP), LOGIN, fetch_redirect_response=False)

    def test_setup_and_verify_need_a_pending_or_signed_in_user(self):
        anonymous = Client()
        for url in (SETUP, VERIFY):
            self.assertRedirects(anonymous.get(url), LOGIN, fetch_redirect_response=False)

    def test_deactivated_while_pending(self):
        client = pending_client("boss")
        self.boss.is_active = False
        self.boss.save()
        self.assertRedirects(client.get(SETUP), LOGIN, fetch_redirect_response=False)

    def test_enrolment_attempts_are_rate_limited(self):
        client = pending_client("boss")
        client.get(SETUP)
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                client.post(SETUP, {"code": "000000"})
            self.assertEqual(client.post(SETUP, {"code": code_at(secret_of(self.boss))}).status_code, 200)  # locked: form again
            self.assertFalse(signed_in(client))
            clock.advance(minutes=15, seconds=1)
            client.post(SETUP, {"code": code_at(secret_of(self.boss))})
            self.assertTrue(signed_in(client))


class SecretStorageTests(SeededTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user("boss", role="admin")
        self.secret, self.codes = enrol(self.user)

    def test_secret_is_encrypted_in_the_database(self):
        row = TotpDevice.objects.get(user=self.user)
        self.assertNotEqual(row.secret_encrypted, self.secret)
        self.assertNotIn(self.secret, row.secret_encrypted)
        self.assertEqual(otp.decrypt_secret(row.secret_encrypted), self.secret)
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM accounts_totpdevice")
            self.assertNotIn(self.secret, str(cursor.fetchall()))  # not hiding anywhere in the raw row

    def test_wrong_key_cannot_decrypt(self):
        from cryptography.fernet import Fernet

        token = TotpDevice.objects.get(user=self.user).secret_encrypted
        with override_settings(OTP_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            with self.assertRaises(ImproperlyConfigured):
                otp.decrypt_secret(token)

    def test_key_rotation_old_secrets_still_decrypt(self):
        from cryptography.fernet import Fernet

        token = TotpDevice.objects.get(user=self.user).secret_encrypted
        new_key = Fernet.generate_key().decode()
        with override_settings(OTP_ENCRYPTION_KEYS=[new_key, *settings.OTP_ENCRYPTION_KEYS]):
            self.assertEqual(otp.decrypt_secret(token), self.secret)
            self.assertNotEqual(otp.encrypt_secret(self.secret), token)

    def test_missing_key_fails_loudly(self):
        with override_settings(OTP_ENCRYPTION_KEYS=[]):
            with self.assertRaises(ImproperlyConfigured):
                otp.encrypt_secret("ABC")

    def test_backup_codes_are_stored_only_as_hashes(self):
        for plain, row in zip(self.codes, BackupCode.objects.filter(user=self.user)):
            raw = plain.replace("-", "")
            self.assertNotIn(raw, row.code_hash)
        self.assertEqual(BackupCode.objects.filter(user=self.user).count(), 10)
        self.assertTrue(any(check_password(self.codes[0].replace("-", ""), r.code_hash) for r in BackupCode.objects.filter(user=self.user)))


class VerifyFlowTests(SeededTestCase):
    def setUp(self):
        super().setUp()
        self.boss = make_user("boss", role="admin")
        self.secret, self.codes = enrol(self.boss)

    def test_password_then_code_signs_in(self):
        client = Client()
        self.assertRedirects(password_step(client, "boss"), VERIFY, fetch_redirect_response=False)
        self.assertFalse(signed_in(client))
        response = client.post(VERIFY, {"code": code_at(self.secret)})
        self.assertRedirects(response, reverse("portal:dashboard"), fetch_redirect_response=False)
        self.assertTrue(signed_in(client))
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.LOGIN).count(), 1)

    def test_wrong_code_is_rejected(self):
        client = pending_client("boss")
        response = client.post(VERIFY, {"code": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(signed_in(client))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_FAILED).exists())

    def test_garbage_input_is_rejected(self):
        client = pending_client("boss")
        for value in ("", "abcdef", "12345", "1234567", "' OR 1=1 --", "0" * 40, "<script>"):
            self.assertEqual(client.post(VERIFY, {"code": value}).status_code, 200, msg=value)
            self.assertFalse(signed_in(client), msg=value)

    def test_code_with_spaces_is_accepted(self):
        client = pending_client("boss")
        code = code_at(self.secret)
        client.post(VERIFY, {"code": f"{code[:3]} {code[3:]}"})
        self.assertTrue(signed_in(client))

    def test_a_used_code_cannot_be_replayed(self):
        code = code_at(self.secret)
        first = pending_client("boss")
        first.post(VERIFY, {"code": code})
        self.assertTrue(signed_in(first))
        first.post(reverse("accounts:logout"))
        second = pending_client("boss")
        second.post(VERIFY, {"code": code})  # same code, same 30-second step
        self.assertFalse(signed_in(second))
        second.post(VERIFY, {"code": code_at(self.secret, offset_steps=1)})  # a later step is fine
        self.assertTrue(signed_in(second))

    def test_tolerance_is_exactly_one_step_either_side(self):
        for offset, expected in ((-1, True), (1, True), (-2, False), (2, False)):
            TotpDevice.objects.filter(user=self.boss).update(last_used_counter=None)
            client = pending_client("boss")
            client.post(VERIFY, {"code": code_at(self.secret, offset)})
            self.assertEqual(signed_in(client), expected, msg=f"offset {offset}")

    def test_older_step_than_the_last_used_is_rejected(self):
        client = pending_client("boss")
        client.post(VERIFY, {"code": code_at(self.secret, 1)})
        client.post(reverse("accounts:logout"))
        late = pending_client("boss")
        late.post(VERIFY, {"code": code_at(self.secret, -1)})  # valid by the clock, but older than the last accepted step
        self.assertFalse(signed_in(late))

    def test_remember_me_and_next_survive_the_second_step(self):
        client = Client()
        client.post(LOGIN + "?next=" + reverse("portal:audit"), {"username": "boss", "password": PASSWORD, "remember_me": "on", "next": reverse("portal:audit")})
        response = client.post(VERIFY, {"code": code_at(self.secret)})
        self.assertEqual(response["Location"], reverse("portal:audit"))
        self.assertFalse(client.session.get_expire_at_browser_close())

    def test_without_remember_me_the_session_ends_with_the_browser(self):
        client = pending_client("boss")
        client.post(VERIFY, {"code": code_at(self.secret)})
        self.assertTrue(client.session.get_expire_at_browser_close())

    def test_a_wrong_password_never_reaches_the_second_step(self):
        client = Client()
        response = password_step(client, "boss", WRONG_PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(client.get(VERIFY), LOGIN, fetch_redirect_response=False)

    def test_code_guessing_is_rate_limited(self):
        with frozen_throttle_clock() as clock:
            client = pending_client("boss")
            messages = set()
            for _ in range(5):
                messages.add(re.search(r'alert err".*?<span>(.*?)</span>', client.post(VERIFY, {"code": "000000"}).content.decode(), re.S).group(1))
            locked = client.post(VERIFY, {"code": code_at(self.secret)})  # correct, but locked
            self.assertEqual(locked.status_code, 200)
            self.assertFalse(signed_in(client))
            locked_message = re.search(r'alert err".*?<span>(.*?)</span>', locked.content.decode(), re.S).group(1)
            self.assertEqual(messages, {locked_message})  # "wrong" and "locked" look the same
            self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_LOCKED).count(), 1)  # the moment it locked
            self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_BLOCKED).count(), 1)  # the attempt during the lock
            clock.advance(minutes=15, seconds=1)
            client.post(VERIFY, {"code": code_at(self.secret)})
            self.assertTrue(signed_in(client))

    def test_lockout_of_one_user_does_not_affect_another(self):
        other = make_user("other", role="admin")
        other_secret, _ = enrol(other)
        client = pending_client("boss")
        for _ in range(5):
            client.post(VERIFY, {"code": "000000"})
        second = pending_client("other")
        second.post(VERIFY, {"code": code_at(other_secret)})
        self.assertTrue(signed_in(second))


class EnforcementTests(SeededTestCase):
    def test_privileged_session_without_second_factor_is_closed(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        client = Client()
        client.force_login(boss)  # a session that never went through the second step
        response = client.get(reverse("portal:audit"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(LOGIN, response["Location"])
        self.assertFalse(signed_in(client))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_REQUIRED_LOGOUT, user=boss).exists())

    def test_admin_without_any_device_cannot_use_a_forced_session_either(self):
        boss = make_user("boss", role="admin")
        client = Client()
        client.force_login(boss)
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 302)

    def test_role_granted_after_sign_in_triggers_the_requirement(self):
        user = make_user("emp", role="employee")
        client = Client()
        password_step(client, "emp")
        self.assertEqual(client.get(reverse("portal:dashboard")).status_code, 200)
        RoleAssignment.objects.create(user=user, role=__import__("django.contrib.auth.models", fromlist=["Group"]).Group.objects.get(name="admin"), scope="all")
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 302)  # old session no longer good enough
        self.assertFalse(signed_in(client))

    def test_a_verified_session_passes(self):
        boss = make_user("boss", role="admin")
        client = Client()
        login_with_two_factor(client, boss)
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 200)

    def test_employee_without_a_device_is_unaffected(self):
        make_user("emp", role="employee")
        client = Client()
        self.assertRedirects(password_step(client, "emp"), reverse("portal:dashboard"), fetch_redirect_response=False)
        self.assertTrue(signed_in(client))

    def test_stock_admin_login_cannot_be_used_to_skip_the_second_factor(self):
        staff = make_user("boss", role="admin", is_staff=True)
        enrol(staff)
        client = Client()
        for response in (client.get("/" + settings.ADMIN_URL + "login/"), client.post("/" + settings.ADMIN_URL + "login/", {"username": "boss", "password": PASSWORD})):
            self.assertEqual(response.status_code, 302)
            self.assertIn(LOGIN, response["Location"])
        self.assertFalse(signed_in(client))
        self.assertEqual(client.get("/" + settings.ADMIN_URL, follow=True).request["PATH_INFO"], LOGIN)

    def test_password_reset_does_not_bypass_the_second_factor(self):
        from django.core import mail

        boss = make_user("boss", role="admin")
        enrol(boss)
        Client().post(reverse("accounts:password_reset"), {"email": "boss@example.test"})
        link = re.search(r"(/accounts/reset/\S+/\S+/)", mail.outbox[0].body).group(1)
        client = Client()
        target = client.get(link, follow=True).redirect_chain[-1][0]
        client.post(target, {"new_password1": "Yangi-Kuchli-Parol-2026!", "new_password2": "Yangi-Kuchli-Parol-2026!"})
        self.assertFalse(signed_in(client))
        again = Client()
        self.assertRedirects(password_step(again, "boss", "Yangi-Kuchli-Parol-2026!"), VERIFY, fetch_redirect_response=False)
        self.assertFalse(signed_in(again))


class BackupCodeTests(SeededTestCase):
    def setUp(self):
        super().setUp()
        self.boss = make_user("boss", role="admin")
        self.secret, self.codes = enrol(self.boss)

    def sign_in_with(self, value):
        client = pending_client("boss")
        client.post(VERIFY, {"code": value})
        return client

    def test_backup_code_signs_in_once(self):
        self.assertTrue(signed_in(self.sign_in_with(self.codes[0])))
        self.assertFalse(signed_in(self.sign_in_with(self.codes[0])))  # already used
        self.assertTrue(signed_in(self.sign_in_with(self.codes[1])))  # others still work

    def test_format_is_forgiving(self):
        raw = self.codes[2]
        self.assertTrue(signed_in(self.sign_in_with(raw.lower().replace("-", " "))))

    def test_remaining_count_and_audit(self):
        self.sign_in_with(self.codes[0])
        self.assertEqual(otp.remaining_backup_codes(self.boss), 9)
        entry = AuditLog.objects.get(action=AuditLog.Action.TWO_FACTOR_BACKUP_USED)
        self.assertEqual(entry.meta["remaining"], 9)
        self.assertNotIn(self.codes[0].replace("-", ""), str(entry.meta))

    def test_wrong_backup_codes_count_towards_the_limit(self):
        with frozen_throttle_clock():
            client = pending_client("boss")
            for _ in range(5):
                client.post(VERIFY, {"code": "AAAAA-AAAAA"})
            client.post(VERIFY, {"code": self.codes[0]})
        self.assertFalse(signed_in(client))
        self.assertEqual(otp.remaining_backup_codes(self.boss), 10)  # the correct code was not even consumed

    def test_regeneration_needs_the_password_and_invalidates_old_codes(self):
        client = Client()
        login_with_two_factor(client, self.boss)
        url = reverse("accounts:backup_codes_regenerate")
        self.assertEqual(client.post(url, {"password": WRONG_PASSWORD}).status_code, 200)  # refused
        self.assertEqual(otp.remaining_backup_codes(self.boss), 10)
        response = client.post(url, {"password": PASSWORD})
        new_codes = response.context["codes"]
        self.assertEqual(len(new_codes), 10)
        self.assertFalse(set(new_codes) & set(self.codes))
        self.assertFalse(signed_in(self.sign_in_with(self.codes[0])))  # old code is dead
        self.assertTrue(signed_in(self.sign_in_with(new_codes[0])))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_BACKUP_REGENERATED).exists())

    def test_regeneration_password_check_is_rate_limited(self):
        client = Client()
        login_with_two_factor(client, self.boss)
        url = reverse("accounts:backup_codes_regenerate")
        with frozen_throttle_clock():
            for _ in range(5):
                client.post(url, {"password": WRONG_PASSWORD})
            self.assertEqual(client.post(url, {"password": PASSWORD}).status_code, 200)  # correct, but locked
        self.assertEqual(otp.remaining_backup_codes(self.boss), 10)

    def test_regeneration_requires_login(self):
        self.assertIn(LOGIN, Client().get(reverse("accounts:backup_codes_regenerate"))["Location"])


class OptInAndDisableTests(SeededTestCase):
    def test_employee_can_opt_in_and_then_needs_the_code(self):
        emp = make_user("emp", role="employee")
        client = Client()
        password_step(client, "emp")
        client.get(SETUP)
        response = client.post(SETUP, {"code": code_at(secret_of(emp))})
        self.assertEqual(len(response.context["codes"]), 10)
        client.post(reverse("accounts:logout"))
        again = Client()
        self.assertRedirects(password_step(again, "emp"), VERIFY, fetch_redirect_response=False)
        self.assertFalse(signed_in(again))

    def test_employee_can_disable_with_the_password(self):
        emp = make_user("emp", role="employee")
        enrol(emp)
        client = Client()
        login_with_two_factor(client, emp)
        url = reverse("accounts:two_factor_disable")
        client.post(url, {"password": WRONG_PASSWORD})
        self.assertTrue(has_confirmed_device(emp))  # wrong password: nothing happens
        client.post(url, {"password": PASSWORD})
        self.assertFalse(has_confirmed_device(emp))
        self.assertFalse(BackupCode.objects.filter(user=emp).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_DISABLED, user=emp).exists())
        fresh = Client()
        self.assertRedirects(password_step(fresh, "emp"), reverse("portal:dashboard"), fetch_redirect_response=False)

    def test_administrators_cannot_disable_it(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        client = Client()
        login_with_two_factor(client, boss)
        url = reverse("accounts:two_factor_disable")
        self.assertRedirects(client.get(url), SECURITY, fetch_redirect_response=False)
        self.assertRedirects(client.post(url, {"password": PASSWORD}), SECURITY, fetch_redirect_response=False)
        self.assertTrue(has_confirmed_device(boss))

    def test_security_page_reflects_the_state(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        client = Client()
        login_with_two_factor(client, boss)
        page = client.get(SECURITY).content.decode()
        self.assertIn("majburiy", page)
        self.assertNotIn(reverse("accounts:two_factor_disable"), page)

    def test_security_page_requires_login(self):
        self.assertIn(LOGIN, Client().get(SECURITY)["Location"])

    def test_password_change_keeps_a_verified_session_working(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        client = Client()
        login_with_two_factor(client, boss)
        client.post(reverse("accounts:password_change"), {"old_password": PASSWORD, "new_password1": "Yangi-Kuchli-Parol-2026!", "new_password2": "Yangi-Kuchli-Parol-2026!"})
        self.assertEqual(client.get(reverse("portal:audit")).status_code, 200)


class RecoveryCommandTests(SeededTestCase):
    def test_reset_lets_an_administrator_enrol_again_without_being_locked_out(self):
        boss = make_user("boss", role="admin")
        enrol(boss)
        elsewhere = Client()
        login_with_two_factor(elsewhere, boss)
        out = StringIO()
        run("reset_2fa", "boss", "--yes", stdout=out)
        self.assertFalse(has_confirmed_device(boss))
        self.assertFalse(TotpDevice.objects.filter(user=boss).exists())
        self.assertFalse(BackupCode.objects.filter(user=boss).exists())
        self.assertEqual(elsewhere.get(reverse("portal:audit")).status_code, 302)  # old sessions closed
        client = Client()
        self.assertRedirects(password_step(client, "boss"), SETUP, fetch_redirect_response=False)  # enrol again
        client.get(SETUP)
        client.post(SETUP, {"code": code_at(secret_of(boss))})
        self.assertTrue(signed_in(client))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_RESET, user=boss).exists())
        self.assertIn("must enrol again", out.getvalue())

    def test_unknown_user(self):
        with self.assertRaises(CommandError):
            run("reset_2fa", "nobody", "--yes")

    def test_requires_confirmation_without_yes(self):
        make_user("boss", role="admin")
        with mock.patch("builtins.input", return_value="wrong"):
            with self.assertRaises(CommandError):
                run("reset_2fa", "boss")
