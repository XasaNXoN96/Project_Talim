from django.apps import AppConfig


class AccessConfig(AppConfig):
    name = "apps.access"
    verbose_name = "Rollar va huquqlar"

    def ready(self):
        from . import signals  # noqa: F401
