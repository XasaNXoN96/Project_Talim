import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.jobs import TrackedCommand
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.tasks.models import Task

logger = logging.getLogger("apps.jobs")


class Command(TrackedCommand):
    help = (
        "Create 'due soon' (due today or tomorrow, by the LOCAL date) and 'overdue' notifications for open tasks. Safe to run as "
        "often as you like: each (task, assignee, due date, kind) produces at most one notification (a database unique key), and "
        "a second run that starts while one is working exits at once. One failing record is counted and skipped, the rest are "
        "still processed; any failure gives exit code 1. Nothing runs it automatically: see docs/SCHEDULER.md."
    )
    job_name = "send_task_reminders"

    def run_job(self, run, *args, **options):
        today = timezone.localdate()
        soon = today + timedelta(days=1)
        created = {"due_soon": 0, "overdue": 0}
        open_tasks = Task.objects.exclude(status__in=Task.FINAL).filter(due_date__isnull=False, due_date__lte=soon).prefetch_related("assignees")
        for task in open_tasks:
            if task.due_date < today:
                kind, label = Notification.Kind.TASK_OVERDUE, "overdue"
            else:
                kind, label = Notification.Kind.TASK_DUE_SOON, "due_soon"
            key = f"{label}:{task.pk}:{task.due_date.isoformat()}"
            for user in task.assignees.all():
                run.processed += 1
                try:
                    if notify(user, kind, task, dedupe_key=key):
                        created[label] += 1
                except Exception as exc:  # noqa: BLE001 — one bad record must not stop the others
                    run.errors += 1
                    logger.error("reminder failed task=%s user=%s kind=%s (%s)", task.pk, user.pk, label, type(exc).__name__)
        self.stdout.write(f"due_soon={created['due_soon']} overdue={created['overdue']}")
