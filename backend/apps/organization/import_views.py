"""Employee import: upload -> preview -> confirm -> report. Needs organization.add_employee; every record belongs to its uploader."""
import datetime
import hashlib

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin
from apps.documents import files
from apps.documents.validation import UploadRejected

from . import access, importer
from .models import Employee, EmployeeImport


def _ttl():
    return datetime.timedelta(minutes=settings.EMPLOYEE_IMPORT_TTL_MINUTES)


def wipe_expired(now=None):
    """Empty the rows (personal data) of previews nobody confirmed in time. Returns how many were wiped."""
    cutoff = (now or timezone.now()) - _ttl()
    qs = EmployeeImport.objects.filter(status=EmployeeImport.Status.PREVIEWED, created_at__lt=cutoff)
    return qs.update(status=EmployeeImport.Status.EXPIRED, rows=[])


def _audit(action, request, imp=None, **meta):
    record(action, request=request, user=request.user, object_type="EmployeeImport", object_id=imp.pk if imp else "", meta=meta)


def _is_open(imp):
    return imp.status == EmployeeImport.Status.PREVIEWED and imp.created_at >= timezone.now() - _ttl()


class _Base(PortalPermissionMixin, View):
    permission_required = "organization.add_employee"

    def has_permission(self):
        # the import writes into any department: not for someone confined to one institution (a school director)
        return super().has_permission() and access.directory_institution_limit(self.request.user) is None

    def get_import(self, request, pk):
        return get_object_or_404(EmployeeImport, pk=pk, user=request.user)  # someone else's import -> 404


