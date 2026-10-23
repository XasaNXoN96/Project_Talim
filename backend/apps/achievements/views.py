from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin
from apps.core.ranged import ranged_file_response
from apps.organization.models import Institution

from . import workflow
from .forms import AchievementForm, CommentForm
from .models import Achievement, AchievementImage, AchievementVideo

PREVIEW_SESSION_KEY = "achievement_preview_tokens"


def _file_response(image, *, public):
    try:
        handle = image.file.storage.open(image.file.name, "rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    response = FileResponse(handle, content_type="image/jpeg")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600" if public else "private, no-cache"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


def _video_response(request, video, *, public):
    """The video with Range support (browsers seek with it). Call it AFTER the permission check."""
    return ranged_file_response(request, video.file, video.content_type, public=public)


def _school_for(user):
    """The Institution of a school user; 403 when the account has none (it cannot send achievements for nobody)."""
    sid = workflow.school_id(user)
    school = Institution.objects.filter(pk=sid).first() if sid else None
    if school is None:
        raise PermissionDenied
    return school


class AchievementListView(PortalPermissionMixin, ListView):
    permission_required = "achievements.view_achievement"
    template_name = "portal/achievements/list.html"
    paginate_by = 20
    context_object_name = "items"

    def get_queryset(self):
        g = self.request.GET
        qs = workflow.visible_achievements(self.request.user).select_related("institution").annotate(n_images=Count("images"))
        if g.get("kind") in Achievement.Kind.values:
            qs = qs.filter(kind=g["kind"])
        if g.get("status") in Achievement.Status.values:
            qs = qs.filter(status=g["status"])
        if g.get("institution") and workflow.is_staff(self.request.user):
            try:
                qs = qs.filter(institution_id=g["institution"])
            except (ValueError, TypeError, ValidationError):
                qs = qs.none()
        q = (g.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(person_name__icontains=q) | Q(description__icontains=q))
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        user = self.request.user
        counts = dict(workflow.visible_achievements(user).values_list("status").annotate(n=Count("pk")).order_by())
        ctx.update(
            kind=g.get("kind", ""), status=g.get("status", ""), q=g.get("q", ""), institution=g.get("institution", ""),
            kinds=Achievement.Kind.choices, statuses=[(c, l, counts.get(c, 0)) for c, l in Achievement.Status.choices],
            institutions=Institution.objects.all() if workflow.is_staff(user) else [], is_staff=workflow.is_staff(user),
            can_add=user.has_perm("achievements.add_achievement"),
        )
        return ctx


class _ItemView(PortalPermissionMixin, View):
    permission_required = "achievements.view_achievement"

    def get_item(self, request, pk):
        return get_object_or_404(workflow.visible_achievements(request.user), pk=pk)  # not visible to you -> 404


class AchievementCreateView(PortalPermissionMixin, View):
    permission_required = "achievements.add_achievement"

    def _form(self, request, data=None, files=None):
        staff = workflow.is_staff(request.user)
        return AchievementForm(data, files, request=request, staff=staff, school=None if staff else _school_for(request.user))

    def get(self, request):
        return render(request, "portal/achievements/form.html", {"form": self._form(request), "creating": True})

    def post(self, request):
        form = self._form(request, request.POST, request.FILES)
        if form.is_valid():
            form.instance.created_by = request.user
            a = form.save()
            record(AuditLog.Action.ACHIEVEMENT_CREATED, request=request, user=request.user, object_type="Achievement", object_id=a.pk,
                   meta={"fields": sorted(form.changed_data)})
            messages.success(request, _("Yutuq qoralama sifatida saqlandi. Tayyor bo‘lgach, tekshiruvga yuboring."))
            return redirect("achievements:detail", pk=a.pk)
        return render(request, "portal/achievements/form.html", {"form": form, "creating": True})


class AchievementEditView(_ItemView):
    permission_required = "achievements.change_achievement"

    def _item(self, request, pk):
        a = self.get_item(request, pk)
        if not workflow.can_edit(a, request.user):
            raise PermissionDenied
        return a

    def _form(self, request, a, data=None, files=None):
        staff = workflow.is_staff(request.user)
        return AchievementForm(data, files, instance=a, request=request, staff=staff, school=None if staff else _school_for(request.user))

    def get(self, request, pk):
        a = self._item(request, pk)
        return render(request, "portal/achievements/form.html", {"form": self._form(request, a), "a": a})

    def post(self, request, pk):
        a = self._item(request, pk)
        form = self._form(request, a, request.POST, request.FILES)
        if form.is_valid():
            changed = sorted(f for f in form.changed_data if f not in ("new_images", "remove_images"))
            if form.cleaned_data.get("new_images") or form.cleaned_data.get("remove_images"):
                changed.append("images")
            form.save()
            record(AuditLog.Action.ACHIEVEMENT_UPDATED, request=request, user=request.user, object_type="Achievement", object_id=a.pk, meta={"fields": changed})
            messages.success(request, _("Ma’lumotlar saqlandi."))
            return redirect("achievements:detail", pk=a.pk)
        return render(request, "portal/achievements/form.html", {"form": form, "a": a})


def _context(request, a, *, preview=False):
    steps = workflow.allowed_steps(a, request.user)
    labels = {
        "submit": _("Tekshiruvga yuborish"), "withdraw": _("Qaytarib olish"), "request_changes": _("Tuzatishga qaytarish"),
        "save_draft": _("Tayyor qoralama sifatida saqlash"), "publish": _("Nashr etish"), "unpublish": _("Nashrdan olish"),
        "archive": _("Arxivlash"), "restore": _("Arxivdan qaytarish"),
    }
    return {
        "a": a, "images": a.images.all(), "history": a.reviews.select_related("actor"), "steps": steps,
        "step_buttons": [(s, labels[s]) for s in steps if s not in ("publish", "request_changes")],
        "request_changes_label": labels["request_changes"],
        "can_edit": workflow.can_edit(a, request.user), "is_staff": workflow.is_staff(request.user),
        "comment_form": CommentForm(), "preview": preview, "version": workflow.version_token(a),
    }


class AchievementDetailView(_ItemView):
    def get(self, request, pk):
        a = self.get_item(request, pk)
        return render(request, "portal/achievements/detail.html", _context(request, a))


class AchievementPreviewView(_ItemView):
    """Shows the item exactly as the public page will show it. Opening it hands out the token that publishing requires."""

    def get(self, request, pk):
        a = self.get_item(request, pk)
        tokens = request.session.get(PREVIEW_SESSION_KEY, {})
        tokens[str(a.pk)] = workflow.version_token(a)
        request.session[PREVIEW_SESSION_KEY] = tokens
        return render(request, "portal/achievements/preview.html", _context(request, a, preview=True))


class AchievementStepView(_ItemView):
    http_method_names = ["post"]

    def post(self, request, pk, step):
        a = self.get_item(request, pk)
        if step not in workflow.STEPS:
            raise Http404
        token = request.session.get(PREVIEW_SESSION_KEY, {}).get(str(a.pk), "") if step == "publish" else ""
        try:
            a = workflow.perform(step, a.pk, request.user, comment=request.POST.get("comment", ""), previewed_token=token, request=request)
        except workflow.WorkflowError as exc:
            messages.error(request, str(exc))
            target = "achievements:preview" if step == "publish" else "achievements:detail"
            return redirect(target, pk=a.pk)
        if step == "publish":
            request.session.get(PREVIEW_SESSION_KEY, {}).pop(str(a.pk), None)
            request.session.modified = True
        messages.success(request, workflow.STEPS[step].success)
        return redirect("achievements:detail", pk=a.pk)


class AchievementImageView(PortalPermissionMixin, View):
    permission_required = "achievements.view_achievement"

    def get(self, request, pk):
        image = get_object_or_404(AchievementImage.objects.filter(achievement__in=workflow.visible_achievements(request.user)), pk=pk)
        return _file_response(image, public=False)


class AchievementVideoView(PortalPermissionMixin, View):
    permission_required = "achievements.view_achievement"

    def get(self, request, pk):
        video = get_object_or_404(AchievementVideo.objects.filter(achievement__in=workflow.visible_achievements(request.user)), pk=pk)
        return _video_response(request, video, public=False)


# ---- public site ------------------------------------------------------------------------------------------------

class PublicListView(ListView):
    template_name = "achievements/list.html"
    context_object_name = "items"
    paginate_by = 12

    def get_queryset(self):
        qs = Achievement.objects.published().select_related("institution").prefetch_related("images")
        kind = self.request.GET.get("kind")
        return qs.filter(kind=kind) if kind in Achievement.Kind.values else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(kinds=Achievement.Kind.choices, kind=self.request.GET.get("kind", ""))
        return ctx


class PublicDetailView(View):
    def get(self, request, slug):
        a = get_object_or_404(Achievement.objects.published().select_related("institution"), slug=slug)
        return render(request, "achievements/detail.html", {"a": a, "images": a.images.all(), "public": True})


class PublicImageView(View):
    def get(self, request, pk):
        image = get_object_or_404(AchievementImage.objects.filter(achievement__in=Achievement.objects.published()), pk=pk)
        return _file_response(image, public=True)


class PublicVideoView(View):
    def get(self, request, pk):
        video = get_object_or_404(AchievementVideo.objects.filter(achievement__in=Achievement.objects.published()), pk=pk)
        return _video_response(request, video, public=True)
