from django.conf import settings
from django.db import models
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.organization.models import Department

from .storage import PrivateStorage


# The default categories are stored in the database in Uzbek (migration 0002). They are translated when SHOWN, through
# the catalogs; categories an administrator adds under any other name are displayed exactly as typed.
SEED_CATEGORY_NAMES = (_("Buyruqlar"), _("Nizomlar va yo‘riqnomalar"), _("Hisobotlar"), _("Shablonlar va namunalar"), _("Boshqa"))


class DocumentCategory(TimeStampedModel):
    name = models.CharField(_("nomi"), max_length=120, unique=True)
    is_active = models.BooleanField(_("faol"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("hujjat turkumi")
        verbose_name_plural = _("hujjat turkumlari")

    def __str__(self):
        return gettext(self.name)


class Document(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Faol")
        ARCHIVED = "archived", _("Arxivda")

    class Access(models.TextChoices):
        GENERAL = "general", _("Barcha xodimlar")
        DEPARTMENT = "department", _("Faqat bo‘lim")
        CONFIDENTIAL = "confidential", _("Maxfiy (muallif va kadrlar/administrator)")

    title = models.CharField(_("sarlavha"), max_length=200)
    description = models.TextField(_("tavsif"), blank=True, max_length=2000)
    number = models.CharField(_("hujjat raqami"), max_length=60, blank=True)
    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT, related_name="documents", verbose_name=_("turkum"))
    doc_date = models.DateField(_("hujjat sanasi"), null=True, blank=True)
    access_level = models.CharField(_("kirish darajasi"), max_length=16, choices=Access.choices, default=Access.GENERAL)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name=_("bo‘lim"))
    status = models.CharField(_("holat"), max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documents_created")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("hujjat")
        verbose_name_plural = _("hujjatlar")
        permissions = [
            ("view_all_documents", _("Barcha (maxfiy bo‘lmagan) hujjatlarni, jumladan bo‘limlarnikini ko‘rish")),
            ("view_confidential_document", _("Maxfiy hujjatlarni ko‘rish")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access_level="department", department__isnull=False) | ~models.Q(access_level="department"),
                name="document_department_needed",
            )
        ]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["doc_date"])]

    def __str__(self):
        return self.title

    @property
    def current_version(self):
        return self.versions.order_by("-number").first()


class DocumentVersion(UUIDModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    file = models.FileField(storage=PrivateStorage(), max_length=120)
    original_name = models.CharField(max_length=150)  # display only
    extension = models.CharField(max_length=8)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    comment = models.CharField(_("izoh"), max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Antivirus verdict recorded at upload. "not_scanned" = stored while the scanner was disabled (or before it existed);
    # "infected" = found by a later re-scan: never served.
    scan_status = models.CharField(max_length=12, choices=[("clean", _("Toza")), ("not_scanned", _("Tekshirilmagan")), ("infected", _("Xavfli"))], default="not_scanned")
    scan_engine = models.CharField(max_length=20, blank=True)
    scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="documentversion_unique_number")]
