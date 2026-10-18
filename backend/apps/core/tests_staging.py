"""Staging tooling (Day 15): the preflight rules, the example environment file, the release script's guard rails.
The end-to-end behaviour (real gunicorn, real PostgreSQL, rollback) is exercised by deploy/staging/verify_release.sh and verify_preflight.sh;
these tests keep the pure rules from regressing in the normal test run."""
import importlib.util
import os
import re
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet
from django.test import SimpleTestCase

STAGING = Path(__file__).resolve().parents[2] / "deploy" / "staging"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, STAGING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def good_env():
    return {
        "DJANGO_SETTINGS_MODULE": "config.settings.production", "DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "k" * 60,
        "DJANGO_ALLOWED_HOSTS": "staging.invalid", "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.invalid", "DJANGO_ADMIN_URL": "gate-abc123/",
        "DJANGO_TRUSTED_PROXIES": "127.0.0.1", "DJANGO_PRIVATE_MEDIA_ROOT": "/var/lib/talim/private_media", "DB_NAME": "talim_staging",
        "DB_USER": "talim_app", "DB_PASSWORD": "pw-not-a-placeholder", "DB_HOST": "127.0.0.1", "OTP_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
        "DOCUMENT_SCAN_MODE": "clamav", "EMAIL_HOST": "smtp.staging.invalid", "DEFAULT_FROM_EMAIL": "noreply@staging.invalid", "DJANGO_HSTS_SECONDS": "0",
    }


