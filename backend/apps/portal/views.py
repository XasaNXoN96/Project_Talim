from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.views.generic import ListView, TemplateView

from apps.access.services import user_role_names
from apps.audit.models import AuditLog
from apps.core.mixins import PortalPermissionMixin

from .hub import can_open_hub, tiles_for


class DashboardView(LoginRequiredMixin, TemplateView):
    """Landing page of the staff portal, laid out like the design mock-up. Every block shows real data and only what the signed-in user may see."""

    template_name = "portal/dashboard.html"

    def get_context_data(self, **kwargs):
        from django.utils import timezone

        from apps.content.models import News
        from apps.notifications.models import Notification
        from apps.organization.models import Department, Employee
        from apps.tasks import access as task_access
        from apps.tasks.models import Task

        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["role_names"] = sorted(user_role_names(user))
        context["today"] = timezone.localdate()
        stats = []
        if user.has_perm("organization.view_employee_directory"):
            stats.append(("users", "c-blue", Employee.objects.exclude(status=Employee.Status.ARCHIVED).count(), "Xodimlar"))
        if user.has_perm("organization.view_department"):
            stats.append(("building", "c-teal", Department.objects.count(), "Bo‘limlar"))
        if user.has_perm("content.view_news"):
            stats.append(("news", "c-red", News.objects.published().count(), "Yangiliklar"))
        if user.has_perm("tasks.view_task"):
            open_tasks = task_access.visible_tasks(user).exclude(status__in=Task.FINAL)
            stats.append(("clipboard", "c-orange", open_tasks.count(), "Topshiriqlar"))
            context["my_tasks"] = list(
                Task.objects.filter(assignees=user).exclude(status__in=Task.FINAL).order_by("due_date", "-created_at")[:5]
            )
        context["stats"] = stats
        if user.has_perm("content.view_news"):
            context["latest_news"] = list(News.objects.published().select_related("category")[:3])
        if user.has_perm("notifications.view_notification"):
            recent = list(Notification.objects.filter(user=user).select_related("task", "news")[:4])
            visible_task_ids = set(
                task_access.visible_tasks(user).filter(pk__in=[n.task_id for n in recent if n.task_id]).values_list("pk", flat=True)
            )
            for n in recent:
                n.shown = n.task_id in visible_task_ids if n.task_id else bool(n.news_id)
            context["recent_notifications"] = recent
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


class JobsView(PortalPermissionMixin, TemplateView):
    """Background-job overview for people who may read the audit log. Counts, times and states only: no paths, settings or record data."""

    template_name = "portal/jobs.html"
    permission_required = "audit.view_auditlog"

    def get_context_data(self, **kwargs):
        from apps.core import jobs

        states = jobs.all_job_states()
        return super().get_context_data(jobs=[{**s, "healthy": jobs.is_healthy(s)} for s in states], **kwargs)


PREVIEW_SECTIONS = ("yutuqlar", "sertifikatlar", "media", "kirish-chiqish", "geolokatsiya", "chat")


class PreviewView(LoginRequiredMixin, TemplateView):
    """Design-mock-up sections that are not built yet (sample data, nothing is stored or collected). Same access as the dashboard: a signed-in user."""

    def get_template_names(self):
        slug = self.kwargs["section"]
        if slug not in PREVIEW_SECTIONS:
            raise Http404
        return [f"portal/preview/{slug}.html"]


class AdminHubView(LoginRequiredMixin, TemplateView):
    """Tiles to the management pages the user may open. Not a new permission: users without any management right get 403."""

    template_name = "portal/admin_hub.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_open_hub(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tiles"] = tiles_for(self.request.user)
        return context
