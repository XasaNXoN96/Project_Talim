from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        IN_PROGRESS = "in_progress", "Jarayonda"
        REVIEW = "review", "Tekshiruvda"
        DONE = "done", "Bajarildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    class Priority(models.TextChoices):
        LOW = "low", "Past"
        NORMAL = "normal", "Oddiy"
        HIGH = "high", "Yuqori"

    FINAL = (Status.DONE, Status.CANCELLED)

    title = models.CharField("sarlavha", max_length=200)
    description = models.TextField("tavsif", blank=True, max_length=5000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks_created")
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tasks_assigned", blank=True)
    status = models.CharField("holat", max_length=16, choices=Status.choices, default=Status.NEW)
    priority = models.CharField("muhimlik", max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField("muddat", null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "topshiriq"
        verbose_name_plural = "topshiriqlar"
        ordering = ["-created_at"]
        permissions = [("view_department_tasks", "Bo‘lim (yoki butun tashkilot) topshiriqlarini ko‘rish")]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["due_date"])]

    def __str__(self):
        return self.title


class TaskComment(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=4000)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "izoh"
        verbose_name_plural = "izohlar"


class TaskEvent(UUIDModel):
    """Append-only history of a task (who did what). Comment text is NOT copied here."""

    class Kind(models.TextChoices):
        CREATED = "created", "Yaratildi"
        EDITED = "edited", "O‘zgartirildi"
        STATUS = "status", "Holat o‘zgardi"
        COMMENTED = "commented", "Izoh qoldirildi"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    meta = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at"]
