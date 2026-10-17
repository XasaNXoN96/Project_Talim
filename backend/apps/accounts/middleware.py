from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

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
            messages.error(request, "Xavfsizlik uchun qayta kiring: ikki bosqichli tasdiqlash talab qilinadi.")
            return redirect(f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)
