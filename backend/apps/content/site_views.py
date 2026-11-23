"""Portal pages that edit the home page blocks (announcement strip, calendar, leadership, FAQ). One small CRUD for four models."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views import View

from apps.core.mixins import PortalPermissionMixin

from .site_forms import KINDS


def _kind(kind):
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


class SiteIndexView(PortalPermissionMixin, View):
    permission_required = "content.manage_site"

    def get(self, request):
        cards = [(code, label, model.objects.count()) for code, (model, _form, label, _cols) in KINDS.items()]
        return render(request, "portal/site/index.html", {"cards": cards})


class SiteListView(PortalPermissionMixin, View):
    permission_required = "content.manage_site"

    def get(self, request, kind):
        model, _form, label, cols = _kind(kind)
        items = list(model.objects.all()[:200])
        return render(request, "portal/site/list.html", {"kind": kind, "label": label, "items": items, "cols": cols})


class SiteFormView(PortalPermissionMixin, View):
    permission_required = "content.manage_site"

    def _obj(self, kind, pk):
        model = _kind(kind)[0]
        return get_object_or_404(model, pk=pk) if pk else None

    def get(self, request, kind, pk=None):
        _model, form_cls, label, _cols = _kind(kind)
        obj = self._obj(kind, pk)
        return render(request, "portal/site/form.html", {"kind": kind, "label": label, "form": form_cls(instance=obj, request=request), "obj": obj})

    def post(self, request, kind, pk=None):
        _model, form_cls, label, _cols = _kind(kind)
        obj = self._obj(kind, pk)
        form = form_cls(request.POST, request.FILES, instance=obj, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Saqlandi."))
            return redirect("site_admin:list", kind=kind)
        return render(request, "portal/site/form.html", {"kind": kind, "label": label, "form": form, "obj": obj})


class SiteDeleteView(PortalPermissionMixin, View):
    permission_required = "content.manage_site"

    def post(self, request, kind, pk):
        model = _kind(kind)[0]
        get_object_or_404(model, pk=pk).delete()
        messages.success(request, _("O‘chirildi."))
        return redirect("site_admin:list", kind=kind)
