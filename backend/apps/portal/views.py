from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, TemplateView

from apps.access.services import user_role_names
from apps.audit.models import AuditLog
from apps.core.mixins import PortalPermissionMixin


class DashboardView(LoginRequiredMixin, TemplateView):
    """Protected landing page of the staff portal. Server-side login check; content is a skeleton for now."""

    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_names"] = sorted(user_role_names(self.request.user))
        return context


class AuditLogListView(PortalPermissionMixin, ListView):
    """Real data: the latest audit entries. Requires the audit.view_auditlog permission (checked on the server)."""

    template_name = "portal/audit_list.html"
    permission_required = "audit.view_auditlog"
    paginate_by = 50
    context_object_name = "entries"

    def get_queryset(self):
        return AuditLog.objects.select_related("user")


class SearchView(LoginRequiredMixin, TemplateView):
    """Search box results. Signed-in users only; each source applies its own permissions inside apps.portal.search."""

    template_name = "portal/search.html"

    def get_context_data(self, **kwargs):
        from django.core.paginator import InvalidPage, Paginator
        from django.http import Http404

        from . import search

        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        text, words = search.clean_query(self.request.GET.get("q"))
        kind = self.request.GET.get("type")
        if kind and kind not in search.KINDS:
            raise Http404
        ctx.update(q=text, too_short=bool(text) and not words, searched=bool(words), kind=kind, labels=search.LABELS, sections=[], page_obj=None)
        if not words:
            return ctx
        for k in ([kind] if kind else search.KINDS):
            qs = search.source(user, k, words)
            if qs is None:
                continue
            if kind:
                paginator = Paginator(qs, search.PAGE_SIZE)
                try:
                    page = paginator.page(self.request.GET.get("page") or 1)
                except InvalidPage:
                    raise Http404 from None
                ctx["page_obj"], ctx["paginator"] = page, paginator
                items, count = list(page), paginator.count
            else:
                count = qs.count()
                items = list(qs[:search.PREVIEW])
            ctx["sections"].append({"kind": k, "label": search.LABELS[k], "count": count, "more": count > len(items) and not kind, "items": [search.describe(user, k, o) for o in items]})
        ctx["total"] = sum(s["count"] for s in ctx["sections"])
        return ctx
