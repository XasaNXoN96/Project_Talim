import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import UUIDModel

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters (0/O, 1/I)


def new_code():
    return "M-" + "".join(secrets.choice(CODE_ALPHABET) for _i in range(8))


class Appeal(UUIDModel):
    """A citizen's appeal sent through the public form. The citizen follows it with the code and the last digits of the phone."""

    class Subject(models.TextChoices):
        GENERAL = "general", _("Umumiy savol")
        SUGGESTION = "suggestion", _("Taklif")
        COMPLAINT = "complaint", _("Shikoyat")
        ENROLMENT = "enrolment", _("Qabul va o‘qishga oid")
        OTHER = "other", _("Boshqa")

    class Status(models.TextChoices):
        NEW = "new", _("Yangi")
        IN_PROGRESS = "in_progress", _("Ko‘rib chiqilmoqda")
        ANSWERED = "answered", _("Javob berildi")
        REJECTED = "rejected", _("Rad etildi")

    code = models.CharField(max_length=12, unique=True, default=new_code, editable=False)
    full_name = models.CharField(_("F.I.Sh."), max_length=120)
    phone = models.CharField(_("telefon"), max_length=32)
    email = models.EmailField(_("e-pochta"), blank=True)
    subject = models.CharField(_("mavzu"), max_length=16, choices=Subject.choices, default=Subject.GENERAL)
    message = models.TextField(_("murojaat matni"), max_length=2000)
    status = models.CharField(_("holat"), max_length=12, choices=Status.choices, default=Status.NEW)
    answer = models.TextField(_("javob"), max_length=2000, blank=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("murojaat")
        verbose_name_plural = _("murojaatlar")
        permissions = [("answer_appeal", "Can answer citizens' appeals")]

    def __str__(self):
        return f"{self.code} · {self.full_name}"

    def phone_tail(self):
        digits = "".join(ch for ch in self.phone if ch.isdigit())
        return digits[-4:]
