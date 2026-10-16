from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Department(TimeStampedModel):
    name = models.CharField("nomi", max_length=200)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "bo‘lim"
        verbose_name_plural = "bo‘limlar"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], nulls_distinct=False, name="department_unique_name_per_parent")
        ]

    def __str__(self):
        return self.name


class Position(TimeStampedModel):
    name = models.CharField("nomi", max_length=200, unique=True)

    class Meta:
        verbose_name = "lavozim"
        verbose_name_plural = "lavozimlar"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    """Staff profile. Contains personal data: no real records may be entered until the legal checklist is cleared."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        ON_LEAVE = "on_leave", "Ta’tilda"
        NEW = "new", "Yangi"
        ARCHIVED = "archived", "Arxiv"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )
    last_name = models.CharField("familiya", max_length=100)
    first_name = models.CharField("ism", max_length=100)
    middle_name = models.CharField("otasining ismi", max_length=100, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    position = models.ForeignKey(Position, null=True, blank=True, on_delete=models.PROTECT, related_name="employees")
    work_phone = models.CharField("ish telefoni", max_length=32, blank=True)
    work_email = models.EmailField("ish e-pochtasi", blank=True)
    hired_at = models.DateField("ishga qabul sanasi", null=True, blank=True)
    status = models.CharField("holat", max_length=16, choices=Status.choices, default=Status.NEW)

    class Meta:
        verbose_name = "xodim"
        verbose_name_plural = "xodimlar"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class Institution(TimeStampedModel):
    """Education institution (school, kindergarten, ...). Public listing only when is_published."""

    class Kind(models.TextChoices):
        SCHOOL = "school", "Umumiy o‘rta ta’lim maktabi"
        SPECIALIZED = "specialized", "Ixtisoslashtirilgan maktab"
        PRESCHOOL = "preschool", "Maktabgacha ta’lim muassasasi"
        ARTS = "arts", "Ijod maktabi"
        VOCATIONAL = "vocational", "Kasbiy ta’lim"

    name = models.CharField("nomi", max_length=250)
    kind = models.CharField("turi", max_length=16, choices=Kind.choices)
    head_name = models.CharField("rahbar", max_length=200, blank=True)
    is_published = models.BooleanField("saytda ko‘rsatish", default=False)

    class Meta:
        verbose_name = "ta’lim muassasasi"
        verbose_name_plural = "ta’lim muassasalari"
        ordering = ["name"]

    def __str__(self):
        return self.name
