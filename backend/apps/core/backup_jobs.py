"""Backups as tracked jobs: the shell scripts in deploy/backup do the work; these wrappers only start them, interpret their exit
codes and record the outcome (apps.core.jobs).

Security properties kept on purpose:
  * the scripts' STDOUT is parsed for one fixed summary line and otherwise dropped; their STDERR goes straight to the service journal
    (the scripts print no secrets), it is never copied into the run record, the job log or the exception message;
  * the run record keeps counts, the backup folder name and an exception class: nothing else;
  * credentials are never invented here: PGPASSFILE/PGPASSWORD and the passphrase FILE PATH must already be in the environment
    (an environment file readable only by the service user); only host/port/user/database names default from Django's settings;
  * "success" means exactly what the script guarantees: backup_create = archive written, manifest verified, dump/archive readable;
    backup_restore_check = the newest backup was restored into a scratch database/directory and passed every check.
    Neither says the copy is stored away from this server."""
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from .jobs import JobSkipped, TrackedCommand

EXIT_BUSY = 75
EXIT_PRUNE_FAILED = 4
OFFSITE_TIMEOUT = 3 * 60 * 60
TIMEOUT = 3 * 60 * 60  # seconds; a hung dump is killed and recorded as a failure


def script(name):
    return Path(settings.BASE_DIR) / "deploy" / "backup" / name


def child_env(required):
    """Environment for the scripts: what the service already has, plus non-secret defaults taken from the Django settings."""
    db = settings.DATABASES["default"]
    env = dict(os.environ)
    env.setdefault("PGHOST", str(db.get("HOST") or ""))
    env.setdefault("PGPORT", str(db.get("PORT") or ""))
    env.setdefault("PGUSER", str(db.get("USER") or ""))
    env.setdefault("PGDATABASE", str(db.get("NAME") or ""))
    env.setdefault("PRIVATE_MEDIA_ROOT", str(settings.PRIVATE_MEDIA_ROOT))
    env.setdefault("BACKEND_DIR", str(settings.BASE_DIR))
    env.setdefault("PYTHON", sys.executable)
    missing = [k for k in required if not env.get(k)]
    if missing:
        raise CommandError("backup configuration is incomplete: set " + ", ".join(missing) + " in the service environment.")
    if not (env.get("PGPASSFILE") or env.get("PGPASSWORD")):
        env.pop("PGPASSWORD", None)  # nothing to add: libpq falls back to ~/.pgpass or peer authentication
    return env


