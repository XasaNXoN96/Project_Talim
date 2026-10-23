from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from . import services
from .models import Conversation, Message


class _ChatBase(PortalPermissionMixin, View):
    """Everything in the chat needs `use_chat` AND that the person has read the notice (kept and readable by administrators)."""

    permission_required = "chat.use_chat"
    needs_notice = True

    def dispatch(self, request, *args, **kwargs):
        u = request.user
        if self.needs_notice and u.is_authenticated and u.has_perm("chat.use_chat") and not services.has_accepted(u):
            return redirect("chat:notice")
        return super().dispatch(request, *args, **kwargs)


class NoticeView(_ChatBase):
    needs_notice = False

    def get(self, request):
        return render(request, "portal/chat/notice.html", {"accepted": services.has_accepted(request.user)})

    def post(self, request):
        if request.POST.get("agree") != "1":
            messages.error(request, _("Davom etish uchun ogohlantirish bilan tanishganingizni tasdiqlang."))
            return redirect("chat:notice")
        services.accept_notice(request.user)
        record(AuditLog.Action.CHAT_NOTICE_ACCEPTED, request=request, user=request.user, object_type="User", object_id=request.user.pk)
        return redirect("chat:inbox")


class InboxView(_ChatBase):
    def get(self, request):
        q = (request.GET.get("q") or "").strip()[:100]
        people = services.chat_users().exclude(pk=request.user.pk).select_related("employee__institution", "employee__position")
        if q:
            people = people.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q) | Q(employee__institution__name__icontains=q))
        return render(request, "portal/chat/inbox.html", {
            "items": services.summaries(request.user), "q": q, "people": people.order_by("last_name", "first_name", "username")[:30],
            "can_audit": request.user.has_perm("chat.audit_chat"),
        })


class StartView(_ChatBase):
    http_method_names = ["post"]

    def post(self, request):
        other = services.chat_users().filter(pk=request.POST.get("user") or None).first() if _is_uuid(request.POST.get("user")) else None
        if other is None:
            messages.error(request, _("Bu foydalanuvchi bilan yozishib bo‘lmaydi."))
            return redirect("chat:inbox")
        try:
            conv = services.start(request.user, other)
        except services.ChatError as exc:
            messages.error(request, str(exc))
            return redirect("chat:inbox")
        return redirect("chat:thread", pk=conv.pk)


def _is_uuid(value):
    import uuid

    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


class ThreadView(_ChatBase):
    def _conv(self, request, pk):
        return get_object_or_404(services.my_conversations(request.user), pk=pk)  # somebody else's conversation does not exist for you

    def get(self, request, pk):
        conv = self._conv(request, pk)
        services.mark_read(request.user, conv)
        return render(request, "portal/chat/thread.html", {
            "conv": conv, "other": conv.other(request.user), "messages_list": conv.messages.select_related("sender"), "max_body": services.MAX_BODY,
        })

    def post(self, request, pk):
        conv = self._conv(request, pk)
        try:
            services.send(request.user, conv, request.POST.get("body", ""))
        except services.ChatError as exc:
            messages.error(request, str(exc))
        return redirect("chat:thread", pk=conv.pk)


class ArchiveListView(PortalPermissionMixin, ListView):
    """All conversations, for administrators. Opening one is recorded in the audit log."""

    permission_required = "chat.audit_chat"
    template_name = "portal/chat/archive.html"
    paginate_by = 30
    context_object_name = "conversations"

    def get_queryset(self):
        qs = Conversation.objects.select_related("user_low", "user_high").annotate(n=Count("messages")).filter(n__gt=0)
        q = (self.request.GET.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(user_low__last_name__icontains=q) | Q(user_low__first_name__icontains=q) | Q(user_low__username__icontains=q)
                           | Q(user_high__last_name__icontains=q) | Q(user_high__first_name__icontains=q) | Q(user_high__username__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


class ArchiveThreadView(PortalPermissionMixin, View):
    permission_required = "chat.audit_chat"

    def get(self, request, pk):
        conv = get_object_or_404(Conversation.objects.select_related("user_low", "user_high"), pk=pk)
        record(AuditLog.Action.CHAT_ARCHIVE_VIEWED, request=request, user=request.user, object_type="Conversation", object_id=conv.pk,
               meta={"participants": [str(conv.user_low_id), str(conv.user_high_id)]})
        return render(request, "portal/chat/archive_thread.html", {"conv": conv, "messages_list": conv.messages.select_related("sender")})
