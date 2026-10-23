from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


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
        LOGIN = "login", _("Tizimga kirish")
        LOGIN_FAILED = "login_failed", _("Muvaffaqiyatsiz kirish")
        LOGOUT = "logout", _("Chiqish")
        ROLE_ASSIGNED = "role_assigned", _("Rol biriktirildi")
        ROLE_REVOKED = "role_revoked", _("Rol olib tashlandi")
        LOGIN_LOCKED = "login_locked", _("Kirish vaqtincha bloklandi")
        LOGIN_BLOCKED = "login_blocked", _("Bloklangan paytda kirishga urinish")
        PASSWORD_CHANGED = "password_changed", _("Parol almashtirildi")
        PASSWORD_RESET_REQUESTED = "password_reset_requested", _("Parolni tiklash so‘raldi")
        PASSWORD_RESET_THROTTLED = "password_reset_throttled", _("Parolni tiklash so‘rovlari cheklandi")
        PASSWORD_RESET_COMPLETED = "password_reset_completed", _("Parol tiklandi")
        TWO_FACTOR_ENABLED = "two_factor_enabled", _("2FA yoqildi")
        TWO_FACTOR_DISABLED = "two_factor_disabled", _("2FA o‘chirildi")
        TWO_FACTOR_FAILED = "two_factor_failed", _("2FA kodi noto‘g‘ri")
        TWO_FACTOR_LOCKED = "two_factor_locked", _("2FA tekshiruvi vaqtincha bloklandi")
        TWO_FACTOR_BLOCKED = "two_factor_blocked", _("Bloklangan paytda 2FA urinishi")
        TWO_FACTOR_BACKUP_USED = "two_factor_backup_used", _("Zaxira kod ishlatildi")
        TWO_FACTOR_BACKUP_REGENERATED = "two_factor_backup_regenerated", _("Zaxira kodlar yangilandi")
        TWO_FACTOR_RESET = "two_factor_reset", _("2FA administrator tomonidan tiklandi")
        TWO_FACTOR_REQUIRED_LOGOUT = "two_factor_required_logout", _("2FA talab qilingani uchun sessiya yopildi")
        USER_CREATED = "user_created", _("Foydalanuvchi yaratildi")
        USER_UPDATED = "user_updated", _("Foydalanuvchi o‘zgartirildi")
        USER_DEACTIVATED = "user_deactivated", _("Foydalanuvchi o‘chirildi (faolsizlantirildi)")
        USER_REACTIVATED = "user_reactivated", _("Foydalanuvchi qayta faollashtirildi")
        USER_INVITED = "user_invited", _("Taklifnoma yuborildi")
        ACCOUNT_UNLOCKED = "account_unlocked", _("Hisob blokdan chiqarildi")
        PASSWORD_CHANGE_FORCED = "password_change_forced", _("Parolni almashtirish majburiy qilindi")
        EMPLOYEE_VIEWED = "employee_viewed", _("Xodim kartasi ko‘rildi (shaxsiy ma’lumotlar)")
        EMPLOYEE_CREATED = "employee_created", _("Xodim qo‘shildi")
        EMPLOYEE_UPDATED = "employee_updated", _("Xodim o‘zgartirildi")
        EMPLOYEE_ARCHIVED = "employee_archived", _("Xodim arxivlandi")
        EMPLOYEE_RESTORED = "employee_restored", _("Xodim arxivdan qaytarildi")
        ORG_CHANGED = "org_changed", _("Tashkiliy tuzilma o‘zgartirildi")
        DOCUMENT_UPLOADED = "document_uploaded", _("Hujjat yuklandi")
        DOCUMENT_VERSION_ADDED = "document_version_added", _("Hujjatning yangi versiyasi yuklandi")
        DOCUMENT_VIEWED = "document_viewed", _("Maxfiy hujjat ko‘rildi")
        DOCUMENT_DOWNLOADED = "document_downloaded", _("Hujjat yuklab olindi")
        DOCUMENT_UPDATED = "document_updated", _("Hujjat ma’lumotlari o‘zgartirildi")
        DOCUMENT_ARCHIVED = "document_archived", _("Hujjat arxivlandi")
        DOCUMENT_RESTORED = "document_restored", _("Hujjat arxivdan qaytarildi")
        DOCUMENT_UPLOAD_REJECTED = "document_upload_rejected", _("Hujjat yuklash rad etildi")
        FILE_THREAT_DETECTED = "file_threat_detected", _("Yuklangan faylda xavf aniqlandi")
        REPORT_EXPORTED = "report_exported", _("Hisobot yuklab olindi")
        REPORT_PEOPLE_VIEWED = "report_people_viewed", _("Hisobotda ijrochilar kesimi ko‘rildi")
        TASK_ATTACHMENT_ADDED = "task_attachment_added", _("Topshiriqqa fayl biriktirildi")
        TASK_ATTACHMENT_DOWNLOADED = "task_attachment_downloaded", _("Topshiriq fayli yuklab olindi")
        TASK_ATTACHMENT_REMOVED = "task_attachment_removed", _("Topshiriq fayli olib tashlandi")
        EMPLOYEE_IMPORT_PREVIEWED = "employee_import_previewed", _("Xodimlar importi: ko‘rib chiqish")
        EMPLOYEE_IMPORT_REJECTED = "employee_import_rejected", _("Xodimlar importi: fayl rad etildi")
        EMPLOYEE_IMPORT_COMPLETED = "employee_import_completed", _("Xodimlar importi bajarildi")
        EMPLOYEE_IMPORT_CANCELLED = "employee_import_cancelled", _("Xodimlar importi bekor qilindi")
        EMPLOYEE_IMPORT_FAILED = "employee_import_failed", _("Xodimlar importi xatolik bilan to‘xtadi")
        SESSION_ENDED = "session_ended", _("Sessiya yakunlandi")
        SESSIONS_ENDED_OTHERS = "sessions_ended_others", _("Boshqa sessiyalar yakunlandi")
        PROFILE_CHANGE_REQUESTED = "profile_change_requested", _("Xodim o‘z ma’lumotini o‘zgartirishni so‘radi")
        PROFILE_CHANGE_DECIDED = "profile_change_decided", _("Ma’lumotni o‘zgartirish so‘rovi bo‘yicha qaror")
        CHAT_NOTICE_ACCEPTED = "chat_notice_accepted", _("Chat haqidagi ogohlantirish qabul qilindi")
        CHAT_ARCHIVE_VIEWED = "chat_archive_viewed", _("Administrator suhbatni ko‘rdi")
        MEDIA_UPLOADED = "media_uploaded", _("Media fayllar yuklandi")
        MEDIA_CHANGED = "media_changed", _("Media fayl o‘zgartirildi")
        ACHIEVEMENT_CREATED = "achievement_created", _("Yutuq yaratildi")
        ACHIEVEMENT_UPDATED = "achievement_updated", _("Yutuq o‘zgartirildi")
        ACHIEVEMENT_STEP = "achievement_step", _("Yutuq holati o‘zgardi")
        ACHIEVEMENT_PUBLISHED = "achievement_published", _("Yutuq nashr etildi")
        NEWS_CREATED = "news_created", _("Yangilik yaratildi")
        NEWS_UPDATED = "news_updated", _("Yangilik o‘zgartirildi")
        NEWS_PUBLISHED = "news_published", _("Yangilik nashr etildi")
        NEWS_UNPUBLISHED = "news_unpublished", _("Yangilik nashrdan olindi")
        NEWS_ARCHIVED = "news_archived", _("Yangilik arxivlandi")
        NEWS_RESTORED = "news_restored", _("Yangilik arxivdan qaytarildi")
        NEWS_SUBMITTED = "news_submitted", _("Yangilik tekshiruvga yuborildi")
        NEWS_WITHDRAWN = "news_withdrawn", _("Yangilik tekshiruvdan qaytarib olindi")
        NEWS_CHANGES_REQUESTED = "news_changes_requested", _("Yangilik tuzatishga qaytarildi")
        NEWS_APPROVED = "news_approved", _("Yangilik ma’qullandi")
        ADMIN_CREATED = "admin_created", _("Django admin: yozuv yaratildi")
        ADMIN_CHANGED = "admin_changed", _("Django admin: yozuv o‘zgartirildi")
        ADMIN_DELETED = "admin_deleted", _("Django admin: yozuv o‘chirildi")
        ADMIN_BLOCKED = "admin_blocked", _("Django admin: amal taqiqlandi")
        NEWS_CATEGORY_CHANGED = "news_category_changed", _("Yangilik kategoriyasi o‘zgartirildi")

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
        verbose_name = _("audit yozuvi")
        verbose_name_plural = _("audit yozuvlari")
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
