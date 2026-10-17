from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccessConfig(AppConfig):
    name = "apps.access"
    verbose_name = _("Rollar va huquqlar")

    def ready(self):
        from . import signals  # noqa: F401
