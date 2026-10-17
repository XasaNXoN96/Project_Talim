from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel, UUIDModel


class User(UUIDModel, AbstractUser):
    """Custom user model (must exist before the first migration).

    Passwords are handled by Django's auth system (Argon2 hasher) — never stored or compared by hand.
    New users get NO privileges: is_staff / is_superuser default to False and permissions come only
    from roles (groups) assigned through apps.access.
    """

    class Locale(models.TextChoices):
        UZ = "uz", "O‘zbekcha"
        RU = "ru", "Русский"
        EN = "en", "English"

    email = models.EmailField("e-mail", max_length=254)  # required (AbstractUser makes it optional)
    locale = models.CharField("til", max_length=2, choices=Locale.choices, default=Locale.UZ)
    must_change_password = models.BooleanField("parolni almashtirish shart", default=False)

    class Meta:
        verbose_name = "foydalanuvchi"
        verbose_name_plural = "foydalanuvchilar"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.UniqueConstraint(Lower("username"), name="accounts_user_username_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class ThrottleState(models.Model):
    """Attempt counter for rate limiting. Lives in PostgreSQL so it works across processes and servers.

    `key_hash` is an HMAC of the throttled value (identifier, user id, IP, e-mail), so neither raw identifiers
    nor addresses are stored. See apps.accounts.throttle for the rules.
    """

    kind = models.CharField(max_length=32)
    key_hash = models.CharField(max_length=64)
    failures = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_blocked_log_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "key_hash"], name="throttlestate_unique_key")]
        indexes = [models.Index(fields=["locked_until"]), models.Index(fields=["last_failure_at"])]

    def __str__(self):
        return f"{self.kind}:{self.key_hash[:8]} failures={self.failures}"


class TotpDevice(TimeStampedModel):
    """Authenticator-app secret. The secret is stored ENCRYPTED (Fernet); see apps.accounts.otp."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp_device")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)  # set only after a valid code was entered
    last_used_counter = models.BigIntegerField(null=True, blank=True)  # 30-second step; blocks code replay

    def __str__(self):
        return f"TOTP({self.user_id}, confirmed={self.confirmed_at is not None})"


class BackupCode(TimeStampedModel):
    """One-time recovery code, stored only as a password hash."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="backup_codes")
    code_hash = models.CharField(max_length=255)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "used_at"])]