def run_script(name, argv, env):
    """-> (exit code, stdout). stderr is inherited (journal). Raises CommandError on a timeout or a missing script."""
    path = script(name)
    if not path.is_file():
        raise CommandError(f"{name} is missing from the installation.")
    try:
        done = subprocess.run([str(path), *argv], env=env, stdout=subprocess.PIPE, text=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise CommandError(f"{name} did not finish within {TIMEOUT // 3600} hours and was stopped.") from None
    return done.returncode, done.stdout


def summary(stdout, tag):
    """The one machine-readable line (BACKUP_OK / RESTORE_OK ...) as a dict, or None."""
    for line in stdout.splitlines():
        if line.startswith(tag + " "):
            return dict(re.findall(r"(\w+)=(\S+)", line))
    return None


def run_offsite(command, name, backup_dir):
    """Optional hand-over of a finished backup to a mechanism the OWNER chose (BACKUP_OFFSITE_COMMAND in backup.env). This is an extension point, not a
    provider: nothing here knows where the copy goes. The command is run WITHOUT a shell, as `<command> <backup folder name>`, with a minimal environment
    (PATH, BACKUP_DIR, BACKUP_NAME and OFFSITE_* names only): the database password, the OTP keys, the Django secret and the PATH of the passphrase file
    are NOT passed on. The file must be absolute, executable and not writable by anyone but its owner. A failure makes the whole job a failure, so
    the existing job status and alerts show it; the local copy is kept either way."""
    path = Path(command)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise CommandError("BACKUP_OFFSITE_COMMAND must be the absolute path of an executable file.")
    if path.stat().st_mode & 0o022:
        raise CommandError("BACKUP_OFFSITE_COMMAND must not be writable by group or others.")
    child = {"PATH": "/usr/local/bin:/usr/bin:/bin", "BACKUP_DIR": str(backup_dir), "BACKUP_NAME": name}
    child.update({k: v for k, v in os.environ.items() if k.startswith("OFFSITE_")})
    # Own process group so that a timeout can stop everything the command started; stdout AND stderr are discarded: the command is the owner's code and
    # may print tokens or file names, so nothing it says reaches our journal (it should log by itself, e.g. with `logger`). Only its exit code is used.
    proc = subprocess.Popen([str(path), name], env=child, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        returncode = proc.wait(timeout=OFFSITE_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        raise CommandError(f"backup {name} was created locally, but the offsite step did not finish within {OFFSITE_TIMEOUT // 3600 or 1} hour(s) and was stopped.") from None
    if returncode != 0:
        raise CommandError(f"backup {name} was created locally, but the offsite step failed (exit code {returncode}); it is NOT stored away from this server.")


class BackupCreate(TrackedCommand):
    help = (
        "Create an encrypted backup (deploy/backup/backup.sh) and record the run. Success = the archive was written, its manifest verified "
        "and the dump/archive could be read back; it is NOT a restore test and says nothing about where the copy is stored."
    )
    job_name = "backup_create"

    def run_job(self, run, *args, **options):
        env = child_env(["BACKUP_DIR", "BACKUP_PASSPHRASE_FILE"])
        code, out = run_script("backup.sh", [], env)
        if code == EXIT_BUSY:
            raise JobSkipped()
        info = summary(out, "BACKUP_OK")
        prune_failed = code == EXIT_PRUNE_FAILED and info is not None
        if code != 0 and not prune_failed or info is None:
            raise CommandError(f"backup.sh failed (exit code {code}); nothing was kept.")
        run.processed = int(info.get("files", 0))
        run.note = info.get("name", "")[:80]
        offsite = (os.environ.get("BACKUP_OFFSITE_COMMAND") or "").strip()
        retention = (f"backup {info.get('name', '')} was created and is kept, but retention failed: {info.get('prune_failed', '?')} old copy(ies) could not be "
                     "deleted (permissions or a damaged directory); the disk will fill up until this is fixed.")
        if offsite:  # a failed retention must not leave the NEW copy without its off-server hand-over; "offsite=ok" only means the command exited 0
            try:
                run_offsite(offsite, info.get("name", ""), env["BACKUP_DIR"])
            except CommandError as exc:
                raise CommandError(f"{exc} Also, retention also failed: {info.get('prune_failed', '?')} old copy(ies) could not be deleted.") if prune_failed else exc
            run.note = (run.note + " offsite=ok")[:80]
        if prune_failed:
            raise CommandError(retention)
        self.stdout.write(f"backup written: {run.note} files={run.processed}")


class RestoreCheck(TrackedCommand):
    help = (
        "Restore the NEWEST complete backup into a scratch database and directory (deploy/backup/restore_check.sh) and record the run. "
        "Success = every check passed on the scratch copy; the live database and files are never touched."
    )
    job_name = "backup_restore_check"

    def run_job(self, run, *args, **options):
        env = child_env(["BACKUP_DIR", "BACKUP_PASSPHRASE_FILE"])
        backups = sorted(p for p in Path(env["BACKUP_DIR"]).glob("talim-*Z") if p.is_dir() and (p / "MANIFEST.sha256").is_file())
        if not backups:
            raise CommandError("no complete backup found to check.")
        env = {**env, "MARK_VERIFIED": "1"}  # a successful check marks THIS copy as proven restorable (retention then never deletes it)
        code, out = run_script("restore_check.sh", [str(backups[-1])], env)
        if code == EXIT_BUSY:
            raise JobSkipped()
        info = summary(out, "RESTORE_OK")
        if code != 0 or info is None:
            raise CommandError(f"restore check failed (exit code {code}).")
        run.processed = int(info.get("documents", 0))
        run.note = info.get("name", "")[:80]
        self.stdout.write(f"restore verified on a scratch copy: {run.note} documents={run.processed}")
