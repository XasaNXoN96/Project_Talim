"""Background jobs: one runner, honest states, safe repeats, no data or secrets in logs. Fictional data only."""
import datetime
import io
import json
import threading
from unittest import mock

from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ThrottleState, UserSession
from apps.accounts.testing import login_with_two_factor, make_user
from apps.core import jobs
from apps.core.models import JobRun
from apps.notifications.models import Notification
from apps.organization.models import EmployeeImport
from apps.tasks.models import Task

SECRET = "hunter2-TOKEN-abc123"


def run(name, *args, **kw):
    out, err = io.StringIO(), io.StringIO()
    call_command(name, *args, stdout=out, stderr=err, **kw)
    return out.getvalue()


def exit_code(command_class, name):
    """What the shell would see: run_from_argv turns a CommandError into exit status 1 (and closes connections, which a test must not)."""
    with mock.patch("django.core.management.base.connections.close_all"):
        try:
            command_class().run_from_argv(["manage.py", name])
        except SystemExit as exc:
            return exc.code
    return 0


def make_task(title="Hisobot", due=None, assignees=2, **kw):
    creator = kw.pop("creator", None) or make_user(f"c{Task.objects.count()}{timezone.now().timestamp()}".replace(".", ""))
    t = Task.objects.create(title=title, created_by=creator, due_date=due, **kw)
    t.assignees.set([make_user(f"w{t.pk.hex[:8]}{i}") for i in range(assignees)])
    return t


class States(TestCase):
    def test_a_job_that_never_ran_is_never_reported_as_fine(self):
        for s in jobs.all_job_states():
            self.assertEqual((s["state"], s["last_started"], s["last_success"], s["processed"], s["errors"]), ("never", None, None, None, None), s["name"])
            self.assertEqual(jobs.is_healthy(s), s["every"] is None)  # only on-demand jobs may be quiet
        with self.assertRaises(CommandError) as ctx:
            run("job_status")
        self.assertIn("send_task_reminders", str(ctx.exception))
        text = io.StringIO()
        try:
            call_command("job_status", stdout=text)
        except CommandError:
            pass
        self.assertIn("never", text.getvalue())
        self.assertNotIn(" success ", text.getvalue())  # (the column "last_success=-" is fine: it says there was none)

    def test_the_four_states_come_only_from_recorded_runs(self):
        now = timezone.now()
        JobRun.objects.create(name="purge_throttles", started_at=now - datetime.timedelta(minutes=5), finished_at=now - datetime.timedelta(minutes=5), status="success", processed=4)
        JobRun.objects.create(name="purge_employee_imports", started_at=now - datetime.timedelta(minutes=2), finished_at=now - datetime.timedelta(minutes=2), status="failed", errors=1, error_class="OperationalError")
        JobRun.objects.create(name="clear_expired_sessions", started_at=now - datetime.timedelta(hours=3), status="running")  # started, never finished
        JobRun.objects.create(name="check_scanner", started_at=now - datetime.timedelta(minutes=4), finished_at=now - datetime.timedelta(minutes=4), status="success")
        JobRun.objects.create(name="check_scanner", started_at=now - datetime.timedelta(seconds=20), status="running")  # genuinely working
        states = {s["name"]: s for s in jobs.all_job_states(now)}
        self.assertEqual(states["purge_throttles"]["state"], "success")
        self.assertEqual((states["purge_throttles"]["processed"], states["purge_throttles"]["errors"]), (4, 0))
        self.assertEqual((states["purge_employee_imports"]["state"], states["purge_employee_imports"]["error_class"]), ("failed", "OperationalError"))
        self.assertEqual(states["clear_expired_sessions"]["state"], "unknown")
        self.assertEqual(states["check_scanner"]["state"], "running")
        self.assertEqual(states["send_task_reminders"]["state"], "never")
        self.assertTrue(jobs.is_healthy(states["purge_throttles"]))
        self.assertFalse(jobs.is_healthy(states["purge_employee_imports"]))
        self.assertFalse(jobs.is_healthy(states["clear_expired_sessions"]))
        self.assertTrue(jobs.is_healthy(states["check_scanner"]))
        self.assertIsNone(states["clear_expired_sessions"]["processed"])  # a run that never finished has no result to show

    def test_a_periodic_job_with_an_old_success_is_overdue_and_a_failure_does_not_erase_the_last_success(self):
        now = timezone.now()
        JobRun.objects.create(name="send_task_reminders", started_at=now - datetime.timedelta(minutes=89), finished_at=now - datetime.timedelta(minutes=89), status="success")
        self.assertFalse(jobs.job_state("send_task_reminders", now)["overdue"])  # hourly job, 89 minutes: still inside 2 intervals
        JobRun.objects.all().delete()
        JobRun.objects.create(name="send_task_reminders", started_at=now - datetime.timedelta(hours=3), finished_at=now - datetime.timedelta(hours=3), status="success")
        JobRun.objects.create(name="send_task_reminders", started_at=now - datetime.timedelta(minutes=1), finished_at=now, status="failed", errors=2)
        s = jobs.job_state("send_task_reminders", now)
        self.assertEqual((s["state"], s["overdue"]), ("failed", True))
        self.assertEqual(s["last_success"], now - datetime.timedelta(hours=3))

    def test_status_command_exit_codes_and_machine_output(self):
        now = timezone.now()
        for name, spec in jobs.JOBS.items():
            JobRun.objects.create(name=name, started_at=now, finished_at=now, status="success", processed=1)
        self.assertIn("success", run("job_status"))  # every job healthy: no exception, i.e. exit code 0
        data = json.loads(run("job_status", "--json"))
        self.assertEqual({d["name"] for d in data}, set(jobs.JOBS))
        self.assertTrue(all(d["state"] == "success" for d in data))
        JobRun.objects.filter(name="purge_throttles").update(status="failed")
        from apps.core.management.commands.job_status import Command

        self.assertEqual(exit_code(Command, "job_status"), 1)  # the real command-line path
        JobRun.objects.filter(name="purge_throttles").update(status="success")
        self.assertEqual(exit_code(Command, "job_status"), 0)
        self.assertIn("success", run("job_status", "--job", "send_task_reminders"))
        with self.assertRaises(CommandError):
            run("job_status", "--job", "nope")

    def test_history_is_pruned_but_the_newest_runs_survive(self):
        base = timezone.now() - datetime.timedelta(days=400)
        JobRun.objects.bulk_create([JobRun(name="purge_throttles", started_at=base + datetime.timedelta(minutes=i), finished_at=base, status="success") for i in range(jobs.KEEP_RUNS + 20)])
        run("purge_throttles")
        self.assertEqual(JobRun.objects.filter(name="purge_throttles").count(), jobs.KEEP_RUNS)
        newest = JobRun.objects.filter(name="purge_throttles").order_by("-started_at").first()
        self.assertGreater(newest.started_at, timezone.now() - datetime.timedelta(minutes=1))


