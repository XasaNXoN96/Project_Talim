"""Scanner tests against a STUB clamd (a tiny threaded server that speaks the INSTREAM protocol).

They prove how OUR code behaves for each answer or failure. They do NOT prove that a real ClamAV detects anything:
real-daemon checks live in tests_real_clamd.py and are skipped unless a clamd is reachable (CLAMAV_REAL_TEST=1).
"""
import os
import socket
import struct
import subprocess
import sys
import shutil
import tempfile
import threading
import time
from pathlib import Path

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog

from . import files, scanner
from .models import Document, DocumentCategory, DocumentVersion
from .testing import PDF, upload
from .validation import UploadRejected


class FakeClamd:
    """behaviour: ok | found | error | size | garbage | silent (never answers) | hangup (closes mid-stream) | slow_accept"""

    def __init__(self, behaviour="ok", unix_path=None):
        self.behaviour, self.received, self.connections = behaviour, b"", 0
        self.unix_path = unix_path
        if unix_path:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.bind(unix_path)
        else:
            self.sock = socket.socket()
            self.sock.bind(("127.0.0.1", 0))
            self.port = self.sock.getsockname()[1]
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()
        self.thread.join(2)
        self.sock.close()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _read(self, conn, n):
        buf = b""
        while len(buf) < n:
            part = conn.recv(n - len(buf))
            if not part:
                raise EOFError
            buf += part
        return buf

    def _handle(self, conn):
        try:
            cmd = b""
            while not cmd.endswith(b"\0"):
                cmd += conn.recv(1)
            if cmd == b"zPING\0":
                conn.sendall(b"PONG\0")
                return
            assert cmd == b"zINSTREAM\0", cmd
            data = b""
            while True:
                (length,) = struct.unpack("!I", self._read(conn, 4))
                if length == 0:
                    break
                data += self._read(conn, length)
                if self.behaviour == "hangup":
                    conn.close()
                    return
            self.received = data
            reply = {"ok": b"stream: OK\0", "found": b"stream: Win.Test.Malware-1 FOUND\0", "error": b"Some failure ERROR\0",
                     "size": b"INSTREAM size limit exceeded. ERROR\0", "garbage": b"\xff\xfe nonsense\0"}.get(self.behaviour)
            if self.behaviour == "silent":
                time.sleep(3)
            elif reply:
                conn.sendall(reply)
        except (EOFError, OSError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


def scanning(fake, **extra):
    cfg = {"DOCUMENT_SCAN_MODE": "clamav", "CLAMAV_SOCKET": fake.unix_path or "", "CLAMAV_HOST": "127.0.0.1", "CLAMAV_PORT": getattr(fake, "port", 0), "CLAMAV_TIMEOUT": 2}
    cfg.update(extra)
    return override_settings(**cfg)


class ScannerProtocolTests(SimpleTestCase):
    def run_with(self, behaviour, data=b"hello", **extra):
        fake = FakeClamd(behaviour).start()
        try:
            with scanning(fake, **extra):
                return scanner.scan_bytes(data), fake
        finally:
            fake.stop()

    def test_clean_verdict_and_the_whole_content_reaches_only_the_configured_daemon(self):
        data = os.urandom(300_000)  # several chunks
        result, fake = self.run_with("ok", data)
        self.assertTrue(result.clean)
        self.assertEqual(fake.received, data)

    def test_threat_verdict_carries_a_sanitised_signature(self):
        result, _ = self.run_with("found")
        self.assertFalse(result.clean)
        self.assertEqual(result.signature, "Win.Test.Malware-1")

    def test_every_non_ok_answer_is_a_failure_not_a_pass(self):
        for behaviour, code in (("error", "scan_error"), ("size", "scan_error"), ("garbage", "scan_error")):
            with self.assertRaises(scanner.ScanFailed) as ctx:
                self.run_with(behaviour)
            self.assertEqual(ctx.exception.code, code, behaviour)

    def test_connection_dropped_mid_stream_is_a_failure(self):
        with self.assertRaises(scanner.ScanFailed):
            self.run_with("hangup", os.urandom(300_000))

    def test_daemon_not_running_is_unavailable(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()  # nobody listens now
        with override_settings(DOCUMENT_SCAN_MODE="clamav", CLAMAV_SOCKET="", CLAMAV_HOST="127.0.0.1", CLAMAV_PORT=port, CLAMAV_TIMEOUT=2):
            with self.assertRaises(scanner.ScanFailed) as ctx:
                scanner.scan_bytes(b"x")
        self.assertEqual(ctx.exception.code, "scan_unavailable")

    def test_missing_unix_socket_is_unavailable(self):
        with override_settings(CLAMAV_SOCKET="/nonexistent/clamd.sock", CLAMAV_TIMEOUT=2):
            with self.assertRaises(scanner.ScanFailed) as ctx:
                scanner.scan_bytes(b"x")
        self.assertEqual(ctx.exception.code, "scan_unavailable")

    def test_timeout_is_enforced_as_one_overall_deadline(self):
        started = time.monotonic()
        with self.assertRaises(scanner.ScanFailed) as ctx:
            self.run_with("silent", CLAMAV_TIMEOUT=0.5)
        self.assertEqual(ctx.exception.code, "scan_timeout")
        self.assertLess(time.monotonic() - started, 2.5)

    def test_unix_socket_transport(self):
        socket_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, socket_dir, True)  # only the directory created here
        path = str(Path(socket_dir) / "clamd.sock")
        fake = FakeClamd("ok", unix_path=path).start()
        try:
            with scanning(fake):
                self.assertTrue(scanner.scan_bytes(b"abc").clean)
                self.assertTrue(scanner.ping())
        finally:
            fake.stop()

    def test_ping_false_when_down(self):
        with override_settings(CLAMAV_SOCKET="/nonexistent/clamd.sock"):
            self.assertFalse(scanner.ping())


class PipelineTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.cat = DocumentCategory.objects.first()
        self.client = Client()
        login_with_two_factor(self.client, self.hr)

    def payload(self, name="maxfiy-ism.pdf"):
        return {"title": "Yangi", "category": self.cat.pk, "access_level": "general", "file": upload(name)}

    def post_create(self, fake, **extra):
        with scanning(fake, **extra):
            return self.client.post(reverse("documents:create"), self.payload())

    def test_clean_file_is_accepted_and_the_verdict_is_recorded(self):
        fake = FakeClamd("ok").start()
        try:
            r = self.post_create(fake)
        finally:
            fake.stop()
        self.assertEqual(r.status_code, 302)
        v = DocumentVersion.objects.get()
        self.assertEqual((v.scan_status, v.scan_engine), ("clean", "clamav"))
        self.assertIsNotNone(v.scanned_at)
        self.assertEqual(fake.received, PDF)

    def test_infected_file_is_rejected_unpublished_and_audited_safely(self):
        before = sum(1 for p in Path(settings_root()).rglob("*") if p.is_file())
        fake = FakeClamd("found").start()
        try:
            r = self.post_create(fake)
        finally:
            fake.stop()
        self.assertContains(r, "zararli dastur aniqlandi")
        self.assertEqual((Document.objects.count(), DocumentVersion.objects.count()), (0, 0))
        self.assertEqual(sum(1 for p in Path(settings_root()).rglob("*") if p.is_file()), before)  # nothing written to the private store
        threat = AuditLog.objects.get(action=AuditLog.Action.FILE_THREAT_DETECTED)
        self.assertEqual(threat.meta, {"signature": "Win.Test.Malware-1"})
        reject = AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED)
        self.assertEqual(reject.meta, {"reason": "malware"})
        for e in (threat, reject):
            self.assertNotIn("maxfiy", str(e.meta) + e.object_id)

    def test_scanner_down_fails_closed(self):
        fake = FakeClamd("ok")
        fake.sock.close()  # the port is now closed: connection refused
        with scanning(fake):
            r = self.client.post(reverse("documents:create"), self.payload())
        self.assertContains(r, "tekshirish xizmati")
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED).meta, {"reason": "scan_unavailable"})

    def test_timeout_fails_closed(self):
        fake = FakeClamd("silent").start()
        try:
            r = self.post_create(fake, CLAMAV_TIMEOUT=0.5)
        finally:
            fake.stop()
        self.assertContains(r, "uzoq davom etdi")
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(AuditLog.objects.get(action=AuditLog.Action.DOCUMENT_UPLOAD_REJECTED).meta, {"reason": "scan_timeout"})

    def test_daemon_error_and_size_limit_answers_fail_closed(self):
        for behaviour in ("error", "size", "garbage"):
            fake = FakeClamd(behaviour).start()
            try:
                r = self.post_create(fake)
            finally:
                fake.stop()
            self.assertContains(r, "qabul qilinmadi", msg_prefix=behaviour)
        self.assertEqual(Document.objects.count(), 0)

    def test_invalid_files_never_reach_the_scanner(self):
        fake = FakeClamd("ok").start()
        try:
            with scanning(fake):
                self.client.post(reverse("documents:create"), {**self.payload(), "file": upload("x.exe", b"MZ")})
        finally:
            fake.stop()
        self.assertEqual(fake.connections, 0)

    def test_new_versions_are_scanned_too(self):
        fake_ok = FakeClamd("ok").start()
        try:
            self.post_create(fake_ok)
        finally:
            fake_ok.stop()
        d = Document.objects.get()
        fake = FakeClamd("found").start()
        try:
            with scanning(fake):
                self.client.post(reverse("documents:version_add", args=[d.pk]), {"file": upload("v2.pdf", PDF + b"%2")})
        finally:
            fake.stop()
        self.assertEqual(d.versions.count(), 1)

    def test_disabled_mode_stores_but_marks_files_as_not_scanned(self):
        with override_settings(DOCUMENT_SCAN_MODE="disabled"):
            self.client.post(reverse("documents:create"), self.payload())
        self.assertEqual(DocumentVersion.objects.get().scan_status, "not_scanned")

    def test_audit_never_contains_content(self):
        fake = FakeClamd("found").start()
        try:
            with scanning(fake):
                self.client.post(reverse("documents:create"), {**self.payload(), "file": upload("a.pdf", PDF + b"SECRET-CONTENT")})
        finally:
            fake.stop()
        self.assertFalse(any("SECRET-CONTENT" in str(e.meta) for e in AuditLog.objects.all()))


