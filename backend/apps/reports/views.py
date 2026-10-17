from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.utils.translation import gettext

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from . import exports
from .services import FilterForm, build_report


def _form(request):
    return FilterForm(request.GET or None, user=request.user)


def _filters_for_audit(cleaned):
    return {
        "from": cleaned["date_from"].isoformat(), "to": cleaned["date_to"].isoformat(),
        "department": str(cleaned["department"].pk) if cleaned.get("department") else "",
        "status": cleaned.get("status") or "", "category": str(cleaned["category"].pk) if cleaned.get("category") else "",
    }


class ReportView(PortalPermissionMixin, View):
    permission_required = "reports.view_reports"

    def get(self, request):
        form = FilterForm(request.GET or {}, user=request.user)  # an empty GET still validates: defaults = the last 30 days
        ctx = {"form": form, "query": request.GET.urlencode(), "can_export": request.user.has_perm("reports.export_reports"), "error": None}
        if not form.is_valid():
            return render(request, "portal/reports/index.html", ctx)
        try:
            data = build_report(request.user, form.cleaned_data)
        except PermissionError:
            raise PermissionDenied from None
        except Exception:  # noqa: BLE001  # a failing query must show an error state, never a stack trace
            import logging

            logging.getLogger(__name__).exception("Report failed")
            ctx["error"] = True
            return render(request, "portal/reports/index.html", ctx, status=500)
        if "people" in data.sections:
            record(AuditLog.Action.REPORT_PEOPLE_VIEWED, request=request, user=request.user, object_type="Report", meta=_filters_for_audit(form.cleaned_data))
        max_created = max([r[1] for r in data.timeline] + [r[2] for r in data.timeline] + [1])
        chart = [{"label": l, "created": c, "completed": d, "cw": round(100 * c / max_created), "dw": round(100 * d / max_created)} for l, c, d in data.timeline]
        ctx.update(data=data, kpis=data.kpis, chart=chart, tables={t.key: t for t in data.tables})
        return render(request, "portal/reports/index.html", ctx)


class ReportExportView(PortalPermissionMixin, View):
    """Same filters, same build_report(), same permission checks as the page; plus reports.export_reports."""

    permission_required = ["reports.view_reports", "reports.export_reports"]
    http_method_names = ["get"]
    FORMATS = {
        "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", exports.to_xlsx, AuditLog.Action.REPORT_EXPORTED),
        "pdf": ("application/pdf", exports.to_pdf, AuditLog.Action.REPORT_EXPORTED),
    }

    def get(self, request, fmt):
        if fmt not in self.FORMATS:
            return HttpResponse(status=404)
        form = FilterForm(request.GET, user=request.user)
        if not form.is_valid():
            messages.error(request, gettext("Filtrlar noto‘g‘ri: %(errors)s") % {"errors": "; ".join(e for errs in form.errors.values() for e in errs)})
            return redirect(f"{request.path.rsplit('export/', 1)[0]}?{request.GET.urlencode()}")
        try:
            data = build_report(request.user, form.cleaned_data)
        except PermissionError:
            raise PermissionDenied from None
        ctype, writer, action = self.FORMATS[fmt]
        content = writer(data, request.user)
        record(action, request=request, user=request.user, object_type="Report", meta={
            "format": fmt, "filters": _filters_for_audit(form.cleaned_data), "sections": sorted(data.sections),
            "rows": {t.key: len(t.rows) for t in data.tables}, "bytes": len(content),
        })
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="hisobot-{stamp}.{fmt}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
