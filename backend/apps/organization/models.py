from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.documents.storage import PrivateStorage


class Department(TimeStampedModel):
    name = models.CharField(_("nomi"), max_length=200)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField(_("faol"), default=True)

    class Meta:
        verbose_name = _("bo‘lim")
        verbose_name_plural = _("bo‘limlar")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], nulls_distinct=False, name="department_unique_name_per_parent")
        ]

    def __str__(self):
        return self.name


class Position(TimeStampedModel):
    name = models.CharField(_("nomi"), max_length=200, unique=True)

    class Meta:
        verbose_name = _("lavozim")
        verbose_name_plural = _("lavozimlar")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    """Staff profile. Contains personal data: no real records may be entered until the legal checklist is cleared."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Faol")
        ON_LEAVE = "on_leave", _("Ta’tilda")
        NEW = "new", _("Yangi")
        ARCHIVED = "archived", _("Arxiv")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )
    last_name = models.CharField(_("familiya"), max_length=100)
    first_name = models.CharField(_("ism"), max_length=100)
    middle_name = models.CharField(_("otasining ismi"), max_length=100, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.PROTECT, related_name="employees")
    work_phone = models.CharField(_("ish telefoni"), max_length=32, blank=True)
    work_email = models.EmailField(_("ish e-pochtasi"), blank=True)
    hired_at = models.DateField(_("ishga qabul sanasi"), null=True, blank=True)
    personal_phone = models.CharField(_("shaxsiy telefon"), max_length=32, blank=True)
    birth_date = models.DateField(_("tug‘ilgan sana"), null=True, blank=True)
    status = models.CharField(_("holat"), max_length=16, choices=Status.choices, default=Status.NEW)
    # School/kindergarten the person works at (None = works in the department office).
    institution = models.ForeignKey(
        "Institution", null=True, blank=True, on_delete=models.PROTECT, related_name="employees", verbose_name=_("ta’lim muassasasi")
    )
    # Profile photo: re-encoded JPEG in the private storage, served only through the permission-checked photo view.
    photo = models.FileField(storage=PrivateStorage(), max_length=120, blank=True)

    class Meta:
        verbose_name = _("xodim")
        verbose_name_plural = _("xodimlar")
        ordering = ["last_name", "first_name"]
        permissions = [
            ("view_employee_directory", _("Xodimlar ro‘yxatini ko‘rish (ism, lavozim, bo‘lim, holat)")),
            ("view_employee_contacts", _("Xodimlarning aloqa ma’lumotlarini ko‘rish")),
            ("view_employee_private", _("Xodimlarning shaxsiy ma’lumotlarini ko‘rish")),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class Institution(TimeStampedModel):
    """Education institution (school, kindergarten, ...). Public listing only when is_published."""

    class Kind(models.TextChoices):
        SCHOOL = "school", _("Umumiy o‘rta ta’lim maktabi")
        SPECIALIZED = "specialized", _("Ixtisoslashtirilgan maktab")
        PRESCHOOL = "preschool", _("Maktabgacha ta’lim muassasasi")
        ARTS = "arts", _("Ijod maktabi")
        VOCATIONAL = "vocational", _("Kasbiy ta’lim")

    name = models.CharField(_("nomi"), max_length=250)
    kind = models.CharField(_("turi"), max_length=16, choices=Kind.choices)
    head_name = models.CharField(_("rahbar"), max_length=200, blank=True)
    is_published = models.BooleanField(_("saytda ko‘rsatish"), default=False)

    class Meta:
        verbose_name = _("ta’lim muassasasi")
        verbose_name_plural = _("ta’lim muassasalari")
        ordering = ["name"]

    def __str__(self):
        return self.name


class EmployeeImport(UUIDModel):
    """One Excel import: the parsed rows wait here between the preview and the confirmation, then are wiped.

    `rows` holds personal data (it is the uploaded sheet, cleaned). It exists only while `status` is "previewed" and the
    record is younger than EMPLOYEE_IMPORT_TTL_MINUTES; completing, cancelling or expiring it empties `rows`. The uploaded
    file itself is never stored. `summary` keeps counts and row numbers only."""

    class Status(models.TextChoices):
        PREVIEWED = "previewed", _("Ko‘rib chiqish")
        COMPLETED = "completed", _("Bajarildi")
        CANCELLED = "cancelled", _("Bekor qilindi")
        EXPIRED = "expired", _("Muddati o‘tdi")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVIEWED)
    file_sha256 = models.CharField(max_length=64)
    rows = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


# Fields a person may ask to change about THEMSELVES. Never: department, position, institution, status, hire date, account link.
SELF_EDITABLE_FIELDS = ("last_name", "first_name", "middle_name", "work_phone", "work_email", "personal_phone", "birth_date")


class EmployeeChangeRequest(TimeStampedModel):
    """A person's request to correct their own data. It changes nothing until HR or an administrator approves it.

    The values (personal data) are kept only while the request is open: a decision empties them and leaves the field NAMES, who decided
    and when, so the history stays useful without keeping old and new personal data around."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Kutilmoqda")
        APPROVED = "approved", _("Tasdiqlandi")
        REJECTED = "rejected", _("Rad etildi")
        CANCELLED = "cancelled", _("Bekor qilindi")

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="change_requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    fields = models.JSONField(default=list)  # names of the fields concerned (kept after the decision)
    changes = models.JSONField(default=dict)  # {field: new value as text}; emptied by a decision
    old_values = models.JSONField(default=dict)  # {field: value when asked}; emptied by a decision
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True, max_length=1000)

    class Meta:
        verbose_name = _("ma’lumotni o‘zgartirish so‘rovi")
        verbose_name_plural = _("ma’lumotni o‘zgartirish so‘rovlari")
        ordering = ["-created_at"]
        permissions = [
            ("request_employee_change", _("O‘z ma’lumotlarini o‘zgartirishni so‘rash")),
            ("review_employee_change", _("Ma’lumotni o‘zgartirish so‘rovlarini ko‘rib chiqish")),
        ]
        constraints = [
            models.UniqueConstraint(fields=["employee"], condition=models.Q(status="pending"), name="one_pending_change_request_per_employee"),
        ]
