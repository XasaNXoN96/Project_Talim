from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import UUIDModel


class Notification(UUIDModel):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = "task_assigned", _("Topshiriq berildi")
        TASK_SUBMITTED = "task_submitted", _("Topshiriq tekshiruvga topshirildi")
        TASK_ACCEPTED = "task_accepted", _("Topshiriq qabul qilindi")
        TASK_RETURNED = "task_returned", _("Topshiriq qaytarildi")
        TASK_CANCELLED = "task_cancelled", _("Topshiriq bekor qilindi")
        TASK_DUE_SOON = "task_due_soon", _("Topshiriq muddati yaqin")
        TASK_OVERDUE = "task_overdue", _("Topshiriq muddati o‘tdi")
        NEWS_SUBMITTED = "news_submitted", _("Yangilik tekshiruvga yuborildi")
        NEWS_CHANGES_REQUESTED = "news_changes_requested", _("Yangilik tuzatishga qaytarildi")
        NEWS_APPROVED = "news_approved", _("Yangilik ma’qullandi")
        PROFILE_CHANGE_ASKED = "profile_change_asked", _("Ma’lumotni o‘zgartirish so‘rovi keldi")
        PROFILE_CHANGE_DONE = "profile_change_done", _("Ma’lumot o‘zgartirish so‘rovi tasdiqlandi")
        PROFILE_CHANGE_DENIED = "profile_change_denied", _("Ma’lumot o‘zgartirish so‘rovi rad etildi")
        ACHIEVEMENT_SUBMITTED = "achievement_submitted", _("Yutuq tekshiruvga yuborildi")
        ACHIEVEMENT_RETURNED = "achievement_returned", _("Yutuq tuzatishga qaytarildi")
        ACHIEVEMENT_PUBLISHED = "achievement_published", _("Yutuq nashr etildi")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=200)  # task title at the time; shown only to someone who can still view the task
    task = models.ForeignKey("tasks.Task", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    news = models.ForeignKey("content.News", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    achievement = models.ForeignKey("achievements.Achievement", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    change_request = models.ForeignKey("organization.EmployeeChangeRequest", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
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
