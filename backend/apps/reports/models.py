from django.db import models


class ReportAccess(models.Model):
    """Holds the report permissions only; there is no table (managed = False)."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_reports", "Hisobotlar sahifasini ko‘rish (doira rol bo‘yicha)"),
            ("export_reports", "Hisobotlarni Excel/PDF ga yuklab olish"),
            ("view_report_people", "Hisobotda ijrochilar kesimini ko‘rish (shaxsiy natijalar)"),
        ]
