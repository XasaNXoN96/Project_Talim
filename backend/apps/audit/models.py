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
        LOGIN_LOCKED = "login_locked", "Kirish vaqtincha bloklandi"
        LOGIN_BLOCKED = "login_blocked", "Bloklangan paytda kirishga urinish"
        PASSWORD_CHANGED = "password_changed", "Parol almashtirildi"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Parolni tiklash so‘raldi"
        PASSWORD_RESET_THROTTLED = "password_reset_throttled", "Parolni tiklash so‘rovlari cheklandi"
        PASSWORD_RESET_COMPLETED = "password_reset_completed", "Parol tiklandi"
        TWO_FACTOR_ENABLED = "two_factor_enabled", "2FA yoqildi"
        TWO_FACTOR_DISABLED = "two_factor_disabled", "2FA o‘chirildi"
        TWO_FACTOR_FAILED = "two_factor_failed", "2FA kodi noto‘g‘ri"
        TWO_FACTOR_LOCKED = "two_factor_locked", "2FA tekshiruvi vaqtincha bloklandi"
        TWO_FACTOR_BLOCKED = "two_factor_blocked", "Bloklangan paytda 2FA urinishi"
        TWO_FACTOR_BACKUP_USED = "two_factor_backup_used", "Zaxira kod ishlatildi"
        TWO_FACTOR_BACKUP_REGENERATED = "two_factor_backup_regenerated", "Zaxira kodlar yangilandi"
        TWO_FACTOR_RESET = "two_factor_reset", "2FA administrator tomonidan tiklandi"
        TWO_FACTOR_REQUIRED_LOGOUT = "two_factor_required_logout", "2FA talab qilingani uchun sessiya yopildi"
        USER_CREATED = "user_created", "Foydalanuvchi yaratildi"
        USER_UPDATED = "user_updated", "Foydalanuvchi o‘zgartirildi"
        USER_DEACTIVATED = "user_deactivated", "Foydalanuvchi o‘chirildi (faolsizlantirildi)"
        USER_REACTIVATED = "user_reactivated", "Foydalanuvchi qayta faollashtirildi"
        USER_INVITED = "user_invited", "Taklifnoma yuborildi"
        ACCOUNT_UNLOCKED = "account_unlocked", "Hisob blokdan chiqarildi"
        PASSWORD_CHANGE_FORCED = "password_change_forced", "Parolni almashtirish majburiy qilindi"
        EMPLOYEE_VIEWED = "employee_viewed", "Xodim kartasi ko‘rildi (shaxsiy ma’lumotlar)"
        EMPLOYEE_CREATED = "employee_created", "Xodim qo‘shildi"
        EMPLOYEE_UPDATED = "employee_updated", "Xodim o‘zgartirildi"
        EMPLOYEE_ARCHIVED = "employee_archived", "Xodim arxivlandi"
        EMPLOYEE_RESTORED = "employee_restored", "Xodim arxivdan qaytarildi"
        ORG_CHANGED = "org_changed", "Tashkiliy tuzilma o‘zgartirildi"
        DOCUMENT_UPLOADED = "document_uploaded", "Hujjat yuklandi"
        DOCUMENT_VERSION_ADDED = "document_version_added", "Hujjatning yangi versiyasi yuklandi"
        DOCUMENT_VIEWED = "document_viewed", "Maxfiy hujjat ko‘rildi"
        DOCUMENT_DOWNLOADED = "document_downloaded", "Hujjat yuklab olindi"
        DOCUMENT_UPDATED = "document_updated", "Hujjat ma’lumotlari o‘zgartirildi"
        DOCUMENT_ARCHIVED = "document_archived", "Hujjat arxivlandi"
        DOCUMENT_RESTORED = "document_restored", "Hujjat arxivdan qaytarildi"
        DOCUMENT_UPLOAD_REJECTED = "document_upload_rejected", "Hujjat yuklash rad etildi"

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
