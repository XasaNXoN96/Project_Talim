import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.core.models import TimeStampedModel, UUIDModel
from apps.documents.storage import PrivateStorage


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", pgettext_lazy("task status", "Yangi")
        IN_PROGRESS = "in_progress", _("Jarayonda")
        REVIEW = "review", _("Tekshiruvda")
        DONE = "done", _("Bajarildi")
        CANCELLED = "cancelled", _("Bekor qilindi")

    class Priority(models.TextChoices):
        LOW = "low", _("Past")
        NORMAL = "normal", _("Oddiy")
        HIGH = "high", _("Yuqori")
        URGENT = "urgent", _("Shoshilinch")

    FINAL = (Status.DONE, Status.CANCELLED)

    title = models.CharField(_("sarlavha"), max_length=200)
    description = models.TextField(_("tavsif"), blank=True, max_length=5000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks_created")
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tasks_assigned", blank=True)
    status = models.CharField(_("holat"), max_length=16, choices=Status.choices, default=Status.NEW)
    priority = models.CharField(_("muhimlik"), max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField(_("muddat"), null=True, blank=True)
    due_time = models.TimeField(_("muddat vaqti"), null=True, blank=True)  # set by the person who gives the task; none = end of that day
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("topshiriq")
        verbose_name_plural = _("topshiriqlar")
        ordering = ["-created_at"]
        permissions = [("view_department_tasks", _("Bo‘lim (yoki butun tashkilot) topshiriqlarini ko‘rish"))]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["due_date"])]

    def __str__(self):
        return self.title

    @property
    def deadline(self):
        """Aware datetime of the deadline (end of that day when no time was set); None without a due date."""
        if not self.due_date:
            return None
        return timezone.make_aware(datetime.datetime.combine(self.due_date, self.due_time or datetime.time.max))

    @property
    def is_overdue(self):
        """Open and past its deadline. With a due time the task is overdue from that minute, not from the next day."""
        return self.status not in self.FINAL and self.deadline is not None and timezone.now() > self.deadline


def overdue_q(prefix=""):
    """Q for 'past its deadline' (date passed, or today and the due time passed). Combine with a status filter yourself."""
    now = timezone.localtime()
    return Q(**{f"{prefix}due_date__lt": now.date()}) | Q(**{f"{prefix}due_date": now.date(), f"{prefix}due_time__lt": now.time()})


class TaskComment(TimeStampedModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=4000)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("izoh")
        verbose_name_plural = _("izohlar")


class TaskEvent(UUIDModel):
    """Append-only history of a task (who did what). Comment text is NOT copied here."""

    class Kind(models.TextChoices):
        CREATED = "created", _("Yaratildi")
        EDITED = "edited", _("O‘zgartirildi")
        STATUS = "status", _("Holat o‘zgardi")
        COMMENTED = "commented", _("Izoh qoldirildi")
        ATTACHED = "attached", _("Fayl biriktirildi")
        DETACHED = "detached", _("Fayl olib tashlandi")

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
        permissions = [("remove_taskattachment", _("Faylni topshiriqdan olib tashlash (faylning o‘zi o‘chirilmaydi)"))]
