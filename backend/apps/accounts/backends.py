from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


def find_login_user(identifier):
    """The single user whose username or e-mail equals `identifier` (case-insensitive), else None."""
    identifier = str(identifier or "").strip()
    if not identifier:
        return None
    User = get_user_model()
    candidates = list(User._default_manager.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))[:2])
    return candidates[0] if len(candidates) == 1 else None


class EmailOrUsernameBackend(ModelBackend):
    """Log in with username OR e-mail (case-insensitive) — the login page says «Elektron pochta yoki login».

    Password verification is Django's own (check_password). Unknown or ambiguous identifiers still run the
    password hasher once, so response time does not reveal whether an account exists.
    Permission lookups are inherited from ModelBackend (groups/permissions).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user = find_login_user(username)
        if user is None:
            get_user_model()().set_password(password)  # equalise timing: unknown/ambiguous identifiers cost the same
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
