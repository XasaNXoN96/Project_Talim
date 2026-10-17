"""The scheduling files: complete (every job has a timer and a cron line), unprivileged, free of secrets, and syntactically valid."""
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.core import jobs

DEPLOY = Path(settings.BASE_DIR) / "deploy"
SYSTEMD = DEPLOY / "systemd"
DOCS = Path(settings.BASE_DIR).parent / "docs" / "SCHEDULER.md"
PERIODIC = {n for n, s in jobs.JOBS.items() if s["every"]}


def text(path):
    return path.read_text()


class Files(SimpleTestCase):
    def test_every_periodic_job_has_a_timer_a_cron_line_and_a_mention_in_the_docs_and_on_demand_jobs_have_no_timer(self):
        cron = text(SYSTEMD / "crontab.example")
        doc = text(DOCS)
        for name in jobs.JOBS:
            timer = SYSTEMD / f"talim-{name}.timer"
            if name in PERIODIC:
                self.assertTrue(timer.exists(), name)
                cmd = jobs.command_of(name)
                self.assertIn(f"Unit=talim-job@{cmd}.service", text(timer))
                self.assertEqual(len(re.findall(rf"manage\.py {cmd} ", cron)), 1, name)
            else:
                self.assertFalse(timer.exists(), f"{name} is on demand: no timer")
                self.assertNotIn(f"manage.py {jobs.command_of(name)} ", cron)
            self.assertIn(name, doc, name)
        extra = {p.name[len("talim-"):-len(".timer")] for p in SYSTEMD.glob("talim-*.timer")} - PERIODIC
        self.assertEqual(extra, set())  # no timer for a job the application does not know

    def test_the_timer_schedule_matches_the_interval_the_status_page_expects(self):
        # a job is "overdue" after 2 x its interval: the schedule must run at least that often
        every = {"send_task_reminders": "*:07:00", "purge_employee_imports": "*:00/15:00", "purge_throttles": "*:37:00", "check_scanner": "*:00/5:00",
                 "clear_expired_sessions": "03:23:00", "verify_document_files": "Sun *-*-* 04:11:00",
                 "backup_create": "*-*-* 02:15:00", "backup_restore_check": "Sun *-*-* 05:40:00"}
        for name, fragment in every.items():
            self.assertIn(fragment, text(SYSTEMD / f"talim-{name}.timer"), name)
        self.assertEqual({n for n in PERIODIC}, set(every))

    def test_units_run_unprivileged_with_absolute_paths_hardening_and_no_secrets(self):
        unit = text(SYSTEMD / "talim-job@.service")
        self.assertRegex(unit, r"(?m)^User=talim$")
        self.assertNotRegex(unit, r"(?m)^User=root")
        for line in re.findall(r"(?m)^(ExecStart|WorkingDirectory|EnvironmentFile)=(.*)$", unit):
            for path in re.findall(r"(/[\w./@%-]+)", line[1]):
                self.assertTrue(path.startswith("/"), line)
        self.assertIn("EnvironmentFile=/etc/talim/talim.env", unit)
        self.assertIn("ExecStart=/srv/talim/backend/.venv/bin/python /srv/talim/backend/manage.py %i", unit)
        for must in ("NoNewPrivileges=true", "ProtectSystem=strict", "PrivateTmp=true", "ProtectHome=true", "OnFailure=talim-job-failed@%n.service", "UMask=0077", "TimeoutStartSec="):
            self.assertIn(must, unit)
        self.assertIn("Type=oneshot", unit)

    def test_nothing_in_the_deploy_files_looks_like_a_secret_value(self):
        files = [f for d in (SYSTEMD, DEPLOY / "tmpfiles.d", DEPLOY / "logrotate") for f in d.rglob("*") if f.is_file()] + [DEPLOY / "alert.sh.example"]
        self.assertGreaterEqual(len(files), 10)
        pattern = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[=:]\s*['\"]?[A-Za-z0-9+/_\-]{6,}")
        for f in files:
            for n, line in enumerate(text(f).splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(pattern.search(line), f"{f.name}:{n}")

    def test_cron_lines_are_locked_logged_privately_and_use_absolute_paths(self):
        lines = [l for l in text(SYSTEMD / "crontab.example").splitlines() if l and not l.startswith("#") and not re.match(r"^[A-Z]+=", l)]
        self.assertEqual(len(lines), len(PERIODIC))
        for l in lines:
            self.assertIn("umask 077;", l)
            self.assertIn("/usr/bin/flock -n /run/talim/", l)
            self.assertIn("/srv/talim/backend/.venv/bin/python /srv/talim/backend/manage.py ", l)
            self.assertIn(". /etc/talim/talim.env", l)
            self.assertRegex(l, r">> /var/log/talim/[\w]+\.log 2>&1$")
            self.assertNotIn("/tmp", l)
            self.assertNotRegex(l, r"(?i)password=|secret=|token=")
        self.assertIn("MAILTO=", text(SYSTEMD / "crontab.example"))
        self.assertIn("never root", text(SYSTEMD / "crontab.example"))

    def test_runtime_directories_and_log_rotation_belong_to_the_application_user_with_closed_modes(self):
        tmpfiles = text(DEPLOY / "tmpfiles.d" / "talim.conf")
        self.assertRegex(tmpfiles, r"(?m)^d /run/talim\s+0750 talim talim")
        self.assertRegex(tmpfiles, r"(?m)^d /var/log/talim\s+0750 talim talim")
        self.assertIn("create 0640 talim talim", text(DEPLOY / "logrotate" / "talim"))

    def test_the_verification_script_passes_on_the_committed_files(self):
        if not shutil.which("systemd-analyze"):
            self.skipTest("systemd-analyze is not installed here: unit files were not machine-checked")
        r = subprocess.run([str(DEPLOY / "verify_deploy_files.sh")], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("clean", r.stdout)
        self.assertIn("ok", r.stdout)

    def test_backup_jobs_get_their_own_writable_path_and_environment_file_and_nothing_secret(self):
        for cmd in ("run_backup", "run_restore_check"):
            drop = text(SYSTEMD / f"talim-job@{cmd}.service.d" / "backup.conf")
            self.assertIn("EnvironmentFile=-/etc/talim/backup.env", drop)
            self.assertRegex(drop, r"(?m)^ReadWritePaths=/var/backups/talim$")
            self.assertRegex(drop, r"(?m)^TimeoutStartSec=3h$")
        cron = text(SYSTEMD / "crontab.example")
        for line in [l for l in cron.splitlines() if "run_backup" in l or "run_restore_check" in l]:
            self.assertIn(". /etc/talim/backup.env", line)

    def test_the_alert_hook_is_optional_and_the_example_holds_no_recipient_or_credentials(self):
        failed = text(SYSTEMD / "talim-job-failed@.service")
        self.assertIn("ExecStart=-/etc/talim/alert.sh %i", failed)  # the dash: a missing script is not an error
        example = text(DEPLOY / "alert.sh.example")
        self.assertIn("/etc/talim/alert.address", example)
        self.assertNotRegex(example, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(example, r"(?i)password|secret|token")
