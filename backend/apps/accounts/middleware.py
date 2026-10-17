from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record

from .twofactor import VERIFIED_KEY, must_verify_two_factor


class TwoFactorEnforcementMiddleware:
    """Defence in depth: a signed-in session of a user who must use 2FA is valid only if it went through 2FA.

    Catches sessions that were created any other way (a role granted after login, a bypass attempt, a bug).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not request.session.get(VERIFIED_KEY) and must_verify_two_factor(user):
            record(AuditLog.Action.TWO_FACTOR_REQUIRED_LOGOUT, request=request, user=user)
            logout(request)
            messages.error(request, _("Xavfsizlik uchun qayta kiring: ikki bosqichli tasdiqlash talab qilinadi."))
            return redirect(f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)


class MustChangePasswordMiddleware:
    """A signed-in user flagged `must_change_password` can do nothing but change the password (or sign out)."""

    ALLOWED_URL_NAMES = {"accounts:password_change", "accounts:password_change_done", "accounts:logout", "healthz", "csp_report", "set_language"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.must_change_password and not request.path.startswith("/static/"):
            try:
                match = resolve(request.path_info)
                name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
            except Resolver404:
                name = None
            if name not in self.ALLOWED_URL_NAMES:
                messages.warning(request, _("Davom etishdan oldin parolingizni almashtiring."))
                return redirect("accounts:password_change")
        return self.get_response(request)
