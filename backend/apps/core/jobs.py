"""Scheduled / background jobs: ONE runner for all of them.

What every job gets from `TrackedCommand`:
  * a PostgreSQL advisory lock per job (cross-process, cross-server): a second run that starts while one is working exits at
    once with code 0 and records nothing (it is not a failure and must not overwrite the real last result);
  * a `JobRun` row: started/finished, processed, errors, and the exception CLASS if it crashed — never messages or data;
  * exit codes for monitoring: 0 = ran and every record was fine (or skipped because another run holds the lock),
    1 = crashed or any record failed;
  * server log lines with job name, counts and exception class only.
Nothing here schedules anything: see docs/SCHEDULER.md."""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import JobRun

logger = logging.getLogger("apps.jobs")

RUNNING_STALE = timedelta(minutes=30)  # "running" longer than this: the process died or hangs -> result unknown
KEEP_RUNS = 200                         # history kept per job
OVERDUE_FACTOR = 2                      # a periodic job is "overdue" when its last success is older than this many intervals

# name -> label, expected interval in minutes (None = on demand: never "overdue"), advisory lock id; "command" = the manage.py command
# when it differs from the job name
JOBS = {
    "send_task_reminders": {"label": _("Topshiriq eslatmalarini yuborish"), "every": 60, "lock": 7_310_001},
    "purge_employee_imports": {"label": _("Import ko‘rib chiqishlarini tozalash"), "every": 15, "lock": 7_310_002},
    "clear_expired_sessions": {"label": _("Muddati o‘tgan sessiyalarni tozalash"), "every": 24 * 60, "lock": 7_310_003},
    "purge_throttles": {"label": _("Urinishlar hisoblagichini tozalash"), "every": 60, "lock": 7_310_004},
    "check_scanner": {"label": _("Antivirus xizmatini tekshirish"), "every": 5, "lock": 7_310_005},
    "verify_document_files": {"label": _("Hujjat fayllari yaxlitligini tekshirish"), "every": 7 * 24 * 60, "lock": 7_310_006},
    "scan_documents": {"label": _("Hujjatlarni antivirus bilan qayta tekshirish"), "every": None, "lock": 7_310_007},
    # Two DIFFERENT facts about backups: an archive was written and is readable (backup_create), and a restore of it into a scratch
    # database and directory was actually verified (backup_restore_check). Neither says the copy is off this server.
    "backup_create": {"command": "run_backup", "label": _("Zaxira nusxa yaratildi (arxiv o‘qiladi)"), "every": 24 * 60, "lock": 7_310_008},
    "backup_restore_check": {"command": "run_restore_check", "label": _("Zaxira nusxadan tiklash tekshirildi"), "every": 7 * 24 * 60, "lock": 7_310_009},
}


class JobSkipped(Exception):
    """Raised by run_job when the work was not started because something else is already doing it (not a failure, not a run)."""


def _try_lock(lock_id):
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
        return cur.fetchone()[0]


def _unlock(lock_id):
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", [lock_id])


def _prune(name):
    old = JobRun.objects.filter(name=name).order_by("-started_at").values_list("pk", flat=True)[KEEP_RUNS:]
    ids = list(old)
    if ids:
        JobRun.objects.filter(pk__in=ids).delete()