class ImportUploadView(_Base):
    def get(self, request):
        return render(request, "portal/employees/import_upload.html", self.context())

    def context(self, **extra):
        return {"max_mb": settings.EMPLOYEE_IMPORT_MAX_BYTES // (1024 * 1024), "max_rows": settings.EMPLOYEE_IMPORT_MAX_ROWS, "columns": importer.COLUMNS, "required": importer.REQUIRED, **extra}

    def post(self, request):
        wipe_expired()
        upload = request.FILES.get("file")
        if upload is None:
            return render(request, "portal/employees/import_upload.html", self.context(error=gettext("Fayl tanlanmagan.")))
        try:
            if upload.size > settings.EMPLOYEE_IMPORT_MAX_BYTES:
                raise importer.ImportFileError("too_big", mb=settings.EMPLOYEE_IMPORT_MAX_BYTES // (1024 * 1024))
            if not upload.name.lower().endswith(".xlsx"):
                raise importer.ImportFileError("not_xlsx")
            # the shared gate: extension vs content, macros/active content, zip bombs, antivirus (fail-closed)
            checked = files.check_or_audit(upload, request=request, user=request.user, object_type="EmployeeImport")
            if checked.extension != "xlsx":
                raise importer.ImportFileError("not_xlsx")
            parsed = importer.read_rows(checked.data)
        except UploadRejected as exc:
            _audit(AuditLog.Action.EMPLOYEE_IMPORT_REJECTED, request, reason=exc.code)
            return render(request, "portal/employees/import_upload.html", self.context(error=str(exc)))
        except importer.ImportFileError as exc:
            _audit(AuditLog.Action.EMPLOYEE_IMPORT_REJECTED, request, reason=exc.code)
            return render(request, "portal/employees/import_upload.html", self.context(error=exc.message))
        results = importer.evaluate(parsed)
        imp = EmployeeImport.objects.create(
            user=request.user, file_sha256=hashlib.sha256(checked.data).hexdigest(),
            rows=[{"n": n, "raw": {k: _jsonable(v) for k, v in raw.items()}} for n, raw in parsed],
        )
        _audit(AuditLog.Action.EMPLOYEE_IMPORT_PREVIEWED, request, imp, **importer.tally(results), sha256=imp.file_sha256[:16])
        return redirect("employees:import_detail", pk=imp.pk)


def _jsonable(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def _parsed(imp):
    return [(r["n"], r["raw"]) for r in imp.rows]


class ImportDetailView(_Base):
    """Preview while open, report afterwards."""

    def get(self, request, pk):
        imp = self.get_import(request, pk)
        if imp.status == EmployeeImport.Status.PREVIEWED and not _is_open(imp):
            return render(request, "portal/employees/import_report.html", {"imp": imp, "expired": True})
        if imp.status != EmployeeImport.Status.PREVIEWED:
            errors = [{"n": e["n"], "messages": [importer.message(c) for c in e["codes"]]} for e in imp.summary.get("errors", [])]
            return render(request, "portal/employees/import_report.html", {"imp": imp, "errors": errors})
        results = importer.evaluate(_parsed(imp))
        only_problems = request.GET.get("only") == "problems"
        shown = [r for r in results if r["state"] != "ok"] if only_problems else results
        rows = [{**r, "messages": importer.render_errors(r["errors"]), "department": r["cleaned"]["department"], "position": r["cleaned"]["position"]} for r in shown]
        return render(request, "portal/employees/import_preview.html", {
            "imp": imp, "rows": rows, "tally": importer.tally(results), "only_problems": only_problems,
            "minutes": settings.EMPLOYEE_IMPORT_TTL_MINUTES,
        })


class ImportConfirmView(_Base):
    http_method_names = ["post"]

    def post(self, request, pk):
        include_dupes = request.POST.get("include_duplicates") == "1"
        try:
            with transaction.atomic():
                imp = get_object_or_404(EmployeeImport.objects.select_for_update(), pk=pk, user=request.user)
                if not _is_open(imp):
                    messages.error(request, _("Bu import allaqachon bajarilgan, bekor qilingan yoki muddati o‘tgan."))
                    return redirect("employees:import_detail", pk=imp.pk)
                results = importer.evaluate(_parsed(imp))  # again, against the database as it is now
                todo = [r for r in results if r["state"] == "ok" or (include_dupes and r["state"] == "duplicate")]
                created = []
                for r in todo:
                    c = r["cleaned"]
                    created.append(Employee(
                        last_name=c["last_name"], first_name=c["first_name"], middle_name=c["middle_name"], department_id=r["department_id"],
                        position_id=r["position_id"], status=r["status"], work_phone=c["work_phone"], work_email=c["work_email"],
                        hired_at=c["hired_at"] or None, personal_phone=c["personal_phone"], birth_date=c["birth_date"] or None,
                    ))
                Employee.objects.bulk_create(created)
                for e in created:
                    record(AuditLog.Action.EMPLOYEE_CREATED, request=request, user=request.user, object_type="Employee", object_id=e.pk, meta={"via": "import", "import": str(imp.pk)})
                imp.summary = {
                    "added": len(created), "total": len(results),
                    "duplicates_skipped": [r["n"] for r in results if r["state"] == "duplicate" and not include_dupes],
                    "duplicates_imported": [r["n"] for r in results if r["state"] == "duplicate" and include_dupes],
                    "errors": [{"n": r["n"], "codes": [code for code, _p in r["errors"]]} for r in results if r["state"] == "error"],
                }
                imp.status, imp.rows, imp.completed_at = EmployeeImport.Status.COMPLETED, [], timezone.now()
                imp.save()
                _audit(AuditLog.Action.EMPLOYEE_IMPORT_COMPLETED, request, imp, added=len(created), skipped=len(results) - len(created), errors=len(imp.summary["errors"]),
                       duplicates_imported=len(imp.summary["duplicates_imported"]))
        except Http404:
            raise
        except Exception:
            # nothing was saved (the whole block is one transaction); the preview stays so the user can retry or cancel
            _audit(AuditLog.Action.EMPLOYEE_IMPORT_FAILED, request, EmployeeImport.objects.filter(pk=pk, user=request.user).first())
            messages.error(request, _("Import xatolik bilan to‘xtadi. Hech narsa saqlanmadi; qayta urinib ko‘ring."))
            return redirect("employees:import_detail", pk=pk)
        messages.success(request, _("Import bajarildi."))
        return redirect("employees:import_detail", pk=imp.pk)


class ImportCancelView(_Base):
    http_method_names = ["post"]

    def post(self, request, pk):
        with transaction.atomic():
            imp = get_object_or_404(EmployeeImport.objects.select_for_update(), pk=pk, user=request.user)
            if imp.status == EmployeeImport.Status.PREVIEWED:
                imp.status, imp.rows = EmployeeImport.Status.CANCELLED, []
                imp.save(update_fields=["status", "rows"])
                _audit(AuditLog.Action.EMPLOYEE_IMPORT_CANCELLED, request, imp)
                messages.info(request, _("Import bekor qilindi. Yuklangan ma’lumotlar o‘chirildi."))
        return redirect("employees:import")


class ImportTemplateView(_Base):
    def get(self, request):
        response = HttpResponse(importer.build_template(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="xodimlar-import-namuna.xlsx"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