class Runner(TestCase):
    def test_a_successful_run_is_recorded_with_counts_and_repeating_it_is_harmless(self):
        t = make_task(due=timezone.localdate(), assignees=3)
        out1 = run("send_task_reminders")
        r1 = JobRun.objects.get()
        self.assertEqual((r1.status, r1.processed, r1.errors, r1.error_class), ("success", 3, 0, ""))
        self.assertIsNotNone(r1.finished_at)
        self.assertIn("due_soon=3", out1)
        out2 = run("send_task_reminders")
        self.assertIn("due_soon=0", out2)  # nothing new
        self.assertEqual(Notification.objects.filter(task=t).count(), 3)
        self.assertEqual(JobRun.objects.count(), 2)
        self.assertEqual(jobs.job_state("send_task_reminders")["state"], "success")

    def test_one_failing_record_is_counted_skipped_and_the_rest_still_processed_with_exit_code_one(self):
        t = make_task(due=timezone.localdate(), assignees=3)
        users = list(t.assignees.order_by("username"))
        bad = users[1]
        from apps.notifications import services

        def flaky(user, *a, **kw):
            if user.pk == bad.pk:
                raise RuntimeError(f"db exploded for {SECRET}")
            return services.notify(user, *a, **kw)

        with mock.patch("apps.notifications.management.commands.send_task_reminders.notify", side_effect=flaky):
            with self.assertRaises(CommandError) as ctx:
                run("send_task_reminders")
        self.assertIn("1 record(s) failed", str(ctx.exception))
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertEqual(sorted(Notification.objects.filter(task=t).values_list("user__username", flat=True)), sorted(u.username for u in users if u.pk != bad.pk))
        r = JobRun.objects.get()
        self.assertEqual((r.status, r.processed, r.errors, r.error_class), ("failed", 3, 1, "RecordErrors"))
        # the next run (problem gone) delivers the one that was missed and does not repeat the others
        out = run("send_task_reminders")
        self.assertIn("due_soon=1", out)
        self.assertEqual(Notification.objects.filter(task=t).count(), 3)

    def test_a_crash_is_recorded_by_class_only_and_exits_nonzero_through_the_real_command_line(self):
        with mock.patch("apps.organization.management.commands.purge_employee_imports.wipe_expired", side_effect=ValueError(f"password={SECRET}")):
            with self.assertRaises(CommandError) as ctx:
                run("purge_employee_imports")
            self.assertNotIn(SECRET, str(ctx.exception))
            from apps.organization.management.commands.purge_employee_imports import Command

            self.assertEqual(exit_code(Command, "purge_employee_imports"), 1)
        r = JobRun.objects.filter(name="purge_employee_imports").first()
        self.assertEqual((r.status, r.error_class), ("failed", "ValueError"))
        self.assertNotIn(SECRET, " ".join(str(v) for v in JobRun.objects.values_list("error_class", flat=True)))

    def test_logs_carry_names_counts_ids_and_exception_classes_but_no_secrets_titles_or_addresses(self):
        t = make_task(title=f"Maxfiy {SECRET}", due=timezone.localdate(), assignees=2)
        victim = t.assignees.order_by("username").first()

        def boom(user, *a, **kw):
            if user.pk == victim.pk:
                raise RuntimeError(f"cannot mail {user.email} {SECRET}")
            return None

        with self.assertLogs("apps.jobs", level="DEBUG") as cap:
            with mock.patch("apps.notifications.management.commands.send_task_reminders.notify", side_effect=boom):
                with self.assertRaises(CommandError):
                    run("send_task_reminders")
        text = "\n".join(cap.output)
        for forbidden in (SECRET, "Maxfiy", victim.email, "cannot mail", "Traceback"):
            self.assertNotIn(forbidden, text.replace("exc_info", ""))
        self.assertIn("RuntimeError", text)
        self.assertIn(str(t.pk), text)
        with self.assertLogs("apps.jobs", level="INFO") as cap2, mock.patch("apps.accounts.throttle.purge_expired", side_effect=ValueError(SECRET)):
            with self.assertRaises(CommandError):
                run("purge_throttles")
        self.assertNotIn(SECRET, "\n".join(cap2.output))

    def test_exit_codes_for_the_scanner_and_integrity_jobs(self):
        from django.test import override_settings

        with override_settings(DOCUMENT_SCAN_MODE="disabled"):
            with self.assertRaises(CommandError):
                run("check_scanner")
        self.assertEqual(JobRun.objects.get(name="check_scanner").status, "failed")
        run("verify_document_files")  # an empty store is consistent: exit code 0
        self.assertEqual(JobRun.objects.get(name="verify_document_files").status, "success")
        with override_settings(DOCUMENT_SCAN_MODE="clamav", CLAMAV_SOCKET="", CLAMAV_HOST="127.0.0.1", CLAMAV_PORT=1):
            with self.assertRaises(CommandError):
                run("check_scanner")


