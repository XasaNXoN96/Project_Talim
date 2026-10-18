"""Day 26 review: what a person sees when the OTP encryption key is lost or wrong (restored database, missing key file, rotation gone wrong).
The operator needs a clear signal, the person a calm page, and a backup code must still work (it does not depend on the key)."""
import logging

from django.test import Client, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog

from .tests_twofactor import VERIFY, SeededTestCase, code_at, enrol, password_step, signed_in
from .testing import make_user

from cryptography.fernet import Fernet  # noqa: E402

WRONG_KEY = Fernet.generate_key().decode()   # a different, throw-away key (the test settings use a fixed one)


class LostOrWrongOtpKey(SeededTestCase):
    def setUp(self):
        super().setUp()
        self.boss = make_user("boss", role="admin")
        self.secret, self.codes = enrol(self.boss)          # enrolled with the configured (test) key

    def pending(self):
        c = Client(raise_request_exception=False)
        password_step(c, "boss")
        return c

    def test_a_six_digit_code_with_an_unreadable_secret_gives_a_calm_refusal_not_a_server_error(self):
        with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]):
            c = self.pending()
            r = c.post(VERIFY, {"code": code_at(self.secret)})
        self.assertEqual(r.status_code, 200, "an unreadable second-factor secret must not end in an HTTP 500")
        self.assertFalse(signed_in(c))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.TWO_FACTOR_FAILED).exists())

    def test_the_operator_gets_a_loud_log_line_without_any_secret(self):
        with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]), self.assertLogs("apps.accounts", level=logging.ERROR) as logs:
            self.pending().post(VERIFY, {"code": code_at(self.secret)})
        text = "\n".join(logs.output)
        self.assertIn("OTP_ENCRYPTION_KEYS", text)
        self.assertNotIn(self.secret, text)
        self.assertNotIn(WRONG_KEY, text)

    def test_a_backup_code_still_signs_in_because_it_does_not_depend_on_the_key(self):
        with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]):
            c = self.pending()
            c.post(VERIFY, {"code": self.codes[0]})
        self.assertTrue(signed_in(c))

    def test_the_page_tells_the_person_to_contact_the_administrator_in_every_language(self):
        for lang, text in (("uz", "administrator"), ("ru", "администратор"), ("en", "administrator")):
            with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]):
                c = self.pending()
                c.cookies["django_language"] = lang
                r = c.post(VERIFY, {"code": code_at(self.secret)})
            self.assertIn(text, r.content.decode().lower(), lang)


class UnfinishedEnrolmentAfterKeyLoss(SeededTestCase):
    """A person who had started (not finished) enrolling when the key was lost must be able to start again: nothing depends on an unconfirmed secret."""

    def test_the_setup_page_replaces_an_unreadable_unconfirmed_secret_instead_of_failing(self):
        from .models import TotpDevice
        from .twofactor import VERIFIED_KEY  # noqa: F401
        boss = make_user("boss", role="admin")
        c = Client(raise_request_exception=False)
        password_step(c, "boss")
        self.assertEqual(c.get(reverse("accounts:two_factor_setup")).status_code, 200)       # creates the pending device under the current key
        old = TotpDevice.objects.get(user=boss).secret_encrypted
        with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]):
            r = c.get(reverse("accounts:two_factor_setup"))
        self.assertEqual(r.status_code, 200, "an unconfirmed device under a lost key must be replaced, not crash the page")
        self.assertNotEqual(TotpDevice.objects.get(user=boss).secret_encrypted, old)

    def test_a_confirmed_device_is_never_silently_replaced(self):
        from .models import TotpDevice
        boss = make_user("boss2", role="admin")
        enrol(boss)
        before = TotpDevice.objects.get(user=boss).secret_encrypted
        with override_settings(OTP_ENCRYPTION_KEYS=[WRONG_KEY]):
            from . import otp
            from django.core.exceptions import ImproperlyConfigured
            with self.assertRaises(ImproperlyConfigured):
                otp.provisioning_uri(otp.get_or_create_pending_device(boss))
        self.assertEqual(TotpDevice.objects.get(user=boss).secret_encrypted, before)   # only an administrator (reset_2fa) may drop a confirmed device
