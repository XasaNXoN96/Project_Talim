import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from . import access, files, services
from .forms import DocumentCreateForm, DocumentForm, VersionForm
from .models import Document, DocumentCategory
from .validation import UploadRejected


def _audit(action, request, document, **meta):
    record(action, request=request, user=request.user, object_type="Document", object_id=document.pk, meta=meta)


class DocumentListView(PortalPermissionMixin, ListView):
    permission_required = "documents.view_document"
    template_name = "portal/documents/list.html"
    paginate_by = 25
    context_object_name = "documents"

    def get_queryset(self):
        qs = access.visible_documents(self.request.user).select_related("category", "created_by")
        g = self.request.GET
        q = (g.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(number__icontains=q) | Q(description__icontains=q))
        if g.get("category"):
            try:
                qs = qs.filter(category_id=uuid.UUID(g["category"]))
            except ValueError:
                qs = qs.none()
        if g.get("level") in Document.Access.values:
            qs = qs.filter(access_level=g["level"])
        if g.get("status") == "archived":
            qs = qs.filter(status=Document.Status.ARCHIVED)
        else:
            qs = qs.filter(status=Document.Status.ACTIVE)
        return qs.order_by("-doc_date", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        ctx.update(
            q=g.get("q", ""), category=g.get("category", ""), level=g.get("level", ""), status=g.get("status", ""),
            categories=DocumentCategory.objects.filter(is_active=True), levels=Document.Access.choices,
            can_add=access.can_add(self.request.user), can_see_archive=self.request.user.has_perm("documents.view_all_documents"),
        )
        return ctx


class _DocBase(PortalPermissionMixin, View):
    permission_required = "documents.view_document"

    def get_document(self, request, pk):
        document = get_object_or_404(Document.objects.select_related("category", "created_by", "department"), pk=pk)
        if not access.can_view(request.user, document):
            raise PermissionDenied
        return document


class DocumentDetailView(_DocBase):
    def get(self, request, pk):
        document = self.get_document(request, pk)
        if document.access_level == Document.Access.CONFIDENTIAL:
            _audit(AuditLog.Action.DOCUMENT_VIEWED, request, document)
        return render(request, "portal/documents/detail.html", {
            "d": document, "versions": document.versions.select_related("uploaded_by"), "can_edit": access.can_edit(request.user, document),
            "version_form": VersionForm(),
        })


class DocumentCreateView(PortalPermissionMixin, View):
    permission_required = "documents.add_document"

    def get(self, request):
        return render(request, "portal/documents/form.html", {"form": DocumentCreateForm(), "creating": True})

    def post(self, request):
        form = DocumentCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                checked = services.check_or_audit(form.cleaned_data["file"], request=request, user=request.user)
            except UploadRejected as exc:
                form.add_error("file", str(exc))
            else:
                with transaction.atomic():
                    document = Document(created_by=request.user, **{k: v for k, v in form.cleaned_data.items() if k != "file"})
                    document.save()
                    version = services.add_version(document, checked, actor=request.user)
                    _audit(AuditLog.Action.DOCUMENT_UPLOADED, request, document, version=version.number, size=version.size, ext=version.extension)
                messages.success(request, "Hujjat yuklandi.")
                return redirect("documents:detail", pk=document.pk)
        return render(request, "portal/documents/form.html", {"form": form, "creating": True})


class DocumentEditView(_DocBase):
    permission_required = "documents.change_document"

    def _doc(self, request, pk):
        document = self.get_document(request, pk)
        if not access.can_edit(request.user, document):
            raise PermissionDenied
        return document

    def get(self, request, pk):
        d = self._doc(request, pk)
        return render(request, "portal/documents/form.html", {"form": DocumentForm(instance=d), "d": d})

    def post(self, request, pk):
        d = self._doc(request, pk)
        form = DocumentForm(request.POST, instance=d)
        if form.is_valid():
            changed = sorted(form.changed_data)
            form.save()
            if changed:
                _audit(AuditLog.Action.DOCUMENT_UPDATED, request, d, fields=changed)
            messages.success(request, "Saqlandi.")
            return redirect("documents:detail", pk=d.pk)
        return render(request, "portal/documents/form.html", {"form": form, "d": d})


class VersionAddView(_DocBase):
    http_method_names = ["post"]
    permission_required = "documents.change_document"

    def post(self, request, pk):
        d = self.get_document(request, pk)
        if not access.can_edit(request.user, d) or d.status == Document.Status.ARCHIVED:
            raise PermissionDenied
        form = VersionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                checked = services.check_or_audit(form.cleaned_data["file"], request=request, user=request.user)
            except UploadRejected as exc:
                messages.error(request, str(exc))
            else:
                v = services.add_version(d, checked, actor=request.user, comment=form.cleaned_data["comment"])
                _audit(AuditLog.Action.DOCUMENT_VERSION_ADDED, request, d, version=v.number, size=v.size, ext=v.extension)
                messages.success(request, f"Yangi versiya (v{v.number}) yuklandi.")
        else:
            messages.error(request, "Fayl tanlanmagan yoki noto‘g‘ri.")
        return redirect("documents:detail", pk=d.pk)


class DocumentDownloadView(_DocBase):
    def get(self, request, pk, number=None):
        d = self.get_document(request, pk)  # permission is decided BEFORE any file is opened
        versions = d.versions
        version = versions.filter(number=number).first() if number else versions.order_by("-number").first()
        if version is None:
            raise Http404
        if version.scan_status == "infected":
            raise Http404  # quarantined by a later scan: never served
        response = files.download_response(version.file, filename=files.safe_download_name(d.title, f"_v{version.number}.{version.extension}"))
        _audit(AuditLog.Action.DOCUMENT_DOWNLOADED, request, d, version=version.number)
        return response


class DocumentArchiveView(_DocBase):
    http_method_names = ["post"]
    permission_required = "documents.change_document"
    restore = False

    def post(self, request, pk):
        d = self.get_document(request, pk)
        if not access.can_edit(request.user, d):
            raise PermissionDenied
        d.status = Document.Status.ACTIVE if self.restore else Document.Status.ARCHIVED
        d.save(update_fields=["status", "updated_at"])
        _audit(AuditLog.Action.DOCUMENT_RESTORED if self.restore else AuditLog.Action.DOCUMENT_ARCHIVED, request, d)
        messages.success(request, "Hujjat arxivdan qaytarildi." if self.restore else "Hujjat arxivlandi.")
        return redirect("documents:detail", pk=d.pk)