class TimeZones(TestCase):
    """Reminder dates follow the LOCAL day (Asia/Tashkent, UTC+5, no daylight saving), not UTC."""

    def at(self, iso):
        return mock.patch("django.utils.timezone.now", return_value=datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc))

    def test_the_local_midnight_changes_the_kind_and_never_duplicates(self):
        d = datetime.date(2026, 3, 11)
        t = make_task(due=d, assignees=1)
        with self.at("2026-03-10T18:59:00"):  # 23:59 on 10 March in Tashkent: the task is due tomorrow
            run("send_task_reminders")
        self.assertEqual(list(Notification.objects.filter(task=t).values_list("kind", flat=True)), ["task_due_soon"])
        with self.at("2026-03-10T19:01:00"):  # 00:01 on 11 March: due today -> same key, so no second notification
            run("send_task_reminders")
        self.assertEqual(Notification.objects.filter(task=t).count(), 1)
        with self.at("2026-03-11T19:01:00"):  # 00:01 on 12 March: now overdue, once
            run("send_task_reminders")
            run("send_task_reminders")
        self.assertEqual(sorted(Notification.objects.filter(task=t).values_list("kind", flat=True)), ["task_due_soon", "task_overdue"])

    def test_job_times_are_stored_timezone_aware_and_shown_as_utc_by_the_command(self):
        run("purge_throttles")
        r = JobRun.objects.get()
        self.assertIsNotNone(r.started_at.tzinfo)
        self.assertLessEqual(abs(timezone.now() - r.started_at), datetime.timedelta(seconds=30))
        self.assertIn("UTC", run("job_status", "--job", "purge_throttles"))


