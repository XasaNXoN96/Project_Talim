from django.db import models
from django.utils.translation import gettext_lazy as _


class ReportAccess(models.Model):
    """Holds the report permissions only; there is no table (managed = False)."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_reports", _("Hisobotlar sahifasini ko‘rish (doira rol bo‘yicha)")),
            ("export_reports", _("Hisobotlarni Excel/PDF ga yuklab olish")),
            ("view_report_people", _("Hisobotda ijrochilar kesimini ko‘rish (shaxsiy natijalar)")),
        ]
