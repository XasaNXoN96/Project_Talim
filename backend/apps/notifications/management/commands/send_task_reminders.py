from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.tasks.models import Task


class Command(BaseCommand):
    help = (
        "Create 'due soon' (due today or tomorrow) and 'overdue' notifications for open tasks. Safe to run as often as "
        "you like: each (task, assignee, due date, kind) produces at most one notification. Nothing runs it automatically: "
        "schedule it (cron/systemd timer), e.g. every hour: `python manage.py send_task_reminders`."
    )

    LOCK_ID = 7_310_001  # arbitrary application-wide key for the PostgreSQL advisory lock

    def handle(self, *args, **options):
        # A second run that starts while one is still working exits at once instead of doing the same work twice.
        # (Even without the lock, the unique dedupe key makes duplicates impossible; the lock only saves effort.)
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [self.LOCK_ID])
            if not cur.fetchone()[0]:
                self.stdout.write("another run is in progress: skipped")
                return
        try:
            self._run()
        finally:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [self.LOCK_ID])

    def _run(self):
        today = timezone.localdate()
        soon = today + timedelta(days=1)
        created = {"due_soon": 0, "overdue": 0}
        open_tasks = Task.objects.exclude(status__in=Task.FINAL).filter(due_date__isnull=False, due_date__lte=soon).prefetch_related("assignees")
        for task in open_tasks:
            if task.due_date < today:
                kind, label = Notification.Kind.TASK_OVERDUE, "overdue"
            else:
                kind, label = Notification.Kind.TASK_DUE_SOON, "due_soon"
            for user in task.assignees.all():
                key = f"{label}:{task.pk}:{task.due_date.isoformat()}"
                if notify(user, kind, task, dedupe_key=key):
                    created[label] += 1
        self.stdout.write(f"due_soon={created['due_soon']} overdue={created['overdue']}")
