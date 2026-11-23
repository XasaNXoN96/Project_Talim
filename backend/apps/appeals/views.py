from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import PortalPermissionMixin
from apps.core.network import client_ip

from .forms import AnswerForm, AppealForm, StatusForm
from .models import Appeal

SEND_LIMIT = 5  # appeals per address per hour
LOOKUP_LIMIT = 10  # status look-ups per address per 10 minutes


def _hit(key, limit, seconds):
    """Count one use of `key`; True while still within the limit."""
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key) <= limit
    except ValueError:
        cache.set(key, 1, seconds)
        return True


class AppealCreateView(View):
    def get(self, request):
        return render(request, "appeals/form.html", {"form": AppealForm()})

    def post(self, request):
        form = AppealForm(request.POST)
        ip = client_ip(request) or "unknown"
        if not _hit(f"appeal-send:{ip}", SEND_LIMIT, 3600):
            form.add_error(None, _("Juda ko‘p murojaat yuborildi. Iltimos, birozdan keyin urinib ko‘ring."))
            return render(request, "appeals/form.html", {"form": form}, status=429)
        if not form.is_valid():
            return render(request, "appeals/form.html", {"form": form}, status=400 if "website" in form.errors else 200)
        appeal = form.save()
        return render(request, "appeals/done.html", {"appeal": appeal})


class AppealStatusView(View):
    def get(self, request):
        initial = {"code": (request.GET.get("code") or "").strip().upper()[:12]}
        return render(request, "appeals/status.html", {"form": StatusForm(initial=initial)})

    def post(self, request):
        form = StatusForm(request.POST)
        ip = client_ip(request) or "unknown"
        if not _hit(f"appeal-look:{ip}", LOOKUP_LIMIT, 600):
            form.add_error(None, _("Juda ko‘p urinish. Iltimos, birozdan keyin urinib ko‘ring."))
            return render(request, "appeals/status.html", {"form": form}, status=429)
        appeal = None
        if form.is_valid():
            candidate = Appeal.objects.filter(code=form.cleaned_data["code"].strip().upper()).first()
            if candidate and candidate.phone_tail() == form.cleaned_data["phone_tail"]:
                appeal = candidate
            else:  # the same message for a wrong code and a wrong number: nobody can probe which codes exist
                form.add_error(None, _("Bunday murojaat topilmadi. Kod va telefonning oxirgi 4 raqamini tekshiring."))
        return render(request, "appeals/status.html", {"form": form, "appeal": appeal})


class AppealListView(PortalPermissionMixin, ListView):
    permission_required = "appeals.view_appeal"
    template_name = "appeals/list.html"
    context_object_name = "appeals"
    paginate_by = 20

    def get_queryset(self):
        qs = Appeal.objects.all()
        status = self.request.GET.get("status") or ""
        q = (self.request.GET.get("q") or "").strip()[:60]
        if status in dict(Appeal.Status.choices):
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(full_name__icontains=q) | Q(message__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status") or ""
        context["q"] = (self.request.GET.get("q") or "").strip()[:60]
        context["statuses"] = Appeal.Status.choices
        context["counts"] = Appeal.objects.aggregate(new=Count("id", filter=Q(status="new")), total=Count("id"))
        return context


class AppealDetailView(PortalPermissionMixin, View):
    permission_required = "appeals.view_appeal"

    def get(self, request, pk):
        appeal = get_object_or_404(Appeal, pk=pk)
        if appeal.status == Appeal.Status.NEW and request.user.has_perm("appeals.answer_appeal"):
            Appeal.objects.filter(pk=pk, status=Appeal.Status.NEW).update(status=Appeal.Status.IN_PROGRESS)
            appeal.status = Appeal.Status.IN_PROGRESS
        form = AnswerForm(initial={"status": appeal.status if appeal.status != Appeal.Status.NEW else Appeal.Status.IN_PROGRESS, "answer": appeal.answer})
        return render(request, "appeals/detail.html", {"appeal": appeal, "form": form, "can_answer": request.user.has_perm("appeals.answer_appeal")})

    def post(self, request, pk):
        appeal = get_object_or_404(Appeal, pk=pk)
        if not request.user.has_perm("appeals.answer_appeal"):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        form = AnswerForm(request.POST)
        if not form.is_valid():
            return render(request, "appeals/detail.html", {"appeal": appeal, "form": form, "can_answer": True})
        appeal.status = form.cleaned_data["status"]
        appeal.answer = (form.cleaned_data["answer"] or "").strip()
        appeal.answered_by = request.user
        appeal.answered_at = timezone.now()
        appeal.save(update_fields=["status", "answer", "answered_by", "answered_at"])
        messages.success(request, _("Javob saqlandi."))
        return redirect("appeals_admin:detail", pk=appeal.pk)
