"""REAL clamd checks. Skipped unless CLAMAV_REAL_TEST=1 and a daemon answers PING.

Run (see docs/CLAMAV.md):  CLAMAV_REAL_TEST=1 python manage.py test apps.documents.tests_real_clamd
The "threat" below is the industry-standard EICAR test string, harmless by design. Whether it is detected depends on the
signature database loaded into that clamd (the official daily.cvd contains it). In the sandbox where these were first run,
the official database was NOT downloadable, so detection came from a one-line LOCAL hash signature: the real ClamAV engine,
but not the official signatures.
"""
import os

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog

from . import scanner
from .models import Document, DocumentCategory, DocumentVersion
from .testing import PDF, upload

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
REAL = os.environ.get("CLAMAV_REAL_TEST") == "1"


def real_settings():
    return override_settings(
        DOCUMENT_SCAN_MODE="clamav", CLAMAV_SOCKET=os.environ.get("CLAMAV_SOCKET", ""), CLAMAV_HOST=os.environ.get("CLAMAV_HOST", "127.0.0.1"),
        CLAMAV_PORT=int(os.environ.get("CLAMAV_PORT", "3310")), CLAMAV_TIMEOUT=30,
    )


def _skip_reason():
    if not REAL:
        return "set CLAMAV_REAL_TEST=1 to run the real-clamd checks"
    with real_settings():
        return None if scanner.ping() else "CLAMAV_REAL_TEST=1 but clamd does not answer PING"


import unittest  # noqa: E402

_reason = _skip_reason()


@unittest.skipIf(_reason, _reason or "")
class RealClamdTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.client = Client()
        login_with_two_factor(self.client, self.hr)
        self.cat = DocumentCategory.objects.first()

    def test_clean_pdf_passes(self):
        with real_settings():
            self.assertTrue(scanner.scan_bytes(PDF).clean)

    def test_eicar_is_detected_by_the_real_engine(self):
        with real_settings():
            result = scanner.scan_bytes(EICAR)
        self.assertFalse(result.clean)
        self.assertIn("Eicar", result.signature)

    def test_data_beyond_the_daemons_stream_limit_is_a_failure_not_a_pass(self):
        with real_settings(), self.assertRaises(scanner.ScanFailed):
            scanner.scan_bytes(b"\0" * (26 * 1024 * 1024))  # clamd.conf in docs/CLAMAV.md sets StreamMaxLength 25M

    def test_upload_flow_with_a_real_daemon(self):
        with real_settings():
            ok = self.client.post(reverse("documents:create"), {"title": "Toza", "category": self.cat.pk, "access_level": "general", "file": upload("a.txt", b"salom")})
            bad = self.client.post(reverse("documents:create"), {"title": "Zararli", "category": self.cat.pk, "access_level": "general", "file": upload("b.txt", EICAR)})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(DocumentVersion.objects.get().scan_status, "clean")
        self.assertContains(bad, "zararli dastur aniqlandi")
        self.assertEqual(Document.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.FILE_THREAT_DETECTED).exists())