class PreflightRules(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pre = _load("preflight")

    def run_rules(self, env):
        report = self.pre.Report()
        self.pre.check_env_values(env, report)
        return report

    def test_a_correct_environment_passes(self):
        report = self.run_rules(good_env())
        self.assertTrue(report.ok, [r for r in report.rows if r[0] == "FAIL"])

    def test_every_deliberate_mistake_fails(self):
        mistakes = {
            "debug": {"DJANGO_DEBUG": "1"}, "dev settings": {"DJANGO_SETTINGS_MODULE": "config.settings.dev"}, "short secret": {"DJANGO_SECRET_KEY": "short"},
            "wildcard host": {"DJANGO_ALLOWED_HOSTS": "*"}, "wildcard sub": {"DJANGO_ALLOWED_HOSTS": "*.example.test"}, "http origin": {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://x.invalid"},
            "scanner off": {"DOCUMENT_SCAN_MODE": "disabled"}, "csp report only": {"DJANGO_CSP_REPORT_ONLY": "1"}, "bad otp key": {"OTP_ENCRYPTION_KEYS": "nope"},
            "superuser role": {"DB_USER": "postgres"}, "owner role": {"DB_USER": "talim_owner"}, "placeholder": {"DB_PASSWORD": "CHANGE_ME_x"}, "empty": {"EMAIL_HOST": ""},
            "hsts garbage": {"DJANGO_HSTS_SECONDS": "soon"},
        }
        for label, change in mistakes.items():
            with self.subTest(label):
                self.assertFalse(self.run_rules({**good_env(), **change}).ok)

    def test_a_missing_variable_fails(self):
        env = good_env()
        del env["OTP_ENCRYPTION_KEYS"]
        self.assertFalse(self.run_rules(env).ok)

    def test_the_report_never_contains_a_secret_value(self):
        env = good_env()
        env["DJANGO_SECRET_KEY"] = "S3CR3T-" + "z" * 60
        env["DB_PASSWORD"] = "P4SSW0RD-unique"
        env["OTP_ENCRYPTION_KEYS"] = "BADKEY-unique-value"
        text = repr(self.run_rules(env).rows)
        for secret in ("S3CR3T-", "P4SSW0RD-unique", "BADKEY-unique-value"):
            self.assertNotIn(secret, text)

    def test_the_example_file_is_all_placeholders_and_is_refused(self):
        text = (STAGING / "talim.env.staging.example").read_text()
        env = self.pre.parse_env(text)
        self.assertEqual(sorted(set(self.pre.REQUIRED) - set(env)), [])
        report = self.run_rules(env)
        self.assertFalse(report.ok)
        for key in ("DJANGO_SECRET_KEY", "DB_PASSWORD", "OTP_ENCRYPTION_KEYS", "DJANGO_ADMIN_URL", "EMAIL_HOST"):
            self.assertRegex(env[key], r"CHANGE_ME", key)

    def test_parse_env_handles_quotes_comments_and_blank_lines(self):
        env = self.pre.parse_env("# c\n\nA=1\nB='two words'\nC=\"x=y\"\nbroken line\n")
        self.assertEqual(env, {"A": "1", "B": "two words", "C": "x=y"})

    def test_file_rules_reject_a_world_readable_environment_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            envfile = Path(tmp) / "talim.env"
            envfile.write_text("A=1\n")
            media = Path(tmp) / "media"
            media.mkdir(mode=0o700)
            env = {"DJANGO_PRIVATE_MEDIA_ROOT": str(media)}
            os.chmod(envfile, 0o644)
            report = self.pre.Report()
            self.pre.check_files(str(envfile), env, report)
            self.assertTrue(any(r[0] == "FAIL" and "world" in r[1] for r in report.rows))
            os.chmod(envfile, 0o640)
            os.chmod(media, 0o755)
            report = self.pre.Report()
            self.pre.check_files(str(envfile), env, report)
            self.assertTrue(any(r[0] == "FAIL" and "document store" in r[1] for r in report.rows))


class StagingFiles(SimpleTestCase):
    def test_scripts_are_syntactically_valid_and_executable(self):
        for name in ("release.sh", "verify_release.sh", "verify_preflight.sh"):
            path = STAGING / name
            self.assertTrue(os.access(path, os.X_OK), name)
            self.assertEqual(subprocess.run(["bash", "-n", str(path)]).returncode, 0, name)
        for name in ("preflight.py", "smoke_remote.py"):
            compile((STAGING / name).read_text(), name, "exec")

    def test_release_script_guard_rails_are_present(self):
        text = (STAGING / "release.sh").read_text()
        for needle in ("refusing to run as root", "backup failed - nothing was changed", "NOT reverted", "migrate --plan", "healthy", "RELEASE_FAILED_ROLLED_BACK",
                       'echo "$prev_before"', "X-Forwarded-Proto: https", "HEALTH_HOST"):
            self.assertIn(needle, text)
        self.assertNotIn("--no-input", text)
        self.assertIsNone(re.search(r"\bsudo\b(?!.*#)", text.replace("sudo systemctl restart talim-gunicorn", "")), "release.sh must not call sudo itself")

    def test_release_script_refuses_root_before_doing_anything(self):
        if os.getuid() != 0:
            self.skipTest("only meaningful when the tests run as root")
        env = {"PATH": os.environ["PATH"], "RELEASES_DIR": "/nonexistent", "CURRENT_LINK": "/nonexistent/c", "HEALTH_URL": "http://127.0.0.1:1/",
               "RESTART_CMD": "true", "PRE_BACKUP_CMD": "true"}
        r = subprocess.run([str(STAGING / "release.sh"), "deploy", "x"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("root", r.stderr)

    def test_release_script_demands_its_configuration(self):
        r = subprocess.run([str(STAGING / "release.sh"), "status"], env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_no_secret_shaped_values_in_staging_files(self):
        pattern = re.compile(r"(BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{12}|gh[pousr]_[A-Za-z0-9]{20,}|[A-Za-z0-9_-]{43}=)")
        for path in STAGING.iterdir():
            if path.is_file():
                self.assertIsNone(pattern.search(path.read_text()), path.name)

    def test_smoke_script_refuses_untrusted_certificates_unless_told_otherwise(self):
        text = (STAGING / "smoke_remote.py").read_text()
        self.assertIn("ssl.create_default_context()", text)
        self.assertEqual(text.count("CERT_NONE"), 1)
        self.assertIn("if insecure:", text)


class BackupEnvironmentRules(SimpleTestCase):
    """preflight.check_backup_env: the files and values that make the restore check possible without giving the runtime role CREATEDB."""

    def setUp(self):
        import tempfile
        self.pre = _load("preflight")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "backups").mkdir(mode=0o700)
        (root / "media").mkdir()
        self.pass_file = root / "backup.pass"
        self.pass_file.write_text("x" * 40)
        os.chmod(self.pass_file, 0o600)
        self.root = root

    def rows(self, **over):
        values = {"BACKUP_DIR": str(self.root / "backups"), "BACKUP_PASSPHRASE_FILE": str(self.pass_file), "PGUSER": "talim_backup"} | over
        envfile = self.root / "backup.env"
        envfile.write_text("".join(f"{k}={v}\n" for k, v in values.items() if v is not None))
        os.chmod(envfile, 0o640)
        report = self.pre.Report()
        self.pre.check_backup_env(str(envfile), {"DB_USER": "talim_app", "DJANGO_PRIVATE_MEDIA_ROOT": str(self.root / "media")}, report)
        return {name: status for status, name, _d in report.rows}

    def failed(self, rows):
        return {n for n, s in rows.items() if s == "FAIL"} - {"backup role can connect", "backup role rights wrong"}   # the live database probe is not part of these unit tests

    def test_a_correct_file_set_passes_every_file_and_value_rule(self):
        self.assertEqual(self.failed(self.rows()), set())

    def test_the_backup_role_must_not_be_the_runtime_role_or_a_superuser_account(self):
        self.assertIn("backup role must differ from the runtime role", self.failed(self.rows(PGUSER="talim_app")))
        self.assertIn("backup role must not be a superuser account", self.failed(self.rows(PGUSER="postgres")))

    def test_the_passphrase_file_rules(self):
        os.chmod(self.pass_file, 0o644)
        self.assertIn("passphrase file must be mode 0600", self.failed(self.rows()))
        os.chmod(self.pass_file, 0o600)
        self.pass_file.write_text("short")
        self.assertIn("passphrase file is shorter than 20 characters", self.failed(self.rows()))
        inside = self.root / "backups" / "p"
        inside.write_text("x" * 40)
        os.chmod(inside, 0o600)
        self.assertIn("passphrase file lies inside the backup directory or the document store", self.failed(self.rows(BACKUP_PASSPHRASE_FILE=str(inside))))

    def test_missing_variables_and_open_directories_fail(self):
        self.assertIn("backup variables missing", self.failed(self.rows(PGUSER=None)))
        os.chmod(self.root / "backups", 0o755)
        self.assertIn("backup directory must be 0700", self.failed(self.rows()))

    def test_a_world_readable_backup_environment_file_fails(self):
        self.rows()
        os.chmod(self.root / "backup.env", 0o644)
        report = self.pre.Report()
        self.pre.check_backup_env(str(self.root / "backup.env"), {"DB_USER": "talim_app"}, report)
        self.assertTrue(any(s == "FAIL" and "world-accessible" in n for s, n, _d in report.rows))
