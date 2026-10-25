"""Two-factor policy and the pending-login state.

The password step does NOT log the user in for accounts that need a second factor: it only stores a short-lived
"pending" marker in the session. ``login()`` is called after the code (or enrolment) succeeds, so there is never a
signed-in-but-unverified session that a direct URL could exploit. TwoFactorEnforcementMiddleware additionally
refuses any session that belongs to a privileged user but was not completed through this flow.
"""
import time

from django.conf import settings
from django.contrib.auth import get_user_model, login as auth_login

from .models import TotpDevice

def _ts() -> int:
    """Clock for the pending-login window (patched in tests)."""
    return int(time.time())


PENDING_KEY = "pending_2fa"
VERIFIED_KEY = "two_factor_ok"


def requires_two_factor(user) -> bool:
    """Privileged accounts: superusers and holders of the roles in settings.TWO_FACTOR_REQUIRED_ROLES."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if settings.DEBUG and getattr(settings, "DEV_SKIP_TWO_FACTOR", False):
        return False  # local walkthrough only; a person who enrolled a device is still asked (see must_verify_two_factor)
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=settings.TWO_FACTOR_REQUIRED_ROLES).exists()


def has_confirmed_device(user) -> bool:
    return TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def must_verify_two_factor(user) -> bool:
    """Required by role, or the user opted in by enrolling a device."""
    return requires_two_factor(user) or (getattr(user, "is_authenticated", False) and has_confirmed_device(user))


def start_pending(request, user, backend: str, remember: bool, next_url: str) -> None:
    request.session.cycle_key()  # new session id for the pending state (no fixation)
    request.session[PENDING_KEY] = {
        "uid": str(user.pk),
        "backend": backend,
        "remember": bool(remember),
        "next": next_url,
        "at": _ts(),
    }


def get_pending(request):
    """Returns (user, data) for a valid, unexpired pending login, otherwise None (and clears stale state)."""
    data = request.session.get(PENDING_KEY)
    if not data:
        return None
    if _ts() - data.get("at", 0) > settings.TWO_FACTOR_PENDING_SECONDS:
        request.session.pop(PENDING_KEY, None)
        return None
    user = get_user_model()._default_manager.filter(pk=data["uid"], is_active=True).first()
    if user is None:
        request.session.pop(PENDING_KEY, None)
        return None
    return user, data


def clear_pending(request) -> None:
    request.session.pop(PENDING_KEY, None)


def complete_login(request, user, backend: str, remember: bool, *, verified: bool) -> None:
    clear_pending(request)
    auth_login(request, user, backend=backend)  # also rotates the session id
    if verified:
        request.session[VERIFIED_KEY] = True
    if not remember:
        request.session.set_expiry(0)  # ends with the browser; with "remember me", SESSION_COOKIE_AGE applies
