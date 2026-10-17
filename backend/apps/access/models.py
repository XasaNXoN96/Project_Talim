from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.organization.models import Department


class RoleAssignment(TimeStampedModel):
    """Gives a user a role (Group) with a scope. Saving/deleting keeps user.groups in sync (see signals)."""

    class Scope(models.TextChoices):
        OWN = "own", _("Faqat o‘zi")
        DEPARTMENT = "department", _("Bo‘lim")
        ALL = "all", _("Butun tashkilot")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="assignments")
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.OWN)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = _("rol biriktirish")
        verbose_name_plural = _("rol biriktirishlar")
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(scope="department", department__isnull=False))
                | (~models.Q(scope="department") & models.Q(department__isnull=True)),
                name="roleassignment_department_matches_scope",
            ),
            models.UniqueConstraint(
                fields=["user", "role", "scope", "department"], nulls_distinct=False, name="roleassignment_unique"
            ),
        ]

    def clean(self):
        if self.scope == self.Scope.DEPARTMENT and not self.department_id:
            raise ValidationError({"department": _("Bo‘lim doirasi uchun bo‘lim ko‘rsatilishi shart.")})
        if self.scope != self.Scope.DEPARTMENT and self.department_id:
            raise ValidationError({"department": _("Bo‘lim faqat «Bo‘lim» doirasi uchun ko‘rsatiladi.")})

    def save(self, *args, **kwargs):
        self.clean()
        if not self._state.adding:
            old = type(self).objects.filter(pk=self.pk).values("user_id", "role_id").first()
            if old and (old["user_id"] != self.user_id or old["role_id"] != self.role_id):
                raise ValueError("Changing the user or role of an assignment is not allowed; delete and create a new one.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} → {self.role} ({self.scope})"
