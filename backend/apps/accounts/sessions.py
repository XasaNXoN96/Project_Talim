"""Login sessions: tracking, listing and ending.

Django's own session rows (django_session) are the truth about whether a session still works; `UserSession` only adds
first/last activity and a browser label, and every listing is checked against django_session (exists, not expired, belongs
to this user). Ending a session deletes the django_session row, so the next request with that cookie is anonymous.

Limits that cannot be removed: Django's expiry is absolute (SESSION_COOKIE_AGE from login), and a browser-session cookie
that was lost with a closed browser still leaves a server-side row until it expires, so "active" means "the server still
accepts it". Sessions that existed before this feature appear after their next request."""
import re
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.core import network

from .models import UserSession

TOUCH_EVERY = timedelta(minutes=5)  # last_seen_at is refreshed at most this often: one UPDATE per 5 minutes, not per request

_BROWSERS = (("Edge", r"Edg(?:e|A|iOS)?/"), ("Opera", r"OPR/|Opera"), ("Firefox", r"Firefox/|FxiOS/"), ("Chrome", r"Chrome/|CriOS/"), ("Safari", r"Safari/"))
_SYSTEMS = (("Android", r"Android"), ("iOS", r"iPhone|iPad|iPod"), ("Windows", r"Windows"), ("macOS", r"Macintosh|Mac OS X"), ("Linux", r"Linux|X11"))


def describe_agent(user_agent: str):
    """(browser, os) family names from a User-Agent, or ("", "") when it says nothing recognisable. Never the raw header."""
    ua = user_agent or ""
    browser = next((name for name, rx in _BROWSERS if re.search(rx, ua)), "")
    system = next((name for name, rx in _SYSTEMS if re.search(rx, ua)), "")
    return browser, system


def _agent(request):
    return describe_agent((request.META.get("HTTP_USER_AGENT") or "")[:512]) if request is not None else ("", "")


def _ip(request):
    return network.client_ip(request) if request is not None else None


def track(request, user, session_key=None):
    """Create or refresh the row for the current session. Safe to call repeatedly."""
    key = session_key or getattr(getattr(request, "session", None), "session_key", None)
    if not key or not user.is_authenticated:
        return None
    now = timezone.now()
    browser, system = _agent(request)
    row, created = UserSession.objects.get_or_create(session_key=key, defaults={"user": user, "ip": _ip(request), "browser": browser, "os": system})
    if not created:
        if row.user_id != user.pk:  # a key can never move to another account; start over
            row.delete()
            return track(request, user, key)
        learned = (not row.browser and browser) or (not row.os and system) or (not row.ip and _ip(request))  # e.g. the row was made by a bare login
        if learned or now - row.last_seen_at >= TOUCH_EVERY:
            UserSession.objects.filter(pk=row.pk).update(last_seen_at=now, ip=row.ip or _ip(request), browser=row.browser or browser, os=row.os or system)
    return row


def on_login(sender, request, user, **kwargs):
    if request is not None and getattr(request, "session", None) is not None:
        # tidy this user's rows whose session is gone, so the table does not grow without bound
        live = set(Session.objects.filter(session_key__in=UserSession.objects.filter(user=user).values("session_key"), expire_date__gte=timezone.now()).values_list("session_key", flat=True))
        UserSession.objects.filter(user=user).exclude(session_key__in=live).delete()
        track(request, user)


def on_logout(sender, request, user, **kwargs):
    key = getattr(getattr(request, "session", None), "session_key", None)
    if key:
        UserSession.objects.filter(session_key=key).delete()


def active_sessions(user, current_key=None):
    """[{row, current}] for the sessions of `user` that the server still accepts, newest activity first."""
    rows = list(UserSession.objects.filter(user=user).order_by("-last_seen_at"))
    if not rows:
        return []
    live = {s.session_key: s for s in Session.objects.filter(session_key__in=[r.session_key for r in rows], expire_date__gte=timezone.now())}
    out = []
    for row in rows:
        session = live.get(row.session_key)
        if session is None or session.get_decoded().get("_auth_user_id") != str(user.pk):
            continue  # gone, expired, or (impossible by construction) someone else's: never listed
        out.append({"row": row, "current": row.session_key == current_key, "expires": session.expire_date})
    return sorted(out, key=lambda i: not i["current"])  # the current session first, the rest by recent activity


def end_session(row) -> bool:
    """End the session behind one UserSession row (the caller has already checked that it belongs to the signed-in user and is
    not the current one). True when a live session was really removed, False when it was already gone."""
    existed = Session.objects.filter(session_key=row.session_key, expire_date__gte=timezone.now()).delete()[0]
    row.delete()
    return bool(existed)


def end_other_sessions(user, current_key):
    """End every session of `user` except the current one (tracked or not). Returns how many were closed."""
    return invalidate_user_sessions(user, keep_session_key=current_key)


def invalidate_user_sessions(user, keep_session_key=None) -> int:
    """Delete every session of `user` (optionally keeping the current one). Returns how many were removed.

    Django already treats sessions as invalid once the password changes (session auth hash), but the rows are
    removed explicitly so nothing lingers. Linear in the number of live sessions — fine at this scale.
    """
    removed = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if keep_session_key and session.session_key == keep_session_key:
            continue
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
            removed += 1
    UserSession.objects.filter(user=user).exclude(session_key=keep_session_key or "").delete()
    return removed
