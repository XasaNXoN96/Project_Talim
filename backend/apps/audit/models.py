from django.conf import settings
from django.db import models
from django.utils import timezone


class ImmutableAuditError(Exception):
    """Audit records are append-only."""


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableAuditError("Audit log entries cannot be updated.")

    def delete(self):
        raise ImmutableAuditError("Audit log entries cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise ImmutableAuditError("Audit log entries cannot be updated.")


class AuditLog(models.Model):
    """Append-only action journal.

    Application-level protection only: retention/cleanup (once the retention period is legally set) must be a
    dedicated, reviewed job; database-level protection (restricted role) is planned for the hardening stage.
    Never put passwords, tokens or raw personal data into `meta`.
    """

    class Action(models.TextChoices):
        LOGIN = "login", "Tizimga kirish"
        LOGIN_FAILED = "login_failed", "Muvaffaqiyatsiz kirish"
        LOGOUT = "logout", "Chiqish"
        ROLE_ASSIGNED = "role_assigned", "Rol biriktirildi"
        ROLE_REVOKED = "role_revoked", "Rol olib tashlandi"

    at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    action = models.CharField(max_length=32, choices=Action.choices, editable=False)
    object_type = models.CharField(max_length=64, blank=True, editable=False)
    object_id = models.CharField(max_length=64, blank=True, editable=False)
    ip = models.GenericIPAddressField(null=True, blank=True, editable=False)
    user_agent = models.CharField(max_length=255, blank=True, editable=False)
    meta = models.JSONField(default=dict, blank=True, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        verbose_name = "audit yozuvi"
        verbose_name_plural = "audit yozuvlari"
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["action", "-at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableAuditError("Audit log entries cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableAuditError("Audit log entries cannot be deleted.")

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.action}"
