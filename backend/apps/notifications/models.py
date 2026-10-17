from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class Notification(UUIDModel):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = "task_assigned", "Topshiriq berildi"
        TASK_SUBMITTED = "task_submitted", "Topshiriq tekshiruvga topshirildi"
        TASK_ACCEPTED = "task_accepted", "Topshiriq qabul qilindi"
        TASK_RETURNED = "task_returned", "Topshiriq qaytarildi"
        TASK_CANCELLED = "task_cancelled", "Topshiriq bekor qilindi"
        TASK_DUE_SOON = "task_due_soon", "Topshiriq muddati yaqin"
        TASK_OVERDUE = "task_overdue", "Topshiriq muddati o‘tdi"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=200)  # task title at the time; shown only to someone who can still view the task
    task = models.ForeignKey("tasks.Task", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    # Automatic reminders carry a key so running the command twice cannot create a second notification.
    dedupe_key = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "dedupe_key"], condition=~models.Q(dedupe_key=""), name="notification_unique_dedupe_key"),
        ]
        indexes = [models.Index(fields=["user", "read_at"])]
