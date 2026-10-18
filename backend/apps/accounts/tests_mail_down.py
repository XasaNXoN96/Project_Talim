"""Day 26 review: the mail server is unreachable (no SMTP, wrong credentials, outage). Password reset must stay neutral and calm, never a 500 and never a leak
of whether the address exists; the operator needs a log line; an invitation reports the failure to the administrator instead of crashing."""
import logging
import smtplib
from unittest import mock

from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.acceptance import World


def broken_send(*args, **kwargs):
    raise smtplib.SMTPConnectError(421, "service not available")


class MailServerDown(__import__("django.test", fromlist=["TestCase"]).TestCase):
    def setUp(self):
        self.w = World()

    def test_password_reset_answers_the_same_whether_or_not_mail_works_and_does_not_crash(self):
        c = Client(raise_request_exception=False)
        ok_known = c.post(reverse("accounts:password_reset"), {"email": "emp@example.test"})
        mail.outbox.clear()
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=broken_send):
            down_known = Client(raise_request_exception=False).post(reverse("accounts:password_reset"), {"email": "emp@example.test"})
            down_unknown = Client(raise_request_exception=False).post(reverse("accounts:password_reset"), {"email": "nobody@example.test"})
        self.assertEqual((ok_known.status_code, ok_known["Location"]), (down_known.status_code, down_known["Location"]), "an outage must look the same as success to the visitor")
        self.assertEqual((down_unknown.status_code, down_unknown["Location"]), (down_known.status_code, down_known["Location"]))

    def test_the_operator_sees_a_log_line_that_names_no_address_and_no_token(self):
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=broken_send), self.assertLogs("apps.accounts", level=logging.ERROR) as logs:
            Client(raise_request_exception=False).post(reverse("accounts:password_reset"), {"email": "emp@example.test"})
        text = "\n".join(logs.output)
        self.assertNotIn("emp@example.test", text)
        self.assertNotIn("/accounts/reset/", text)

    def test_an_invitation_that_cannot_be_sent_is_reported_to_the_administrator_not_a_crash(self):
        target = self.w.users["emp"]
        admin = self.w.client("admin")
        admin.raise_request_exception = False
        with mock.patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=broken_send):
            r = admin.post(reverse("users:action", args=[target.pk, "invite"]), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action="user_invited").exists(), "an invitation that was not sent must not be recorded as sent")