class TrackedCommand(BaseCommand):
    """Subclass, set `job_name` (a key of JOBS) and implement `run_job(run, *args, **options)`; use run.processed / run.errors."""

    job_name = ""
    LOCK_ID = 0  # filled in from JOBS for every subclass (class attribute: the reminder tests read Command.LOCK_ID)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.job_name:
            cls.LOCK_ID = JOBS[cls.job_name]["lock"]

    def run_job(self, run, *args, **options):  # pragma: no cover - interface
        raise NotImplementedError

    def add_arguments(self, parser):
        parser.add_argument("--no-record", action="store_true", help="run once without the job lock and without writing a run record (used on scratch copies)")

    def handle(self, *args, **options):
        name = self.job_name
        if options.get("no_record"):
            run = JobRun(name=name)
            self.run_job(run, *args, **options)
            if run.errors:
                raise CommandError(f"{name}: {run.errors} record(s) failed, {run.processed} processed.")
            return
        if not _try_lock(self.LOCK_ID):
            logger.info("job=%s skipped: another run holds the lock", name)
            self.stdout.write("another run is in progress: skipped")
            return
        run = JobRun.objects.create(name=name)
        try:
            self.run_job(run, *args, **options)
        except JobSkipped:
            run.delete()  # nothing was done: no record, so the last real result stays the last result
            logger.info("job=%s skipped: the work is already being done elsewhere", name)
            self.stdout.write("another run is in progress: skipped")
            return  # (the lock is released in `finally`)
        except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised as a clean non-zero exit
            self._finish(run, JobRun.Status.FAILED, error_class=type(exc).__name__)
            if isinstance(exc, KeyboardInterrupt):
                raise
            logger.error("job=%s failed processed=%d errors=%d (%s)", name, run.processed, run.errors, type(exc).__name__)
            logger.debug("job=%s failure detail", name, exc_info=True)
            if isinstance(exc, CommandError):
                raise  # a message written by the job's author (no record data)
            raise CommandError(f"{name} failed ({type(exc).__name__}); {run.processed} processed before the failure.") from None
        else:
            if run.errors:
                self._finish(run, JobRun.Status.FAILED, error_class="RecordErrors")
                logger.error("job=%s finished with errors processed=%d errors=%d", name, run.processed, run.errors)
                raise CommandError(f"{name}: {run.errors} record(s) failed, {run.processed} processed.")
            self._finish(run, JobRun.Status.SUCCESS)
            logger.info("job=%s ok processed=%d", name, run.processed)
        finally:
            _unlock(self.LOCK_ID)

    def _finish(self, run, status, error_class=""):
        run.status, run.finished_at, run.error_class = status, timezone.now(), error_class[:60]
        run.save(update_fields=["status", "finished_at", "error_class", "processed", "errors", "note"])
        _prune(self.job_name)


def command_of(name):
    return JOBS[name].get("command", name)


def job_state(name, now=None):
    """State of one job, from its recorded runs only. `state` is one of:
    success | failed | running | never (no run recorded) | unknown (started, never finished, and too long ago).
    `overdue` is True when a periodic job has no recent success (including: never succeeded)."""
    now = now or timezone.now()
    spec = JOBS[name]
    last = JobRun.objects.filter(name=name).order_by("-started_at").first()
    last_ok = JobRun.objects.filter(name=name, status=JobRun.Status.SUCCESS).order_by("-finished_at").first()
    if last is None:
        state = "never"
    elif last.status == JobRun.Status.RUNNING:
        state = "unknown" if now - last.started_at > RUNNING_STALE else "running"
    else:
        state = last.status
    every = spec["every"]
    overdue = bool(every) and (last_ok is None or now - last_ok.finished_at > timedelta(minutes=every * OVERDUE_FACTOR))
    return {
        "name": name, "label": spec["label"], "every": every, "state": state, "overdue": overdue,
        "last_started": last.started_at if last else None, "last_finished": last.finished_at if last else None,
        "last_success": last_ok.finished_at if last_ok else None,
        "processed": last.processed if last and last.status != JobRun.Status.RUNNING else None,
        "errors": last.errors if last and last.status != JobRun.Status.RUNNING else None,
        "error_class": last.error_class if last else "",
        "note": last_ok.note if last_ok else "",
    }


def all_job_states(now=None):
    return [job_state(n, now) for n in JOBS]


def is_healthy(s):
    """For monitoring: success and not overdue. On-demand jobs (every=None) are healthy when never run, and failing otherwise bad."""
    if s["every"] is None:
        return s["state"] in ("success", "never", "running")
    return s["state"] in ("success", "running") and not s["overdue"]