class CleaningNeverTouchesLiveData(TestCase):
    def test_import_previews_only_expired_waiting_ones_are_wiped(self):
        u = make_user("hrx")
        now = timezone.now()
        old = EmployeeImport.objects.create(user=u, file_sha256="0" * 64, rows=[{"n": 2, "raw": {}}])
        EmployeeImport.objects.filter(pk=old.pk).update(created_at=now - datetime.timedelta(minutes=61))
        young = EmployeeImport.objects.create(user=u, file_sha256="1" * 64, rows=[{"n": 2, "raw": {}}])
        done = EmployeeImport.objects.create(user=u, file_sha256="2" * 64, status="completed", summary={"added": 1})
        EmployeeImport.objects.filter(pk=done.pk).update(created_at=now - datetime.timedelta(days=3))
        out = run("purge_employee_imports")
        self.assertIn("wiped: 1", out)
        old.refresh_from_db(), young.refresh_from_db(), done.refresh_from_db()
        self.assertEqual((old.status, old.rows), ("expired", []))
        self.assertEqual((young.status, len(young.rows)), ("previewed", 1))
        self.assertEqual((done.status, done.summary), ("completed", {"added": 1}))
        self.assertIn("wiped: 0", run("purge_employee_imports"))  # repeating is safe
        self.assertEqual(JobRun.objects.get(name="purge_employee_imports", processed=0).status, "success")

    def test_sessions_only_expired_ones_and_orphaned_old_index_rows_go(self):
        alive_user, other = make_user("live"), make_user("other")
        from django.test import Client as C

        live = C()
        live.force_login(alive_user)
        live.get("/portal/")
        key = live.session.session_key
        dead = Session.objects.create(session_key="dead" * 8, session_data="x", expire_date=timezone.now() - datetime.timedelta(days=1))
        old_orphan = UserSession.objects.create(user=other, session_key="orph" * 8)
        UserSession.objects.filter(pk=old_orphan.pk).update(first_seen_at=timezone.now() - datetime.timedelta(hours=3))
        fresh_orphan = UserSession.objects.create(user=other, session_key="fres" * 8)  # younger than the grace period
        out = run("clear_expired_sessions")
        self.assertIn("expired sessions removed: 1", out)
        self.assertFalse(Session.objects.filter(pk=dead.pk).exists())
        self.assertTrue(Session.objects.filter(session_key=key).exists())
        self.assertTrue(UserSession.objects.filter(session_key=key).exists())  # the live session and its index row are untouched
        self.assertFalse(UserSession.objects.filter(pk=old_orphan.pk).exists())
        self.assertTrue(UserSession.objects.filter(pk=fresh_orphan.pk).exists())
        self.assertEqual(live.get("/portal/").status_code, 200)
        self.assertIn("expired sessions removed: 0; stale index rows removed: 0", run("clear_expired_sessions"))

    def test_throttle_rows_with_an_active_lock_are_kept(self):
        now = timezone.now()
        ThrottleState.objects.create(kind="login:user", key_hash="a" * 64, failures=9, last_failure_at=now - datetime.timedelta(days=30), locked_until=now + datetime.timedelta(minutes=5))
        ThrottleState.objects.create(kind="login:user", key_hash="b" * 64, failures=1, last_failure_at=now - datetime.timedelta(days=30))
        ThrottleState.objects.create(kind="login:user", key_hash="c" * 64, failures=1, last_failure_at=now)
        self.assertIn("deleted 1", run("purge_throttles"))
        self.assertEqual(sorted(ThrottleState.objects.values_list("key_hash", flat=True)), ["a" * 64, "c" * 64])
        self.assertIn("deleted 0", run("purge_throttles"))


