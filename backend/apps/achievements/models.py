import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.documents.storage import PrivateStorage


class AchievementQuerySet(models.QuerySet):
    def published(self):
        """The ONLY queryset public pages may use: published and already due."""
        return self.filter(status=Achievement.Status.PUBLISHED, publish_at__lte=timezone.now())


class Achievement(TimeStampedModel):
    """An award of a teacher, a pupil or a whole school (medal, certificate, diploma...).

    A school sends it; the administrators check it, may complete it, and publish it only after seeing a preview.
    Nothing is public until then (see apps.achievements.workflow)."""

    class Kind(models.TextChoices):
        MEDAL = "medal", _("Medal")
        CERTIFICATE = "certificate", _("Sertifikat")
        DIPLOMA = "diploma", _("Diplom")
        AWARD = "award", _("Mukofot")
        OTHER = "other", _("Boshqa")

    class PersonKind(models.TextChoices):
        TEACHER = "teacher", _("Ustoz")
        STUDENT = "student", _("O‘quvchi")
        TEAM = "team", _("Jamoa yoki muassasa")

    class Level(models.TextChoices):
        INSTITUTION = "institution", _("Muassasa darajasi")
        DISTRICT = "district", _("Tuman")
        REGION = "region", _("Viloyat")
        REPUBLIC = "republic", _("Respublika")
        INTERNATIONAL = "international", _("Xalqaro")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Qoralama")
        SUBMITTED = "submitted", _("Yuborilgan")
        CHANGES_REQUESTED = "changes_requested", _("Tuzatish talab etiladi")
        PREPARED = "prepared", _("Tayyor qoralama")
        PUBLISHED = "published", _("Nashr etilgan")
        ARCHIVED = "archived", _("Arxiv")

    institution = models.ForeignKey("organization.Institution", on_delete=models.PROTECT, related_name="achievements", verbose_name=_("ta’lim muassasasi"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(_("turi"), max_length=16, choices=Kind.choices, default=Kind.CERTIFICATE)
    title = models.CharField(_("sarlavha"), max_length=200)
    person_kind = models.CharField(_("kim erishdi"), max_length=16, choices=PersonKind.choices, default=PersonKind.TEACHER)
    person_name = models.CharField(_("ism-familiya yoki jamoa nomi"), max_length=200)
    person_position = models.CharField(_("lavozim, fan yoki sinf"), max_length=200, blank=True)
    level = models.CharField(_("daraja"), max_length=16, choices=Level.choices, default=Level.DISTRICT)
    awarded_on = models.DateField(_("olingan sana"), null=True, blank=True)
    description = models.TextField(_("tavsif"), blank=True, max_length=5000)
    video_url = models.URLField(_("video havolasi"), blank=True, max_length=300)  # https link to a video hosted elsewhere
    consent_confirmed = models.BooleanField(_("nashrga rozilik"), default=False)
    status = models.CharField(_("holat"), max_length=24, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField(_("nashr sanasi"), null=True, blank=True)
    slug = models.SlugField(max_length=120, unique=True, editable=False)

    objects = AchievementQuerySet.as_manager()

    class Meta:
        verbose_name = _("yutuq")
        verbose_name_plural = _("yutuqlar")
        ordering = ["-publish_at", "-created_at"]
        permissions = [("publish_achievement", _("Yutuqni tekshirish va nashr etish"))]
        indexes = [models.Index(fields=["status", "-publish_at"]), models.Index(fields=["institution", "status"])]
        constraints = [
            models.CheckConstraint(condition=~Q(status="published") | Q(publish_at__isnull=False), name="achievement_published_requires_date"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"{slugify(self.title)[:60] or 'yutuq'}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)


class AchievementImage(UUIDModel):
    """A picture of an achievement: re-encoded JPEG in the private storage, served only by the achievement views."""

    MAX_PER_ACHIEVEMENT = 5

    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="images")
    file = models.FileField(storage=PrivateStorage(), max_length=120)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at"]


class AchievementReview(TimeStampedModel):
    """Append-only history: who did what to which achievement, when, with which comment. Written only by the workflow."""

    class Action(models.TextChoices):
        SUBMIT = "submit", _("Tekshiruvga yuborildi")
        WITHDRAW = "withdraw", _("Tekshiruvdan qaytarib olindi")
        REQUEST_CHANGES = "request_changes", _("Tuzatishga qaytarildi")
        SAVE_DRAFT = "save_draft", _("Tayyor qoralama sifatida saqlandi")
        PUBLISH = "publish", _("Nashr etildi")
        UNPUBLISH = "unpublish", _("Nashrdan olindi")
        ARCHIVE = "archive", _("Arxivlandi")
        RESTORE = "restore", _("Arxivdan qaytarildi")

    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="reviews")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=24, choices=Action.choices)
    from_status = models.CharField(max_length=24)
    to_status = models.CharField(max_length=24)
    comment = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["achievement", "created_at"])]
