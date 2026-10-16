from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDModel


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