def settings_root():
    from django.conf import settings

    return settings.PRIVATE_MEDIA_ROOT


class QuarantineAndCommandTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.emp = make_user("emp", role="employee")
        self.cat = DocumentCategory.objects.first()
        from .services import add_version
        from .validation import validate_upload

        self.doc = Document.objects.create(title="Eski", category=self.cat, created_by=self.hr)
        self.version = add_version(self.doc, validate_upload(upload("a.pdf")), actor=self.hr)  # scan disabled in tests -> not_scanned
        self.client = Client()
        login_with_two_factor(self.client, self.emp)

    def test_rescan_marks_infected_versions_and_they_are_never_served(self):
        fake = FakeClamd("found").start()
        try:
            with scanning(fake):
                call_command("scan_documents")
        finally:
            fake.stop()
        self.version.refresh_from_db()
        self.assertEqual(self.version.scan_status, "infected")
        self.assertEqual(self.client.get(reverse("documents:download", args=[self.doc.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:download_version", args=[self.doc.pk, 1])).status_code, 404)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.FILE_THREAT_DETECTED, meta__source="rescan").exists())
        body = self.client.get(reverse("documents:detail", args=[self.doc.pk])).content.decode()
        self.assertNotIn(reverse("documents:download_version", args=[self.doc.pk, 1]), body)

    def test_rescan_marks_clean(self):
        fake = FakeClamd("ok").start()
        try:
            with scanning(fake):
                call_command("scan_documents")
        finally:
            fake.stop()
        self.version.refresh_from_db()
        self.assertEqual(self.version.scan_status, "clean")
        self.assertEqual(self.client.get(reverse("documents:download", args=[self.doc.pk])).status_code, 200)

    def test_rescan_with_scanner_down_changes_nothing_and_fails(self):
        from django.core.management.base import CommandError

        with override_settings(DOCUMENT_SCAN_MODE="clamav", CLAMAV_SOCKET="/nonexistent/x.sock", CLAMAV_TIMEOUT=1):
            with self.assertRaises(CommandError):
                call_command("scan_documents")
        self.version.refresh_from_db()
        self.assertEqual(self.version.scan_status, "not_scanned")

    def test_check_scanner_command(self):
        from io import StringIO

        from django.core.management.base import CommandError

        fake = FakeClamd("ok").start()
        try:
            with scanning(fake):
                out = StringIO()
                call_command("check_scanner", stdout=out)
                self.assertIn("clamd OK", out.getvalue())
        finally:
            fake.stop()
        with override_settings(DOCUMENT_SCAN_MODE="clamav", CLAMAV_SOCKET="/nonexistent/x.sock"):
            with self.assertRaises(CommandError):
                call_command("check_scanner")
        with override_settings(DOCUMENT_SCAN_MODE="disabled"):
            with self.assertRaises(CommandError):
                call_command("check_scanner")

    def test_verify_document_files(self):
        from django.core.management.base import CommandError

        call_command("verify_document_files")
        Path(self.version.file.path).write_bytes(b"tampered")
        with self.assertRaises(CommandError):
            call_command("verify_document_files")
        Path(self.version.file.path).unlink()
        with self.assertRaises(CommandError):
            call_command("verify_document_files")


class ProductionGuardTests(SimpleTestCase):
    def test_production_refuses_to_start_with_scanning_disabled(self):
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.production", "DJANGO_SECRET_KEY": "x" * 80, "DJANGO_ALLOWED_HOSTS": "a.test",
               "OTP_ENCRYPTION_KEYS": "Vd89ffgaIBKyfs3cTdxx0oY3ExI6vPux7GHTCBdWaTE=", "EMAIL_HOST": "smtp.test", "DEFAULT_FROM_EMAIL": "a@a.test",
               "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "DOCUMENT_SCAN_MODE": "disabled", "DJANGO_ADMIN_URL": "gate-0123456789abcdef/"}
        proc = subprocess.run([sys.executable, "-c", "import django; django.setup()"], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("DOCUMENT_SCAN_MODE", proc.stderr)
        env["DOCUMENT_SCAN_MODE"] = "clamav"
        proc = subprocess.run([sys.executable, "-c", "import django; django.setup()"], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])


class CheckScannerEicarTests(SimpleTestCase):
    """`check_scanner --eicar`: a daemon that ANSWERS but has no usable signature database must not pass (it would accept real malware)."""

    EICAR_START = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

    def run_check(self, detects, scan_error=None):
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command
        seen = []

        def fake_scan(data):
            seen.append(data)
            if scan_error:
                raise scanner.ScanFailed(scan_error)
            return scanner.ScanResult(clean=not (detects and b"EICAR-STANDARD" in data), signature="Eicar-Test-Signature" if detects else "")

        with override_settings(DOCUMENT_SCAN_MODE="clamav"), mock.patch.object(scanner, "ping", return_value=True), mock.patch.object(scanner, "scan_bytes", side_effect=fake_scan):
            out = StringIO()
            call_command("check_scanner", "--eicar", "--no-record", stdout=out)
            return out.getvalue(), seen

    def test_passes_when_the_standard_test_string_is_detected(self):
        out, seen = self.run_check(detects=True)
        self.assertIn("EICAR test string was DETECTED", out)
        self.assertEqual(seen[-1], self.EICAR_START)                 # exactly the standard string, nothing else

    def test_fails_when_the_daemon_calls_the_test_string_clean_that_means_no_usable_signatures(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError) as ctx:
            self.run_check(detects=False)
        self.assertIn("did NOT detect", str(ctx.exception))
        self.assertIn("freshclam", str(ctx.exception))

    def test_a_scan_that_fails_fails_the_check(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.run_check(detects=True, scan_error="scan_unavailable")

    def test_the_plain_check_without_the_flag_is_unchanged(self):
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command
        with override_settings(DOCUMENT_SCAN_MODE="clamav"), mock.patch.object(scanner, "ping", return_value=True), \
                mock.patch.object(scanner, "scan_bytes", return_value=scanner.ScanResult(clean=True)) as scan:
            out = StringIO()
            call_command("check_scanner", "--no-record", stdout=out)
        self.assertIn("test scan succeeded", out.getvalue())
        self.assertEqual(scan.call_count, 1)
