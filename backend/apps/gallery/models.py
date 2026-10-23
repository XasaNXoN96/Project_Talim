from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.documents.storage import PrivateStorage


class MediaQuerySet(models.QuerySet):
    def published(self):
        """The ONLY queryset public pages may use: published and already due."""
        return self.filter(status=MediaItem.Status.PUBLISHED, publish_at__lte=timezone.now())


class MediaItem(TimeStampedModel):
    """One photo or one video of the common gallery ("Media"). Curated by the staff who hold add/change rights; nothing is public until
    it is published, and only with the confirmed consent of the people shown (children included).

    Photos are re-encoded JPEGs (a full size and a thumbnail), videos are checked MP4/WebM files (apps.achievements.videos): both live in the
    private storage under random names and leave only through the gallery views."""

    class Kind(models.TextChoices):
        PHOTO = "photo", _("Fotorasm")
        VIDEO = "video", _("Video")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Qoralama")
        PUBLISHED = "published", _("Nashr etilgan")

    kind = models.CharField(_("turi"), max_length=8, choices=Kind.choices)
    title = models.CharField(_("sarlavha"), max_length=200, blank=True)
    institution = models.ForeignKey("organization.Institution", null=True, blank=True, on_delete=models.PROTECT, related_name="media_items", verbose_name=_("ta’lim muassasasi"))
    taken_on = models.DateField(_("olingan sana"), null=True, blank=True)
    consent_confirmed = models.BooleanField(_("nashrga rozilik"), default=False)
    status = models.CharField(_("holat"), max_length=12, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField(_("nashr sanasi"), null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    file = models.FileField(storage=PrivateStorage(), max_length=120)
    thumb = models.FileField(storage=PrivateStorage(), max_length=120, blank=True)  # photos only
    content_type = models.CharField(max_length=20)  # image/jpeg | video/mp4 | video/webm, decided by OUR code
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=12, default="not_scanned")

    objects = MediaQuerySet.as_manager()

    class Meta:
        verbose_name = _("media fayl")
        verbose_name_plural = _("media fayllar")
        ordering = ["-taken_on", "-created_at"]
        # No Django "delete_mediaitem": the project grants no delete_* permission to any role. Erasing a file for good (a person may ask for their
        # picture to be removed) has its own, explicit permission, held only by those who curate the gallery.
        default_permissions = ("add", "change", "view")
        permissions = [
            ("publish_mediaitem", _("Media faylni nashr etish va nashrdan olish")),
            ("erase_mediaitem", _("Media faylni serverdan butunlay o‘chirish")),
        ]
        indexes = [models.Index(fields=["kind", "status", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=~Q(status="published") | Q(publish_at__isnull=False), name="media_published_requires_date"),
            models.CheckConstraint(condition=~Q(status="published") | Q(consent_confirmed=True), name="media_published_requires_consent"),
        ]

    def __str__(self):
        return self.title or str(self.pk)
