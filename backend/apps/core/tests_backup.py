"""Backup and restore, for real: pg_dump, openssl, tar and pg_restore on the test PostgreSQL, a throw-away passphrase and fictional data.

Each test builds its own temporary backup directory, passphrase file and COPY of the document store (only the files the database refers
to, plus planted secrets that must be excluded). Nothing here touches a live database or a real store."""
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import threading
import fcntl
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase

from apps.core import backup_jobs, jobs
from apps.core.acceptance import World
from apps.core.models import JobRun
from apps.documents.models import DocumentVersion
from apps.tasks.models import TaskAttachment

BACKEND = Path(settings.BASE_DIR)
SCRIPTS = BACKEND / "deploy" / "backup"
PLANTED = {".env": "DJANGO_SECRET_KEY=planted-secret-key-value", "leak.key": "-----BEGIN PRIVATE KEY----- planted", "cert.pem": "planted-pem", "app.log": "planted log line", "x.tmp": "planted temp"}


def run_script(name, *args, env, timeout=300):
    return subprocess.run([str(SCRIPTS / name), *args], env=env, capture_output=True, text=True, timeout=timeout)


class Base(TransactionTestCase):
    """TransactionTestCase: pg_dump runs in another process and only sees COMMITTED rows. A flush also deletes the one set of rows a
    migration creates (the default document categories), so setUp recreates them the same way the migration does."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="talim-test-backup-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backup_dir = self.tmp / "backups"
        self.backup_dir.mkdir(mode=0o700)
        keydir = Path(tempfile.mkdtemp(prefix="talim-test-keys-"))
        self.addCleanup(shutil.rmtree, keydir, ignore_errors=True)
        self.passphrase = secrets.token_urlsafe(40)  # throw-away, protects nothing
        self.pass_file = self.write_secret(keydir / "backup.pass", self.passphrase)
        from importlib import import_module

        from django.apps import apps as django_apps

        import_module("apps.documents.migrations.0002_default_categories").create(django_apps, None)
        self.world = World()  # users, documents (general + confidential), a task attachment, fictional
        from apps.accounts.tests_twofactor import enrol

        enrol(self.world.users["admin"])  # an administrator with a confirmed authenticator device (its secret is encrypted with the test-only key)
        self.media = self.tmp / "media"
        self.media.mkdir(mode=0o700)
        for v in [*DocumentVersion.objects.all(), *TaskAttachment.objects.all()]:  # a store that holds exactly what the rows refer to
            target = self.media / v.file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(settings.PRIVATE_MEDIA_ROOT) / v.file.name, target)
        for name, body in PLANTED.items():
            (self.media / name).write_text(body)
        db = connection.settings_dict
        self.db_password = db["PASSWORD"]
        self.env = {
            **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")},
            "BACKUP_DIR": str(self.backup_dir), "BACKUP_PASSPHRASE_FILE": str(self.pass_file), "PRIVATE_MEDIA_ROOT": str(self.media),
            "PGHOST": db["HOST"] or "127.0.0.1", "PGPORT": str(db["PORT"] or 5432), "PGUSER": db["USER"], "PGPASSWORD": self.db_password, "PGDATABASE": db["NAME"],
            # for the application commands run against the restored copy (config.settings.dev needs these)
            "BACKEND_DIR": str(BACKEND), "PYTHON": str(BACKEND / ".venv" / "bin" / "python") if (BACKEND / ".venv" / "bin" / "python").exists() else shutil.which("python3"),
            "DB_USER": db["USER"], "DB_PASSWORD": self.db_password, "DB_HOST": db["HOST"] or "127.0.0.1", "DB_PORT": str(db["PORT"] or 5432),
            "DJANGO_SECRET_KEY": "test-only-key-protects-nothing-0123456789-0123456789-0123456789", "OTP_ENCRYPTION_KEYS": ",".join(settings.OTP_ENCRYPTION_KEYS),
            "DJANGO_ALLOWED_HOSTS": "localhost", "DJANGO_DEBUG": "1", "DJANGO_SETTINGS_MODULE": "config.settings.dev",
        }
        self.restore_db = f"talim_restore_check_t{secrets.token_hex(3)}"
        self.addCleanup(subprocess.run, ["dropdb", "--if-exists", self.restore_db], env=self.env, capture_output=True)

    @staticmethod
    def write_secret(path, text):
        path.write_text(text)
        path.chmod(0o600)
        return path

    def backup(self, **extra):
        return run_script("backup.sh", env={**self.env, **extra})

    def make_backup(self):
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.complete()[-1]

    def complete(self):
        return sorted(p for p in self.backup_dir.glob("talim-*Z") if p.is_dir())

    def restore(self, src, **extra):
        files = self.tmp / f"restore-files-{secrets.token_hex(3)}"
        files.mkdir(mode=0o700)
        self.restored_files = files
        env = {**self.env, "RESTORE_DB": self.restore_db, "RESTORE_FILES": str(files), **extra}
        return run_script("restore_check.sh", str(src), env=env)

    def db_exists(self, name):
        r = subprocess.run(["psql", "-d", "postgres", "-Atc", f"select 1 from pg_database where datname='{name}'"], env=self.env, capture_output=True, text=True)
        return r.stdout.strip() == "1"

    def dec(self, path):
        return subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-pass", f"file:{self.pass_file}", "-in", str(path)], capture_output=True).stdout

    def live_counts(self):
        from apps.documents.models import Document

        return (Document.objects.count(), DocumentVersion.objects.count(), TaskAttachment.objects.count())


class CreatingABackup(Base):
    def test_the_backup_is_complete_encrypted_readable_and_leaves_no_plaintext_or_extra_files(self):
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (b,) = self.complete()
        self.assertEqual(sorted(p.name for p in b.iterdir()), ["INFO.txt", "MANIFEST.sha256", "db.dump.enc", "files.tar.enc"])
        self.assertEqual([p for p in self.backup_dir.iterdir() if p.name.endswith(".partial")], [])
        self.assertRegex(r.stdout, r"BACKUP_OK name=talim-\d{8}T\d{6}Z db_bytes=\d+ files=\d+")
        info = (b / "INFO.txt").read_text()
        self.assertIn("readable_check=ok", info)
        self.assertIn("restore_verified=no", info)  # created and readable is NOT restorable: the file says so
        raw_db, raw_files = (b / "db.dump.enc").read_bytes(), (b / "files.tar.enc").read_bytes()
        for raw in (raw_db, raw_files):
            self.assertTrue(raw.startswith(b"Salted__"))
        self.assertNotIn(b"PGDMP", raw_db[:64])
        self.assertNotIn(b"accounts_user", raw_db)
        self.assertNotIn(b"ustar", raw_files[:600])
        self.assertTrue(self.dec(b / "db.dump.enc").startswith(b"PGDMP"))
        for p in b.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600, p.name)
        self.assertEqual(stat.S_IMODE(b.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.backup_dir.stat().st_mode), 0o700)
        r2 = subprocess.run(["sha256sum", "--check", "--quiet", "MANIFEST.sha256"], cwd=b, capture_output=True, text=True)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_planted_secrets_logs_and_temp_files_are_excluded_and_no_secret_reaches_the_output(self):
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stderr)
        (b,) = self.complete()
        listing = subprocess.run(["tar", "--list"], input=self.dec(b / "files.tar.enc"), capture_output=True).stdout.decode()
        for planted in PLANTED:
            self.assertNotIn(planted, listing)
        self.assertIn(".pdf", listing)  # the documents themselves are there
        archive = self.dec(b / "files.tar.enc") + self.dec(b / "db.dump.enc")
        for body in PLANTED.values():
            self.assertNotIn(body.encode(), archive)
        for secret in (self.passphrase, self.db_password, settings.SECRET_KEY, ",".join(settings.OTP_ENCRYPTION_KEYS)):
            self.assertNotIn(secret, r.stdout + r.stderr)
            self.assertNotIn(secret.encode(), archive)  # keys and passwords are not inside the archive they would open
            self.assertNotIn(secret.encode(), (b / "db.dump.enc").read_bytes() + (b / "files.tar.enc").read_bytes())
        self.assertNotIn(self.passphrase, (b / "INFO.txt").read_text())

    def test_the_database_dump_is_a_consistent_snapshot_that_pg_restore_can_read(self):
        b = self.make_backup()
        r = subprocess.run(["pg_restore", "--list"], input=self.dec(b / "db.dump.enc"), capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"documents_documentversion", r.stdout)

    def test_repeating_it_is_safe_and_retention_keeps_only_the_newest_complete_backups(self):
        names = []
        for _ in range(3):
            r = self.backup(BACKUP_KEEP="2")
            self.assertEqual(r.returncode, 0, r.stderr)
            names.append(re.search(r"name=(talim-\S+)", r.stdout).group(1))
        self.assertEqual(len(set(names)), 3)  # same-second runs still get distinct names
        self.assertEqual([p.name for p in self.complete()], sorted(names)[-2:])
        self.assertIn("pruned", r.stdout)

    def test_a_failed_run_keeps_nothing_and_never_costs_an_existing_backup(self):
        good = [self.make_backup()]
        good.append(self.make_backup())
        r = self.backup(PGDATABASE="no_such_database_for_test", BACKUP_KEEP="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("BACKUP_FAILED", r.stderr)
        self.assertEqual(self.complete(), good)  # nothing pruned although KEEP=1 would have deleted one
        self.assertEqual([p.name for p in self.backup_dir.iterdir() if p.name.endswith(".partial")], [])
        for secret in (self.passphrase, self.db_password):
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_a_crash_in_the_middle_leaves_no_partial_directory(self):
        broken = {**self.env, "PATH": str(self.tmp / "bin") + os.pathsep + self.env["PATH"]}
        (self.tmp / "bin").mkdir()
        tar = self.tmp / "bin" / "tar"
        tar.write_text("#!/bin/sh\necho 'simulated disk failure' >&2\nexit 2\n")
        tar.chmod(0o755)
        r = run_script("backup.sh", env=broken)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(list(self.backup_dir.glob("talim-*")), [])

    def test_misconfiguration_is_refused_before_anything_is_written(self):
        keydir = self.pass_file.parent
        cases = {
            "short passphrase": {"BACKUP_PASSPHRASE_FILE": str(self.write_secret(keydir / "short", "tiny"))},
            "wrong mode": {"BACKUP_PASSPHRASE_FILE": str(self._open_file(keydir / "open", self.passphrase))},
            "passphrase inside the backup dir": {"BACKUP_PASSPHRASE_FILE": str(self.write_secret(self.backup_dir / "pass", self.passphrase))},
            "backup dir inside the store": {"BACKUP_DIR": str(self.media / "backups")},
            "store missing": {"PRIVATE_MEDIA_ROOT": str(self.tmp / "nowhere")},
        }
        for label, extra in cases.items():
            r = self.backup(**extra)
            self.assertEqual(r.returncode, 2, (label, r.stdout, r.stderr))
            self.assertIn("configuration error", r.stderr, label)
        loose = self.tmp / "loose"
        loose.mkdir(mode=0o755)
        os.chmod(loose, 0o755)
        self.assertEqual(self.backup(BACKUP_DIR=str(loose)).returncode, 2)  # a readable backup directory is refused
        self.assertEqual(self.complete(), [])
        self.assertNotEqual(run_script("backup.sh", env={k: v for k, v in self.env.items() if k != "PGDATABASE"}).returncode, 0)  # a missing variable is refused too

    def _open_file(self, path, text):
        path.write_text(text)
        path.chmod(0o644)
        return path

    def test_two_backups_at_once_the_second_does_nothing_and_says_so(self):
        lock = open(self.backup_dir / ".backup.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another run is working
        try:
            r = self.backup()
        finally:
            lock.close()
        self.assertEqual(r.returncode, 75)
        self.assertIn("BACKUP_SKIPPED_BUSY", r.stdout)
        self.assertEqual(self.complete(), [])
        self.assertEqual(self.backup().returncode, 0)  # lock released: it works


class RestoringIt(Base):
    def test_restore_into_scratch_database_and_directory_passes_every_check_and_cleans_up(self):
        before = self.live_counts()
        b = self.make_backup()
        leftovers = set(Path(tempfile.gettempdir()).glob("talim-restore-*"))
        r = self.restore(b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("RESTORE_OK name=" + b.name, out)
        self.assertRegex(out, r"documents=2 versions=2 task_attachments=1")  # general + confidential document, one attachment
        self.assertIn("missing=0 mismatched=0 orphans=0", out)  # every row has its file with the right size and SHA-256, and no stray files
        m = re.search(r"access_check documents=(\d+) allowed_ok=(\d+) denied_ok=(\d+) anonymous_ok=(\d+) errors=0", out)
        self.assertIsNotNone(m, out)
        docs, allowed, denied, anon = map(int, m.groups())
        self.assertEqual((docs, allowed, anon), (2, 2, 2))  # the real download view, existing permissions: anonymous refused, allowed people get identical bytes
        self.assertGreaterEqual(denied, 1)  # and somebody without the right is refused
        self.assertIn("two_factor_check devices=1 decryptable=1 accepted=1 failed=0", out)  # the restored 2FA secret opens with the same key, and its code is accepted
        self.assertIn("two_factor_devices=1", out)
        # clean-up: the scratch database and directory are gone, the live data is untouched
        self.assertFalse(self.db_exists(self.restore_db))
        self.assertFalse(self.restored_files.exists())
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("talim-restore-*")), leftovers)
        self.assertEqual(self.live_counts(), before)
        for secret in (self.passphrase, self.db_password):
            self.assertNotIn(secret, out + r.stderr)

    def test_restoring_without_the_right_encryption_key_fails_the_check_and_reveals_nothing(self):
        from cryptography.fernet import Fernet

        b = self.make_backup()
        wrong_key = Fernet.generate_key().decode()
        r = self.restore(b, OTP_ENCRYPTION_KEYS=wrong_key)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout + r.stderr, r"two_factor_check devices=1 decryptable=0 accepted=0 failed=1|1 record\(s\) failed")
        self.assertNotIn("RESTORE_OK", r.stdout)
        for secret in (wrong_key, ",".join(settings.OTP_ENCRYPTION_KEYS), self.passphrase, self.db_password):
            self.assertNotIn(secret, r.stdout + r.stderr)
        self.assertFalse(self.db_exists(self.restore_db))  # and the scratch copy is gone
        ok = self.restore(b)  # the right key again: the very same backup restores fine
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_the_two_factor_check_refuses_to_run_outside_a_scratch_copy(self):
        with self.assertRaises(CommandError):
            call_command("verify_restored_two_factor")

    def test_keep_leaves_the_scratch_copy_for_inspection_and_nothing_else(self):
        b = self.make_backup()
        r = self.restore(b, KEEP="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.db_exists(self.restore_db))
        self.assertTrue(any(self.restored_files.rglob("*.pdf")))

    def test_a_wrong_passphrase_is_refused_and_the_scratch_copy_is_removed(self):
        b = self.make_backup()
        wrong = self.write_secret(self.pass_file.parent / "wrong.pass", secrets.token_urlsafe(40))
        r = self.restore(b, BACKUP_PASSPHRASE_FILE=str(wrong))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("RESTORE_FAILED", r.stderr)
        self.assertNotIn("RESTORE_OK", r.stdout)
        self.assertFalse(self.db_exists(self.restore_db))
        self.assertFalse(self.restored_files.exists())
        for secret in (self.passphrase, wrong.read_text(), self.db_password):
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_a_damaged_archive_is_caught_by_the_manifest_before_anything_is_restored(self):
        b = self.make_backup()
        for victim in ("files.tar.enc", "db.dump.enc"):
            data = bytearray((b / victim).read_bytes())
            data[len(data) // 2] ^= 0xFF
            (b / victim).write_bytes(bytes(data))
            r = self.restore(b)
            self.assertNotEqual(r.returncode, 0, victim)
            self.assertIn("FAILED", r.stdout + r.stderr, victim)
            self.assertNotIn("2/6", r.stdout)  # it never got as far as creating the scratch database
            self.assertFalse(self.db_exists(self.restore_db))
            data[len(data) // 2] ^= 0xFF  # undo for the next round
            (b / victim).write_bytes(bytes(data))

    def test_damage_hidden_behind_a_rewritten_manifest_is_still_caught_later(self):
        b = self.make_backup()
        # truncated database dump + a manifest recomputed by an attacker/bug: decryption itself fails
        data = (b / "db.dump.enc").read_bytes()
        (b / "db.dump.enc").write_bytes(data[:-100])
        subprocess.run("sha256sum db.dump.enc files.tar.enc INFO.txt > MANIFEST.sha256", shell=True, cwd=b, check=True)
        r = self.restore(b)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.db_exists(self.restore_db))
        self.assertFalse(self.restored_files.exists())
        # (1) ciphertext damaged without a rewritten manifest is caught by the manifest; (2) AES-CBC has no authentication, so damage inside
        # a stored document that was re-encrypted properly (and the manifest rewritten) must be caught by the per-file SHA-256 check
        (b / "db.dump.enc").write_bytes(data)
        import io
        import tarfile

        plain = bytearray(self.dec(b / "files.tar.enc"))
        member = next(m for m in tarfile.open(fileobj=io.BytesIO(bytes(plain))).getmembers() if m.name.endswith(".pdf"))
        plain[member.offset_data + 5] ^= 0xFF  # one byte inside a stored document
        subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt", "-pass", f"file:{self.pass_file}", "-out", str(b / "files.tar.enc")],
                       input=bytes(plain), check=True, capture_output=True)
        subprocess.run("sha256sum db.dump.enc files.tar.enc INFO.txt > MANIFEST.sha256", shell=True, cwd=b, check=True)
        r = self.restore(b)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout + r.stderr, r"MISMATCH|mismatched=[1-9]")
        self.assertNotIn("RESTORE_OK", r.stdout)
        self.assertFalse(self.db_exists(self.restore_db))
        self.assertFalse(self.restored_files.exists())

    def test_unsafe_targets_are_refused_so_the_live_database_cannot_be_overwritten(self):
        b = self.make_backup()
        before = self.live_counts()
        for label, extra in {
            "the live database name": {"RESTORE_DB": self.env["PGDATABASE"]},
            "a name that does not say scratch": {"RESTORE_DB": "talim_production"},
            "DB_NAME equals the target": {"RESTORE_DB": "talim_restore_check_same", "DB_NAME": "talim_restore_check_same"},
        }.items():
            r = self.restore(b, **extra)
            self.assertEqual(r.returncode, 2, (label, r.stdout, r.stderr))
        full = self.tmp / "not-empty"
        full.mkdir()
        (full / "x").write_text("x")
        r = run_script("restore_check.sh", str(b), env={**self.env, "RESTORE_DB": self.restore_db, "RESTORE_FILES": str(full)})
        self.assertEqual(r.returncode, 2)
        self.assertEqual((full / "x").read_text(), "x")  # an existing directory is never emptied
        self.assertEqual(run_script("restore_check.sh", str(self.tmp / "none"), env=self.env).returncode, 2)
        self.assertEqual(self.live_counts(), before)

    def test_the_access_check_refuses_to_run_against_anything_but_a_scratch_copy(self):
        with self.assertRaises(CommandError):
            call_command("verify_restored_access")  # this process is the test database: no RESTORE_CHECK, not a scratch name

    def test_a_second_restore_check_at_once_does_nothing(self):
        b = self.make_backup()
        lock = open(self.backup_dir / ".restore.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            r = self.restore(b)
        finally:
            lock.close()
        self.assertEqual(r.returncode, 75)
        self.assertIn("RESTORE_SKIPPED_BUSY", r.stdout)
        self.assertFalse(self.db_exists(self.restore_db))


class AsTrackedJobs(Base):
    def apply_env(self):
        patcher = mock.patch.dict(os.environ, {k: v for k, v in self.env.items() if k not in ("PATH", "HOME")}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def command(self, name, **kw):
        from io import StringIO

        out = StringIO()
        call_command(name, stdout=out, **kw)
        return out.getvalue()

    def test_creating_and_restore_checking_are_recorded_as_two_different_facts(self):
        self.apply_env()
        os.environ["RESTORE_DB"] = self.restore_db
        self.assertEqual(jobs.job_state("backup_create")["state"], "never")
        out = self.command("run_backup")
        run = JobRun.objects.get(name="backup_create")
        self.assertEqual((run.status, run.errors, run.error_class), ("success", 0, ""))
        self.assertRegex(run.note, r"^talim-\d{8}T\d{6}Z$")
        self.assertGreater(run.processed, 0)
        self.assertIn("backup written", out)
        # an archive exists, but nobody has proven that it restores: that row stays "never run"
        self.assertEqual(jobs.job_state("backup_create")["state"], "success")
        self.assertEqual(jobs.job_state("backup_restore_check")["state"], "never")
        self.assertFalse(jobs.is_healthy(jobs.job_state("backup_restore_check")))
        out2 = self.command("run_restore_check")
        run2 = JobRun.objects.get(name="backup_restore_check")
        self.assertEqual((run2.status, run2.processed, run2.note), ("success", 2, run.note))
        self.assertIn("scratch copy", out2)
        self.assertEqual(jobs.job_state("backup_restore_check")["state"], "success")
        self.assertTrue(jobs.is_healthy(jobs.job_state("backup_restore_check")))
        text = " ".join(str(v) for r in JobRun.objects.all() for v in (r.name, r.status, r.error_class, r.note))
        for secret in (self.passphrase, self.db_password):
            self.assertNotIn(secret, text)

    def test_a_failing_backup_is_a_failed_run_with_exit_code_one_and_no_secret_anywhere(self):
        self.apply_env()
        os.environ["PGDATABASE"] = "no_such_database_for_test"
        with self.assertLogs("apps.jobs", level="DEBUG") as cap:
            with self.assertRaises(CommandError) as ctx:
                self.command("run_backup")
        run = JobRun.objects.get(name="backup_create")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_class, "CommandError")
        everything = str(ctx.exception) + "\n".join(cap.output) + run.error_class + run.note
        for secret in (self.passphrase, self.db_password, "no_such_database_for_test"):
            self.assertNotIn(secret, everything)
        self.assertEqual(self.complete(), [])

    def test_missing_configuration_names_the_variables_but_never_their_values(self):
        with mock.patch.dict(os.environ, {"BACKUP_DIR": "", "BACKUP_PASSPHRASE_FILE": ""}, clear=False):
            with self.assertRaises(CommandError) as ctx:
                self.command("run_backup")
        self.assertIn("BACKUP_DIR", str(ctx.exception))
        self.assertIn("BACKUP_PASSPHRASE_FILE", str(ctx.exception))
        self.assertEqual(JobRun.objects.get(name="backup_create").status, "failed")

    def test_a_backup_already_running_is_a_skip_not_a_run(self):
        self.apply_env()
        lock = open(self.backup_dir / ".backup.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            out = self.command("run_backup")
        finally:
            lock.close()
        self.assertIn("skipped", out)
        self.assertEqual(JobRun.objects.filter(name="backup_create").count(), 0)  # the last real result is not overwritten
        self.assertEqual(self.complete(), [])

    def test_the_job_lock_makes_a_concurrent_wrapper_skip_too(self):
        self.apply_env()
        lock_id = jobs.JOBS["backup_create"]["lock"]
        ready, release = threading.Event(), threading.Event()

        def holder():
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", [lock_id])
            ready.set()
            release.wait(10)
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
            connection.close()

        t = threading.Thread(target=holder)
        t.start()
        ready.wait(10)
        try:
            out = self.command("run_backup")
        finally:
            release.set()
            t.join(10)
        self.assertIn("skipped", out)
        self.assertEqual((JobRun.objects.count(), self.complete()), (0, []))

    def test_restore_check_needs_a_complete_backup_and_ignores_unfinished_ones(self):
        self.apply_env()
        with self.assertRaises(CommandError):
            self.command("run_restore_check")  # nothing to check
        unfinished = self.backup_dir / "talim-29990101T000000Z"
        unfinished.mkdir(mode=0o700)  # no manifest: not a complete backup, must not be picked as "newest"
        (self.backup_dir / "talim-29991231T000000Z.partial").mkdir(mode=0o700)
        with self.assertRaises(CommandError):
            self.command("run_restore_check")
        self.assertEqual(JobRun.objects.filter(name="backup_restore_check", status="failed").count(), 2)

    def test_a_hung_script_is_stopped_and_recorded_as_a_failure(self):
        self.apply_env()
        slow = self.tmp / "slow.sh"
        slow.write_text("#!/bin/sh\nsleep 30\n")
        slow.chmod(0o755)
        with mock.patch.object(backup_jobs, "script", return_value=slow), mock.patch.object(backup_jobs, "TIMEOUT", 1):
            with self.assertRaises(CommandError) as ctx:
                self.command("run_backup")
        self.assertIn("did not finish", str(ctx.exception))
        self.assertEqual(JobRun.objects.get(name="backup_create").status, "failed")

    def test_a_wrapper_never_invents_credentials(self):
        with mock.patch.dict(os.environ, {"BACKUP_DIR": "/x", "BACKUP_PASSPHRASE_FILE": "/y"}, clear=False):
            os.environ.pop("PGPASSWORD", None)
            os.environ.pop("PGPASSFILE", None)
            env = backup_jobs.child_env(["BACKUP_DIR"])
        self.assertNotIn("PGPASSWORD", env)
        self.assertNotIn("PGPASSFILE", env)
        self.assertEqual(env["PGUSER"], settings.DATABASES["default"]["USER"])  # names default from settings, secrets do not

    def test_a_stale_backup_is_reported_as_overdue_and_a_fresh_failure_does_not_hide_the_last_success(self):
        import datetime

        from django.utils import timezone

        now = timezone.now()
        JobRun.objects.create(name="backup_create", started_at=now - datetime.timedelta(days=3), finished_at=now - datetime.timedelta(days=3), status="success", processed=5, note="talim-20260101T000000Z")
        s = jobs.job_state("backup_create", now)
        self.assertEqual((s["state"], s["overdue"], s["note"]), ("success", True, "talim-20260101T000000Z"))
        self.assertFalse(jobs.is_healthy(s))  # an old file existing is not "healthy"
        JobRun.objects.create(name="backup_create", started_at=now, finished_at=now, status="failed", errors=0, error_class="CommandError")
        s = jobs.job_state("backup_create", now)
        self.assertEqual((s["state"], s["overdue"]), ("failed", True))
        self.assertEqual(s["last_success"], now - datetime.timedelta(days=3))


class FailureModes(Base):
    """Day 24 audit: interruptions, disk problems, a damaged or incomplete manifest, failed retention, and what the latest VERIFIED copy is protected from."""

    def slow_tar_env(self):
        """A `tar` that hangs, so a run can be interrupted in the middle of creating the archive."""
        bindir = self.tmp / "slowbin"
        bindir.mkdir(exist_ok=True)
        tar = bindir / "tar"
        tar.write_text("#!/bin/sh\nsleep 60\n")
        tar.chmod(0o755)
        return {**self.env, "PATH": str(bindir) + os.pathsep + self.env["PATH"]}

    def interrupted_run(self, sig):
        import signal
        import time
        proc = subprocess.Popen([str(SCRIPTS / "backup.sh")], env=self.slow_tar_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        for _ in range(100):                                   # wait until the partial directory exists, i.e. the run is in the middle of its work
            if any(self.backup_dir.glob("talim-*.partial")):
                break
            time.sleep(0.1)
        self.assertTrue(any(self.backup_dir.glob("talim-*.partial")), "the run never got going")
        os.killpg(proc.pid, sig if isinstance(sig, int) else signal.SIGTERM)
        proc.wait(timeout=30)
        return proc

    def partials(self):
        return sorted(p.name for p in self.backup_dir.glob("talim-*.partial"))

    # -- interruption while creating -------------------------------------------------------------------------------------------------------------------
    def test_a_terminated_run_leaves_no_partial_copy_and_the_previous_one_stays(self):
        import signal
        good = self.make_backup()
        self.interrupted_run(signal.SIGTERM)
        self.assertEqual(self.partials(), [])
        self.assertEqual(self.complete(), [good])

    def test_a_killed_run_leaves_a_partial_directory_that_is_never_offered_and_is_cleaned_by_the_next_run(self):
        import signal
        good = self.make_backup()
        self.interrupted_run(signal.SIGKILL)                  # no trap can run after SIGKILL or a power cut
        self.assertEqual(len(self.partials()), 1)
        self.assertEqual(self.complete(), [good])             # never listed as a finished copy
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.partials(), [], "a stale partial copy was left behind and would pile up until the disk is full")
        self.assertEqual(len(self.complete()), 2)

    def test_the_restore_check_never_picks_an_unfinished_copy(self):
        import signal
        self.make_backup()
        self.interrupted_run(signal.SIGKILL)
        env = {**self.env, "RESTORE_DB": self.restore_db}
        from django.core.management import call_command
        with mock.patch.dict(os.environ, {k: v for k, v in env.items()}), mock.patch("django.core.management.base.connections.close_all"):
            call_command("run_restore_check", "--no-record")
        self.assertFalse(self.db_exists(self.restore_db))

    def test_a_write_failure_such_as_a_full_disk_keeps_nothing_and_costs_no_existing_copy(self):
        good = self.make_backup()
        r = subprocess.run(["bash", "-c", f"ulimit -f 4; exec {SCRIPTS / 'backup.sh'}"], env=self.env, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.partials(), [])
        self.assertEqual(self.complete(), [good])
        self.assertNotIn(self.passphrase, r.stdout + r.stderr)

    # -- manifest and integrity -----------------------------------------------------------------------------------------------------------------------
    def test_a_manifest_that_does_not_list_every_file_is_refused(self):
        b = self.make_backup()
        manifest = b / "MANIFEST.sha256"
        manifest.chmod(0o600)
        lines = manifest.read_text().splitlines()
        manifest.write_text("\n".join(line for line in lines if "INFO.txt" in line) + "\n")      # still valid hashes, but the archives are no longer covered
        r = self.restore(b)
        self.assertNotEqual(r.returncode, 0, "an incomplete manifest must not pass: it would leave the encrypted archives unchecked")
        self.assertIn("manifest", (r.stdout + r.stderr).lower())
        self.assertFalse(self.db_exists(self.restore_db))

    def test_a_manifest_with_foreign_entries_or_paths_is_refused(self):
        b = self.make_backup()
        manifest = b / "MANIFEST.sha256"
        manifest.chmod(0o600)
        manifest.write_text(manifest.read_text() + "0" * 64 + "  ../../etc/hostname\n")
        r = self.restore(b)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("manifest", (r.stdout + r.stderr).lower())

    def test_an_empty_or_missing_manifest_is_refused(self):
        b = self.make_backup()
        (b / "MANIFEST.sha256").chmod(0o600)
        (b / "MANIFEST.sha256").write_text("")
        self.assertNotEqual(self.restore(b).returncode, 0)
        (b / "MANIFEST.sha256").unlink()
        self.assertNotEqual(self.restore(b).returncode, 0)

    def test_every_file_and_directory_of_a_backup_is_private_to_its_owner(self):
        b = self.make_backup()
        for path in [self.backup_dir, *self.backup_dir.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, str(path))
        names = sorted(p.name for p in b.iterdir())
        self.assertEqual(names, ["INFO.txt", "MANIFEST.sha256", "db.dump.enc", "files.tar.enc"])

    # -- retention ------------------------------------------------------------------------------------------------------------------------------------
    def failing_rm_env(self, victim):
        bindir = self.tmp / "rmbin"
        bindir.mkdir(exist_ok=True)
        rm = bindir / "rm"
        rm.write_text(f'#!/bin/sh\ncase "$*" in *{victim}*) echo "rm: cannot remove: Operation not permitted" >&2; exit 1;; esac\nexec /bin/rm "$@"\n')
        rm.chmod(0o755)
        return {**self.env, "PATH": str(bindir) + os.pathsep + self.env["PATH"]}

    def test_when_old_copies_cannot_be_deleted_the_new_copy_is_kept_and_the_failure_is_reported_not_hidden(self):
        old = self.make_backup()
        r = run_script("backup.sh", env={**self.failing_rm_env(old.name), "BACKUP_KEEP": "1"})
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)          # 4 = copy created, retention failed
        self.assertIn("BACKUP_OK", r.stdout)                            # the new copy exists and is announced...
        self.assertIn("prune_failed=1", r.stdout)                       # ...together with the fact that cleaning up failed
        self.assertIn("PRUNE_FAILED", r.stderr)
        self.assertEqual(len(self.complete()), 2)                       # nothing lost, nothing half-deleted
        self.assertEqual(self.partials(), [])

    def test_the_job_wrapper_records_a_failed_retention_as_a_failure_that_names_the_copy(self):
        old = self.make_backup()
        from django.core.management import call_command
        with mock.patch.dict(os.environ, {**self.failing_rm_env(old.name), "BACKUP_KEEP": "1"}), mock.patch("django.core.management.base.connections.close_all"):
            with self.assertRaises(CommandError) as ctx:
                call_command("run_backup", "--no-record")
        self.assertIn("retention", str(ctx.exception).lower())
        self.assertIn("kept", str(ctx.exception).lower())
        self.assertEqual(len(self.complete()), 2)

    def verify(self, b):
        r = self.restore(b, MARK_VERIFIED="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_newest_restore_verified_copy_is_never_pruned_even_when_keep_would_delete_it(self):
        b1 = self.make_backup()
        self.verify(b1)
        self.assertTrue((b1 / "RESTORE_VERIFIED").is_file())
        b2 = self.make_backup()
        self.backup(BACKUP_KEEP="1")
        names = [p.name for p in self.complete()]
        self.assertIn(b1.name, names, "the last copy that was PROVEN restorable must survive while newer ones are unproven")
        self.assertNotIn(b2.name, names)                                # an unproven middle copy is what KEEP=1 may delete
        self.assertEqual(len(names), 2)

    def test_a_failed_restore_check_does_not_mark_the_copy_as_verified(self):
        b = self.make_backup()
        wrong = self.write_secret(self.pass_file.parent / "wrong2.pass", secrets.token_urlsafe(40))
        r = self.restore(b, MARK_VERIFIED="1", BACKUP_PASSPHRASE_FILE=str(wrong))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((b / "RESTORE_VERIFIED").exists())

    # -- the restore side -----------------------------------------------------------------------------------------------------------------------------
    def test_a_busy_restore_check_leaves_no_temporary_directory_behind(self):
        b = self.make_backup()
        tmpdir = self.tmp / "tmpdir"
        tmpdir.mkdir()
        lock = open(self.backup_dir / ".restore.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            r = run_script("restore_check.sh", str(b), env={**self.env, "RESTORE_DB": self.restore_db, "TMPDIR": str(tmpdir)})
        finally:
            lock.close()
        self.assertEqual(r.returncode, 75)
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_stale_restored_files_of_a_killed_check_are_removed_by_the_next_one_but_a_fresh_directory_is_not(self):
        import time
        b = self.make_backup()
        tmpdir = self.tmp / "tmpdir2"
        tmpdir.mkdir()
        stale, fresh = tmpdir / "talim-restore-files-OLD123", tmpdir / "talim-restore-files-NEW123"
        for d in (stale, fresh):
            d.mkdir(mode=0o700)
            (d / "restored-document.pdf").write_text("plaintext of a restored document")
        old = time.time() - 6 * 3600
        os.utime(stale, (old, old))
        r = run_script("restore_check.sh", str(b), env={**self.env, "RESTORE_DB": self.restore_db, "TMPDIR": str(tmpdir)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(stale.exists(), "restored plaintext of a killed earlier check must not stay on disk")
        self.assertTrue(fresh.exists())

    def test_restored_files_keep_private_permissions(self):
        b = self.make_backup()
        r = self.restore(b, KEEP="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for path in self.restored_files.rglob("*"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, str(path))

    def test_a_restore_check_terminated_in_the_middle_removes_its_scratch_database_and_files(self):
        import signal
        import time
        b = self.make_backup()
        bindir = self.tmp / "slowrestore"
        bindir.mkdir()
        shim = bindir / "pg_restore"
        shim.write_text("#!/bin/sh\ncat > /dev/null\nsleep 60\n")
        shim.chmod(0o755)
        files = self.tmp / "restore-files-term"
        files.mkdir(mode=0o700)
        env = {**self.env, "PATH": str(bindir) + os.pathsep + self.env["PATH"], "RESTORE_DB": self.restore_db, "RESTORE_FILES": str(files)}
        proc = subprocess.Popen([str(SCRIPTS / "restore_check.sh"), str(b)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        for _ in range(100):
            if self.db_exists(self.restore_db):
                break
            time.sleep(0.1)
        self.assertTrue(self.db_exists(self.restore_db), "the check never reached the restore step")
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=60)
        time.sleep(0.5)
        self.assertFalse(self.db_exists(self.restore_db))
        self.assertFalse(files.exists())
        self.assertTrue((b / "MANIFEST.sha256").is_file())              # the copy itself is untouched
        self.assertFalse((b / "RESTORE_VERIFIED").exists())


class OffsiteHook(Base):
    """BACKUP_OFFSITE_COMMAND: an extension point for the mechanism the owner will choose. No provider is built in; this only proves the hand-over is safe and visible."""

    def command(self, body="#!/bin/sh\nexit 0\n", mode=0o755):
        path = self.tmp / "offsite.sh"
        path.write_text(body)
        path.chmod(mode)
        return path

    def run_job(self, cmd, **extra):
        from django.core.management import call_command
        env = {**os.environ, **self.env, **extra}
        if cmd is not None:
            env["BACKUP_OFFSITE_COMMAND"] = str(cmd)
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("django.core.management.base.connections.close_all"):
            call_command("run_backup", "--no-record")

    def test_without_the_variable_nothing_is_handed_over(self):
        self.run_job(None)
        self.assertEqual(len(self.complete()), 1)

    def test_the_command_gets_only_the_folder_name_and_a_minimal_environment_without_any_secret(self):
        record = self.tmp / "seen.txt"
        cmd = self.command(f'#!/bin/sh\nenv > "{record}"\necho "ARG=$1" >> "{record}"\n')
        self.run_job(cmd, OFFSITE_TARGET="example-target", OTP_ENCRYPTION_KEYS="must-not-leak-key", DJANGO_SECRET_KEY="must-not-leak-secret")
        seen = record.read_text()
        name = self.complete()[0].name
        self.assertIn(f"ARG={name}", seen)
        self.assertIn(f"BACKUP_NAME={name}", seen)
        self.assertIn("OFFSITE_TARGET=example-target", seen)
        for secret in (self.passphrase, self.db_password, "must-not-leak-key", "must-not-leak-secret", "BACKUP_PASSPHRASE_FILE", "PGPASSWORD", "DB_PASSWORD", "OTP_ENCRYPTION_KEYS"):
            self.assertNotIn(secret, seen)

    def test_a_failing_command_fails_the_job_says_so_and_keeps_the_local_copy(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_job(self.command("#!/bin/sh\nexit 7\n"))
        self.assertIn("offsite step failed", str(ctx.exception))
        self.assertIn("exit code 7", str(ctx.exception))
        self.assertIn("NOT stored away", str(ctx.exception))
        self.assertEqual(len(self.complete()), 1)

    def test_unsafe_or_broken_commands_are_refused_before_anything_is_run(self):
        for bad in (self.command(mode=0o777), self.command(mode=0o644), "relative/path.sh", "/nonexistent/offsite.sh"):
            with self.assertRaises(CommandError, msg=str(bad)):
                self.run_job(bad)
        marker = self.tmp / "ran.txt"
        group_writable = self.command(f'#!/bin/sh\ntouch "{marker}"\n', mode=0o775)
        with self.assertRaises(CommandError):
            self.run_job(group_writable)
        self.assertFalse(marker.exists())

    def failing_rm_path(self, victim):
        bindir = self.tmp / "rmbin"
        bindir.mkdir(exist_ok=True)
        rm = bindir / "rm"
        rm.write_text(f'#!/bin/sh\ncase "$*" in *{victim}*) echo "rm: cannot remove" >&2; exit 1;; esac\nexec /bin/rm "$@"\n')
        rm.chmod(0o755)
        return str(bindir) + os.pathsep + os.environ["PATH"]

    def test_a_failed_retention_does_not_stop_the_new_copy_from_being_handed_over(self):
        old = self.make_backup()
        seen = self.tmp / "handed.txt"
        cmd = self.command(f'#!/bin/sh\necho "$1" > "{seen}"\n')
        with self.assertRaises(CommandError) as ctx:
            self.run_job(cmd, PATH=self.failing_rm_path(old.name), BACKUP_KEEP="1")
        self.assertIn("retention failed", str(ctx.exception))
        self.assertTrue(seen.exists(), "the new copy was never handed over because cleaning up old copies failed")

    def test_the_command_is_never_run_through_a_shell(self):
        marker = self.tmp / "injected.txt"
        cmd = self.command()
        with self.assertRaises(CommandError):
            self.run_job(f"{cmd}; touch {marker}")
        self.assertFalse(marker.exists())
