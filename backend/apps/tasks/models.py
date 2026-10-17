from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel
from apps.documents.storage import PrivateStorage


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
        ATTACHED = "attached", "Fayl biriktirildi"
        DETACHED = "detached", "Fayl olib tashlandi"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    meta = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at"]


class TaskAttachment(UUIDModel):
    """A file attached to a task. Same private storage and the same validation + antivirus path as documents
    (apps.documents.files); there is no separate upload code. "Removing" only unlinks it from the task: the file stays
    on disk for the audit trail and backups, but is no longer offered or served."""

    MAX_PER_TASK = 20

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(storage=PrivateStorage(), max_length=120)
    original_name = models.CharField(max_length=150)  # display only
    extension = models.CharField(max_length=8)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=12, default="not_scanned")
    scan_engine = models.CharField(max_length=20, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["uploaded_at"]
        permissions = [("remove_taskattachment", "Faylni topshiriqdan olib tashlash (faylning o‘zi o‘chirilmaydi)")]
