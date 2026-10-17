from django.contrib.sessions.models import Session
from django.utils import timezone


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
    return removed
