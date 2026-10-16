from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.views.generic import ListView, TemplateView

from apps.access.services import user_role_names
from apps.audit.models import AuditLog


class DashboardView(LoginRequiredMixin, TemplateView):
    """Protected landing page of the staff portal. Server-side login check; content is a skeleton for now."""

    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_names"] = sorted(user_role_names(self.request.user))
        return context


class AuditLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Real data: the latest audit entries. Requires the audit.view_auditlog permission (checked on the server)."""

    template_name = "portal/audit_list.html"
    permission_required = "audit.view_auditlog"
    paginate_by = 50
    context_object_name = "entries"

    def handle_no_permission(self):
        # Anonymous -> sign in first; signed in but without the permission -> 403 (never a silent redirect).
        if not self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path(), self.get_login_url(), self.get_redirect_field_name())
        raise PermissionDenied

    def get_queryset(self):
        return AuditLog.objects.select_related("user")
