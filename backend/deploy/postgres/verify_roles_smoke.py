"""Run by verify_roles.sh as the RESTRICTED application role against a scratch database: the application's normal write paths must work,
and the things the role must not be able to do must fail with 'permission denied'."""
import os

import django

django.setup()
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402
from django.test import Client, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

from apps.access.models import RoleAssignment  # noqa: E402
from apps.audit.models import AuditLog  # noqa: E402
from apps.documents.testing import PDF, upload  # noqa: E402
from apps.tasks.models import Task  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def _atomic_cursor():
    from contextlib import ExitStack

    class _Both:
        def __enter__(self):
            self.stack = ExitStack()
            self.stack.enter_context(transaction.atomic())
            return self.stack.enter_context(connection.cursor())

        def __exit__(self, *exc):
            return self.stack.__exit__(*exc)

    return _Both()


def denied(sql):
    try:
        # CREATE DATABASE cannot run inside a transaction block, so it is tried in autocommit (the others in a rolled-back block)
        with (connection.cursor() if sql.startswith("CREATE DATABASE") else _atomic_cursor()) as cur:
            cur.execute(sql)
        return False, "executed"
    except DatabaseError as exc:
        return "permission denied" in str(exc) or "must be owner" in str(exc), type(exc).__name__


with connection.cursor() as cur:
    cur.execute("select current_user, rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user")
    who, sup, createdb, createrole = cur.fetchone()
check("connected as the restricted role, which is not superuser, cannot create databases or roles", who == os.environ["DB_USER"] and not (sup or createdb or createrole), who)

U = get_user_model()
with override_settings(ALLOWED_HOSTS=["testserver"]):
    hr = U.objects.create_user("smoke_hr", "smoke_hr@example.test", "Namuna-Parol-12345")
    RoleAssignment.objects.create(user=hr, role=Group.objects.get(name="hr"), scope="all")
    boss = U.objects.create_user("smoke_boss", "smoke_boss@example.test", "Namuna-Parol-12345")
    RoleAssignment.objects.create(user=boss, role=Group.objects.get(name="admin"), scope="all")
    c = Client()
    r = c.post(reverse("accounts:login"), {"username": "smoke_hr", "password": "Namuna-Parol-12345"})
    check("login works (sessions, throttling, audit and the sessions index are all written)", r.status_code == 302 and AuditLog.objects.filter(action="login").exists(), str(r.status_code))
    r = c.get(reverse("portal:dashboard"))
    check("an authenticated page loads", r.status_code == 200, str(r.status_code))
    from apps.documents.models import DocumentCategory

    r = c.post(reverse("documents:create"), {"title": "Smoke", "category": DocumentCategory.objects.first().pk, "access_level": "general", "file": upload("s.pdf", PDF)})
    check("a document upload works (files, versions, audit)", r.status_code == 302 and AuditLog.objects.filter(action="document_uploaded").exists(), str(r.status_code))
    t = Task.objects.create(title="Smoke", created_by=hr)
    t.assignees.set([hr])
    call_command("send_task_reminders", verbosity=0)
    call_command("purge_throttles", verbosity=0)
    from apps.core.models import JobRun

    check("scheduled jobs run and record themselves (job runs, notifications)", JobRun.objects.filter(name="purge_throttles", status="success").exists())

n_before = AuditLog.objects.count()
for label, sql in (
    ("UPDATE of the audit log is refused", "UPDATE audit_auditlog SET action = 'tampered'"),
    ("UPDATE of the audit log's other columns is refused (only user_id may change)", "UPDATE audit_auditlog SET meta = '{}'::jsonb"),
    ("DELETE from the audit log is refused", "DELETE FROM audit_auditlog"),
    ("TRUNCATE of the audit log is refused", "TRUNCATE audit_auditlog"),
    ("the migration history cannot be rewritten", "DELETE FROM django_migrations"),
    ("tables cannot be created", "CREATE TABLE smoke_x (id int)"),
    ("tables cannot be dropped", "DROP TABLE accounts_user CASCADE"),
    ("databases cannot be created", "CREATE DATABASE smoke_other"),
    ("roles cannot be created", "CREATE ROLE smoke_role"),
):
    ok, detail = denied(sql)
    check(label, ok, detail)
check("the audit log lost no rows through those attempts", AuditLog.objects.count() == n_before)
check("appending to the audit log still works", AuditLog.objects.create(action="login", object_type="smoke").pk is not None)

victim = U.objects.create_user("smoke_victim", "smoke_victim@example.test", "Namuna-Parol-12345")
AuditLog.objects.create(action="login", user=victim, object_type="User", object_id=str(victim.pk))
victim.delete()  # ON DELETE SET NULL touches audit_auditlog.user_id: the one column the role may update
check("deleting a user detaches (user_id -> NULL) but keeps their audit rows", AuditLog.objects.filter(object_id__isnull=False, user__isnull=True, object_type="User").exists())
print(f"{sum(RESULTS)}/{len(RESULTS)} checks passed")
raise SystemExit(0 if all(RESULTS) else 1)
