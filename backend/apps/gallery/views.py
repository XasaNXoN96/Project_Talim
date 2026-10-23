from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin
from apps.core.ranged import ranged_file_response
from apps.organization.models import Institution

from .forms import ItemForm, PhotoUploadForm, VideoUploadForm
from .models import MediaItem

PER_PAGE = 24


def _list_url(kind):
    from django.urls import reverse

    return reverse("gallery:list") + ("?type=video" if kind == MediaItem.Kind.VIDEO else "")


def can_curate(user):
    return user.is_authenticated and user.is_active and user.has_perm("gallery.publish_mediaitem")


def visible_items(user):
    """Staff (who may publish) see everything; everybody else with a portal account only what is published."""
    qs = MediaItem.objects.all()
    return qs if can_curate(user) else qs.published()


def file_response(request, item, variant, *, public):
    """A photo (full or thumbnail) or a video, from the private storage. Call it AFTER the visibility check."""
    if item.kind == MediaItem.Kind.VIDEO:
        if variant != "full":
            raise Http404
        return ranged_file_response(request, item.file, item.content_type, public=public)
    field = item.thumb if variant == "thumb" and item.thumb else item.file
    try:
        handle = field.storage.open(field.name, "rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    response = FileResponse(handle, content_type="image/jpeg")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=3600" if public else "private, no-cache"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


class MediaListView(PortalPermissionMixin, ListView):
    permission_required = "gallery.view_mediaitem"
    template_name = "portal/media/list.html"
    paginate_by = PER_PAGE
    context_object_name = "items"

    def get_queryset(self):
        g = self.request.GET
        qs = visible_items(self.request.user).select_related("institution")
        qs = qs.filter(kind=MediaItem.Kind.VIDEO if g.get("type") == "video" else MediaItem.Kind.PHOTO)
        if can_curate(self.request.user) and g.get("status") in MediaItem.Status.values:
            qs = qs.filter(status=g["status"])
        q = (g.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(institution__name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g, user = self.request.GET, self.request.user
        base = visible_items(user)
        ctx.update(
            tab="video" if g.get("type") == "video" else "photo", q=g.get("q", ""), status=g.get("status", ""), statuses=MediaItem.Status.choices,
            n_photo=base.filter(kind=MediaItem.Kind.PHOTO).count(), n_video=base.filter(kind=MediaItem.Kind.VIDEO).count(),
            curator=can_curate(user), can_add=user.has_perm("gallery.add_mediaitem"),
        )
        return ctx


class _UploadView(PortalPermissionMixin, View):
    permission_required = "gallery.add_mediaitem"
    form_class = None
    template_name = "portal/media/upload.html"
    title = ""

    def get(self, request):
        return render(request, self.template_name, {"form": self.form_class(request=request), "title": self.title, "video": self.form_class is VideoUploadForm})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES, request=request)
        if form.is_valid():
            with transaction.atomic():
                items = form.save(request.user)
                record(AuditLog.Action.MEDIA_UPLOADED, request=request, user=request.user, object_type="MediaItem", object_id=items[0].pk,
                       meta={"kind": items[0].kind, "count": len(items), "ids": [str(i.pk) for i in items]})
            messages.success(request, gettext("Yuklandi: %(n)d ta fayl. Ular qoralama holatida: tekshirib, nashr eting.") % {"n": len(items)})
            return redirect(_list_url(items[0].kind))
        return render(request, self.template_name, {"form": form, "title": self.title, "video": self.form_class is VideoUploadForm})


class PhotoUploadView(_UploadView):
    form_class = PhotoUploadForm
    title = _("Fotorasmlar yuklash")


class VideoUploadView(_UploadView):
    form_class = VideoUploadForm
    title = _("Video yuklash")


class _ItemView(PortalPermissionMixin, View):
    def get_item(self, request, pk):
        return get_object_or_404(visible_items(request.user), pk=pk)


class ItemEditView(_ItemView):
    permission_required = "gallery.change_mediaitem"

    def get(self, request, pk):
        item = self.get_item(request, pk)
        return render(request, "portal/media/edit.html", {"form": ItemForm(instance=item), "item": item})

    def post(self, request, pk):
        item = self.get_item(request, pk)
        form = ItemForm(request.POST, instance=item)
        if form.is_valid():
            changed = sorted(form.changed_data)
            form.save()
            record(AuditLog.Action.MEDIA_CHANGED, request=request, user=request.user, object_type="MediaItem", object_id=item.pk, meta={"action": "edit", "fields": changed})
            messages.success(request, _("Ma’lumotlar saqlandi."))
            return redirect(_list_url(item.kind))
        return render(request, "portal/media/edit.html", {"form": form, "item": item})


class ItemDeleteView(_ItemView):
    """Erases the record AND the files from the disk (a person may ask for their picture to be removed)."""

    permission_required = "gallery.erase_mediaitem"

    def get(self, request, pk):
        return render(request, "portal/media/delete.html", {"item": self.get_item(request, pk)})

    def post(self, request, pk):
        item = self.get_item(request, pk)
        names = [(f.storage, f.name) for f in (item.file, item.thumb) if f and f.name]
        kind, item_id = item.kind, item.pk
        item.delete()
        for storage, name in names:
            storage.delete(name)
        record(AuditLog.Action.MEDIA_CHANGED, request=request, user=request.user, object_type="MediaItem", object_id=item_id, meta={"action": "delete", "kind": kind})
        messages.success(request, _("Fayl o‘chirildi."))
        return redirect(_list_url(kind))


class BulkView(PortalPermissionMixin, View):
    """Publish or unpublish the ticked items. Publishing needs the consent flag on each one: the others are skipped and reported."""

    http_method_names = ["post"]
    permission_required = "gallery.publish_mediaitem"

    def post(self, request):
        action = request.POST.get("action")
        ids = [i for i in request.POST.getlist("ids") if _is_uuid(i)]
        back = request.POST.get("next", "")
        back = back if back.startswith("/portal/media/") else "/portal/media/"
        if action not in ("publish", "unpublish") or not ids:
            messages.error(request, _("Avval fayllarni belgilang va amalni tanlang."))
            return redirect(back)
        done = skipped = 0
        with transaction.atomic():
            for item in MediaItem.objects.select_for_update().filter(pk__in=ids):
                if action == "publish":
                    if item.status == MediaItem.Status.PUBLISHED:
                        continue
                    if not item.consent_confirmed:
                        skipped += 1
                        continue
                    item.status, item.publish_at = MediaItem.Status.PUBLISHED, timezone.now()
                else:
                    if item.status != MediaItem.Status.PUBLISHED:
                        continue
                    item.status = MediaItem.Status.DRAFT
                item.save()
                done += 1
            record(AuditLog.Action.MEDIA_CHANGED, request=request, user=request.user, object_type="MediaItem", meta={"action": action, "count": done, "skipped": skipped, "ids": ids[:50]})
        if done:
            messages.success(request, gettext("Bajarildi: %(n)d ta fayl.") % {"n": done})
        if skipped:
            messages.error(request, gettext("%(n)d ta faylda nashrga rozilik belgilanmagan: ular nashr etilmadi.") % {"n": skipped})
        return redirect(back)


def _is_uuid(value):
    import uuid

    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


class FileView(PortalPermissionMixin, View):
    permission_required = "gallery.view_mediaitem"

    def get(self, request, pk, variant):
        if variant not in ("full", "thumb"):
            raise Http404
        item = get_object_or_404(visible_items(request.user), pk=pk)
        return file_response(request, item, variant, public=False)


# ---- public site ----------------------------------------------------------------------------------------------------

class PublicListView(ListView):
    template_name = "media/list.html"
    context_object_name = "items"
    paginate_by = PER_PAGE

    def get_queryset(self):
        kind = MediaItem.Kind.VIDEO if self.request.GET.get("type") == "video" else MediaItem.Kind.PHOTO
        return MediaItem.objects.published().filter(kind=kind).select_related("institution")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        published = MediaItem.objects.published()
        ctx.update(tab="video" if self.request.GET.get("type") == "video" else "photo",
                   n_photo=published.filter(kind=MediaItem.Kind.PHOTO).count(), n_video=published.filter(kind=MediaItem.Kind.VIDEO).count())
        return ctx


class PublicFileView(View):
    def get(self, request, pk, variant):
        if variant not in ("full", "thumb"):
            raise Http404
        item = get_object_or_404(MediaItem.objects.published(), pk=pk)
        return file_response(request, item, variant, public=True)
