from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from apps.achievements import workflow as ach_workflow
from apps.content import workflow as news_workflow
from apps.core.mixins import PortalPermissionMixin
from apps.tasks import access as task_access

from .models import Notification
from .services import mark_all_read


class NotificationListView(PortalPermissionMixin, ListView):
    permission_required = "notifications.view_notification"
    template_name = "portal/notifications/list.html"
    paginate_by = 30
    context_object_name = "notifications"

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).select_related("task", "news", "achievement")
        if self.request.GET.get("unread") == "1":
            qs = qs.filter(read_at__isnull=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        visible = set(task_access.visible_tasks(user).filter(pk__in=[n.task_id for n in ctx["notifications"] if n.task_id]).values_list("pk", flat=True))
        can_news = user.has_perm("content.view_news")
        news_ids = {n.news_id for n in ctx["notifications"] if n.news_id}
        visible_news = set(news_workflow.visible_news(user).filter(pk__in=news_ids).values_list("pk", flat=True)) if can_news and news_ids else set()
        ach_ids = {n.achievement_id for n in ctx["notifications"] if n.achievement_id}
        visible_ach = set(ach_workflow.visible_achievements(user).filter(pk__in=ach_ids).values_list("pk", flat=True)) if ach_ids else set()
        for n in ctx["notifications"]:
            if n.achievement_id:
                n.target_visible = n.achievement_id in visible_ach
                continue
            n.target_visible = (n.news_id in visible_news if n.news_id else n.task_id in visible)  # the link is offered only if the task can still be opened
        ctx["only_unread"] = self.request.GET.get("unread") == "1"
        return ctx


class NotificationOpenView(PortalPermissionMixin, View):
    """Marks one notification (own only) as read and goes to its task, if the user may still see it."""

    http_method_names = ["post"]
    permission_required = "notifications.view_notification"

    def post(self, request, pk):
        n = get_object_or_404(Notification, pk=pk, user=request.user)  # someone else's id -> 404
        if n.read_at is None:
            n.read_at = timezone.now()
            n.save(update_fields=["read_at"])
        if n.achievement_id:
            if ach_workflow.visible_achievements(request.user).filter(pk=n.achievement_id).exists():
                return redirect("achievements:detail", pk=n.achievement_id)
            messages.info(request, _("Bu yutuqni ko‘rishga ruxsatingiz yo‘q yoki u o‘chirilgan."))
            return redirect("notifications:list")
        if n.news_id:
            if request.user.has_perm("content.view_news") and news_workflow.visible_news(request.user).filter(pk=n.news_id).exists():
                return redirect("news_admin:preview", pk=n.news_id)
            messages.info(request, _("Bu yangilikni ko‘rishga ruxsatingiz yo‘q yoki u o‘chirilgan."))
            return redirect("notifications:list")
        if n.task_id and task_access.visible_tasks(request.user).filter(pk=n.task_id).exists():
            return redirect("tasks:detail", pk=n.task_id)
        messages.info(request, _("Bu topshiriqni ko‘rishga ruxsatingiz yo‘q yoki u o‘chirilgan."))
        return redirect("notifications:list")


class NotificationReadView(PortalPermissionMixin, View):
    http_method_names = ["post"]
    permission_required = "notifications.view_notification"

    def post(self, request, pk):
        n = get_object_or_404(Notification, pk=pk, user=request.user)
        if n.read_at is None:
            n.read_at = timezone.now()
            n.save(update_fields=["read_at"])
        return redirect("notifications:list")


class NotificationReadAllView(PortalPermissionMixin, View):
    http_method_names = ["post"]
    permission_required = "notifications.view_notification"

    def post(self, request):
        mark_all_read(request.user)
        return redirect("notifications:list")