class ParallelRuns(TransactionTestCase):
    def test_a_second_run_while_one_is_working_skips_without_touching_data_or_history_for_every_job(self):
        make_task(due=timezone.localdate(), assignees=2)
        for name, spec in jobs.JOBS.items():
            holder_ready, release = threading.Event(), threading.Event()

            def holder(lock=spec["lock"]):
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_lock(%s)", [lock])
                holder_ready.set()
                release.wait(10)
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [lock])
                connection.close()

            t = threading.Thread(target=holder)
            t.start()
            holder_ready.wait(10)
            try:
                out = run(name)  # must neither raise nor do anything
            finally:
                release.set()
                t.join(10)
            self.assertIn("skipped", out, name)
        self.assertEqual(JobRun.objects.count(), 0)  # a skipped run is not a run
        self.assertEqual(Notification.objects.count(), 0)
        run("send_task_reminders")
        self.assertEqual((Notification.objects.count(), JobRun.objects.count()), (2, 1))

    def test_lock_ids_are_distinct_so_different_jobs_never_block_each_other(self):
        ids = [s["lock"] for s in jobs.JOBS.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def lock_is_free(self, lock_id):
        """Asked from ANOTHER database session (a lock is re-entrant within the session that holds it, so the same one proves nothing)."""
        result = []

        def ask():
            with connection.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
                got = cur.fetchone()[0]
                if got:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
                result.append(got)
            connection.close()

        t = threading.Thread(target=ask)
        t.start()
        t.join(10)
        return result == [True]

    def test_the_lock_is_released_after_success_after_a_crash_and_after_record_errors(self):
        lock = jobs.JOBS["purge_throttles"]["lock"]
        run("purge_throttles")
        self.assertTrue(self.lock_is_free(lock))
        with mock.patch("apps.accounts.throttle.purge_expired", side_effect=RuntimeError("x")):
            with self.assertRaises(CommandError):
                run("purge_throttles")
        self.assertTrue(self.lock_is_free(lock))
        t = make_task(due=timezone.localdate(), assignees=1)
        with mock.patch("apps.notifications.management.commands.send_task_reminders.notify", side_effect=RuntimeError("x")):
            with self.assertRaises(CommandError):
                run("send_task_reminders")
        self.assertTrue(self.lock_is_free(jobs.JOBS["send_task_reminders"]["lock"]))
        self.assertEqual(list(JobRun.objects.filter(name="purge_throttles").order_by("started_at").values_list("status", flat=True)), ["success", "failed"])
        self.assertTrue(t.pk)


class StatusPage(TestCase):
    def setUp(self):
        from django.core.management import call_command as cc

        cc("seed_roles", verbosity=0)
        self.users = {r: make_user(r, role=r) for r in ("admin", "sysadmin", "hr", "content_manager", "employee")}

    def as_role(self, role, lang="uz"):
        c = Client()
        login_with_two_factor(c, self.users[role])
        c.cookies["django_language"] = lang
        return c

    def test_only_people_who_may_read_the_audit_log_see_it_and_nobody_else_can_change_anything(self):
        url = reverse("portal:jobs")
        for role, code in (("admin", 200), ("sysadmin", 200), ("hr", 403), ("content_manager", 403), ("employee", 403)):
            self.assertEqual(self.as_role(role).get(url).status_code, code, role)
        self.assertEqual(Client().get(url).status_code, 302)
        c = self.as_role("admin")
        self.assertEqual(c.post(url).status_code, 405)
        self.assertEqual(c.put(url).status_code, 405)

    def test_the_page_tells_the_truth_about_never_run_failed_and_unknown_and_exposes_no_internals(self):
        c = self.as_role("sysadmin")
        html = c.get(reverse("portal:jobs")).content.decode()
        self.assertEqual(html.count("Hali ishga tushmagan"), len(jobs.JOBS) - 0)
        self.assertNotIn("Muvaffaqiyatli</span>", html)
        now = timezone.now()
        JobRun.objects.create(name="purge_throttles", started_at=now, finished_at=now, status="success", processed=7)
        JobRun.objects.create(name="check_scanner", started_at=now, finished_at=now, status="failed", errors=0, error_class="CommandError")
        JobRun.objects.create(name="clear_expired_sessions", started_at=now - datetime.timedelta(hours=2), status="running")
        html = c.get(reverse("portal:jobs")).content.decode()
        for needle in ("Muvaffaqiyatli", "Natija noma’lum", ">7<"):
            self.assertIn(needle, html)
        self.assertIn("Xato", html)
        for hidden in ("CommandError", "/srv/", "/etc/", "password", "SECRET_KEY", "clamd", "private_media", "Traceback", ".env"):
            self.assertNotIn(hidden, html)

    def test_the_page_follows_the_language(self):
        for lang, title, never in (("ru", "Фоновые задачи", "Ещё не запускалась"), ("en", "Background jobs", "Not run yet"), ("uz", "Fon vazifalari", "Hali ishga tushmagan")):
            page = self.as_role("admin", lang).get(reverse("portal:jobs"))
            self.assertContains(page, f'<html lang="{lang}">')
            self.assertContains(page, title)
            self.assertContains(page, never)
