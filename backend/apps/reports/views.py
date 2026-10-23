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

from django.db.models import Count

from . import exports, schools
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
        ctx = {"form": form, "query": request.GET.urlencode(), "can_export": request.user.has_perm("reports.export_reports"), "error": None,
               "can_schools": schools.can_see_schools(request.user)}
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


# ---- statistics by school --------------------------------------------------------------------------------------------

class _SchoolsBase(PortalPermissionMixin, View):
    """Whole-organisation reporting right only (see schools.can_see_schools); anything narrower gets 403."""

    permission_required = "reports.view_reports"

    def has_permission(self):
        return schools.can_see_schools(self.request.user)


class SchoolsReportView(_SchoolsBase):
    def get(self, request):
        rows = schools.build_rows()
        return render(request, "portal/reports/schools.html", {"rows": rows, "total": schools.totals(rows), "can_export": request.user.has_perm("reports.export_reports")})


class SchoolDetailView(_SchoolsBase):
    def get(self, request, pk):
        from django.shortcuts import get_object_or_404

        from apps.achievements import workflow as ach_workflow
        from apps.achievements.models import Achievement
        from apps.organization.models import Employee, Institution

        inst = get_object_or_404(Institution, pk=pk)
        row = next(r for r in schools.build_rows() if r.institution.pk == inst.pk)
        tasks = [t for _i, t in schools.school_tasks([inst.pk])]
        visible = set(ach_workflow.visible_achievements(request.user).filter(institution=inst).values_list("pk", flat=True))
        achievements = list(Achievement.objects.filter(institution=inst).order_by("-created_at")[:50])
        for a in achievements:
            a.openable = a.pk in visible
        positions = list(Employee.objects.filter(institution=inst).exclude(status=Employee.Status.ARCHIVED).values_list("position__name").annotate(n=Count("pk")).order_by("-n"))
        return render(request, "portal/reports/school_detail.html", {"inst": inst, "row": row, "tasks": tasks, "achievements": achievements, "positions": positions})


class SchoolsExportView(PortalPermissionMixin, View):
    """The school statistics as an Excel or PDF file: the same rows and the same (organisation-wide) right as the page, plus reports.export_reports."""

    permission_required = ["reports.view_reports", "reports.export_reports"]
    http_method_names = ["get"]
    fmt = "xlsx"
    FORMATS = {
        "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", exports.schools_to_xlsx),
        "pdf": ("application/pdf", exports.schools_to_pdf),
    }

    def has_permission(self):
        return super().has_permission() and schools.can_see_schools(self.request.user)

    def get(self, request):
        ctype, writer = self.FORMATS[self.fmt]
        rows = schools.build_rows()
        content = writer(rows, schools.totals(rows), request.user)
        record(AuditLog.Action.REPORT_EXPORTED, request=request, user=request.user, object_type="Report",
               meta={"format": self.fmt, "kind": "schools", "rows": len(rows), "bytes": len(content)})
        response = HttpResponse(content, content_type=ctype)
        response["Content-Disposition"] = f'attachment; filename="maktablar-{timezone.localtime():%Y%m%d-%H%M}.{self.fmt}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
