from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class PortalPermissionMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Anonymous -> sign in first; signed in without the permission -> 403 (never a silent redirect).

    The check runs on the server for every request, whatever the menu shows."""

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path(), self.get_login_url(), self.get_redirect_field_name())
        raise PermissionDenied
