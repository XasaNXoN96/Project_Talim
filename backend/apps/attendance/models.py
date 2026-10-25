from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.core.models import TimeStampedModel, UUIDModel

NOTICE_VERSION = 1  # raise it when the notice text changes: everybody has to accept again


class WorkZone(TimeStampedModel):
    """A place where staff are expected to be: a centre point and a radius. A zone without an institution applies to everybody;
    a zone of an institution applies to the staff of that institution. Zones are never deleted, only switched off."""

    name = models.CharField(_("nomi"), max_length=200)
    institution = models.ForeignKey(
        "organization.Institution", null=True, blank=True, on_delete=models.PROTECT, related_name="work_zones", verbose_name=_("ta’lim muassasasi")
    )
    latitude = models.DecimalField(_("kenglik"), max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(_("uzunlik"), max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    radius_m = models.PositiveIntegerField(_("radius (metr)"), default=150, validators=[MinValueValidator(30), MaxValueValidator(5000)])
    is_active = models.BooleanField(_("faol"), default=True)

    class Meta:
        verbose_name = _("ish hududi")
        verbose_name_plural = _("ish hududlari")
        ordering = ["name"]
        default_permissions = ("view", "add", "change")  # no delete: switch it off instead

    def __str__(self):
        return self.name


class AttendanceEvent(UUIDModel):
    """One press of "Kirish" (in) or "Chiqish" (out). Location is recorded ONLY at that moment (never followed in the background) and
    its coordinates are wiped after ATTENDANCE_LOCATION_RETENTION_DAYS (the flags and times stay). Events are never edited or deleted:
    a mistake is fixed by an additional manual event with a reason."""

    class Kind(models.TextChoices):
        IN = "in", pgettext_lazy("attendance", "Kirish")
        OUT = "out", pgettext_lazy("attendance", "Chiqish")

    class Source(models.TextChoices):
        SELF = "self", _("O‘zi belgiladi")
        MANUAL = "manual", _("Qo‘lda kiritildi")

    employee = models.ForeignKey("organization.Employee", on_delete=models.PROTECT, related_name="attendance_events")
    kind = models.CharField(max_length=3, choices=Kind.choices)
    at = models.DateTimeField(default=timezone.now, db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    zone = models.ForeignKey(WorkZone, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    inside_zone = models.BooleanField(null=True, blank=True)  # None = no zone applied or no location
    distance_m = models.PositiveIntegerField(null=True, blank=True)  # to the nearest applicable zone
    note = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.SELF)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        verbose_name = _("kirish-chiqish belgisi")
        verbose_name_plural = _("kirish-chiqish belgilari")
        ordering = ["-at"]
        default_permissions = ()
        permissions = [
            ("use_attendance", _("Kirish-chiqishni belgilash")),
            ("view_team_attendance", _("Xodimlarning kirish-chiqishini ko‘rish (qamrov bo‘yicha, ko‘rish jurnalga yoziladi)")),
            ("correct_attendance", _("Kirish-chiqishni qo‘lda tuzatish va aniq koordinatalarni ko‘rish")),
        ]
        indexes = [models.Index(fields=["employee", "-at"])]
        constraints = [
            models.CheckConstraint(condition=Q(latitude__isnull=True, longitude__isnull=True) | Q(latitude__isnull=False, longitude__isnull=False), name="attendance_coords_both_or_none"),
        ]


class AttendanceNoticeAcceptance(models.Model):
    """The person has read that presses are recorded, how the location is used and who may see it."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    version = models.PositiveSmallIntegerField(default=NOTICE_VERSION)
    accepted_at = models.DateTimeField(auto_now_add=True)
