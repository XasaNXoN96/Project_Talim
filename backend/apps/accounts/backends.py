from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Log in with username OR e-mail (case-insensitive) — the login page says «Elektron pochta yoki login».

    Password verification is Django's own (check_password). Unknown or ambiguous identifiers still run the
    password hasher once, so response time does not reveal whether an account exists.
    Permission lookups are inherited from ModelBackend (groups/permissions).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        identifier = str(username).strip()
        if not identifier:
            return None
        User = get_user_model()
        candidates = list(User._default_manager.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))[:2])
        if len(candidates) != 1:
            User().set_password(password)  # equalise timing
            return None
        user = candidates[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
