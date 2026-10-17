from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = _("Foydalanuvchilar")

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out

        from . import sessions

        user_logged_in.connect(sessions.on_login, dispatch_uid="accounts_session_login")
        user_logged_out.connect(sessions.on_logout, dispatch_uid="accounts_session_logout")
