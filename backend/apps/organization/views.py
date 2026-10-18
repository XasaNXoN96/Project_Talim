import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.mixins import PortalPermissionMixin

from . import access
from .forms import DepartmentForm, EmployeeForm, InstitutionForm, PositionForm
from .models import Department, Employee, Institution, Position


class EmployeeListView(PortalPermissionMixin, ListView):
    """Directory only: name, department, position, status. Contacts and private data live on the card."""

    permission_required = "organization.view_employee_directory"
    template_name = "portal/employees/list.html"
    paginate_by = 30
    context_object_name = "employees"

    def get_queryset(self):
        qs = access.directory_queryset(self.request.user)
        q = (self.request.GET.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(middle_name__icontains=q) | Q(position__name__icontains=q))
        dept = self.request.GET.get("department")
        if dept:
            try:
                qs = qs.filter(department_id__in=access.descendant_ids(uuid.UUID(dept)))
            except ValueError:
                qs = qs.none()
        inst = self.request.GET.get("institution")
        if inst:
            try:
                qs = qs.filter(institution_id=uuid.UUID(inst))
            except ValueError:
                qs = qs.none()
        status = self.request.GET.get("status")
        if status in Employee.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            q=self.request.GET.get("q", ""), department=self.request.GET.get("department", ""), status=self.request.GET.get("status", ""),
            departments=Department.objects.filter(is_active=True), statuses=Employee.Status.choices,
            institution=self.request.GET.get("institution", ""), institutions=Institution.objects.all(),
            can_add=self.request.user.has_perm("organization.add_employee"),
        )
        return ctx


class EmployeeDetailView(PortalPermissionMixin, View):
    permission_required = "organization.view_employee_directory"

    def get(self, request, pk):
        employee = get_object_or_404(Employee.objects.select_related("department", "position", "user", "institution"), pk=pk)
        tiers = access.visible_tiers(request.user, employee)
        if "directory" not in tiers or (employee.status == Employee.Status.ARCHIVED and not request.user.has_perm("organization.change_employee")):
            raise PermissionDenied
        own = employee.user_id == request.user.pk
        sensitive = tiers & {"contacts", "private"}
        if sensitive and not own:
            record(
                AuditLog.Action.EMPLOYEE_VIEWED, request=request, user=request.user, object_type="Employee", object_id=employee.pk,
                meta={"tiers": sorted(sensitive)},
            )
        return render(request, "portal/employees/detail.html", {
            "e": employee, "tiers": tiers, "own": own,
            "can_edit": request.user.has_perm("organization.change_employee"),
        })


class EmployeePhotoView(PortalPermissionMixin, View):
    """The photo is shown to exactly the people who see this person in the directory list (same queryset); nobody else, no public URL."""

    permission_required = "organization.view_employee_directory"

    def get(self, request, pk):
        employee = access.directory_queryset(request.user).filter(pk=pk).first()
        if employee is None or not employee.photo:
            raise Http404
        try:
            handle = employee.photo.storage.open(employee.photo.name, "rb")
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise Http404 from exc
        response = FileResponse(handle, content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-cache"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class EmployeeMeView(PortalPermissionMixin, View):
    permission_required = "organization.view_employee_directory"

    def get(self, request):
        employee = Employee.objects.filter(user=request.user).first()
        if employee is None:
            messages.info(request, _("Sizning hisobingizga xodim kartasi biriktirilmagan."))
            return redirect("employees:list")
        return redirect("employees:detail", pk=employee.pk)


def _changed(form):
    return sorted(f for f in form.changed_data if f not in ("photo_upload", "photo_clear")) + (
        ["photo"] if form.cleaned_data.get("photo_upload") or form.cleaned_data.get("photo_clear") else []
    )


class EmployeeCreateView(PortalPermissionMixin, View):
    permission_required = "organization.add_employee"

    def _form(self, request, data=None, files=None):
        return EmployeeForm(data, files, can_link_user=request.user.has_perm("accounts.manage_users"), request=request)

    def get(self, request):
        return render(request, "portal/employees/form.html", {"form": self._form(request), "creating": True})

    def post(self, request):
        form = self._form(request, request.POST, request.FILES)
        if form.is_valid():
            employee = form.save()
            record(
                AuditLog.Action.EMPLOYEE_CREATED, request=request, user=request.user, object_type="Employee", object_id=employee.pk,
                meta={"fields": _changed(form)},
            )
            messages.success(request, _("Xodim qo‘shildi."))
            return redirect("employees:detail", pk=employee.pk)
        return render(request, "portal/employees/form.html", {"form": form, "creating": True})


class EmployeeEditView(PortalPermissionMixin, View):
    permission_required = "organization.change_employee"

    def _form(self, request, employee, data=None, files=None):
        return EmployeeForm(data, files, instance=employee, can_link_user=request.user.has_perm("accounts.manage_users"), request=request)

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        return render(request, "portal/employees/form.html", {"form": self._form(request, employee), "e": employee})

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        form = self._form(request, employee, request.POST, request.FILES)
        if form.is_valid():
            changed = _changed(form)
            form.save()
            if changed:
                record(
                    AuditLog.Action.EMPLOYEE_UPDATED, request=request, user=request.user, object_type="Employee", object_id=employee.pk,
                    meta={"fields": changed},
                )
            messages.success(request, _("Ma’lumotlar saqlandi."))
            return redirect("employees:detail", pk=employee.pk)
        return render(request, "portal/employees/form.html", {"form": form, "e": employee})


class EmployeeArchiveView(PortalPermissionMixin, View):
    http_method_names = ["post"]
    permission_required = "organization.change_employee"
    restore = False

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        if self.restore:
            employee.status = Employee.Status.ACTIVE
            action, text = AuditLog.Action.EMPLOYEE_RESTORED, _("Xodim arxivdan qaytarildi.")
        else:
            employee.status = Employee.Status.ARCHIVED
            action, text = AuditLog.Action.EMPLOYEE_ARCHIVED, _("Xodim arxivlandi.")
        employee.save(update_fields=["status", "updated_at"])
        record(action, request=request, user=request.user, object_type="Employee", object_id=employee.pk)
        messages.success(request, text)
        return redirect("employees:detail", pk=employee.pk)


# ---- organisation structure -------------------------------------------------------------------------------------

def _tree(departments):
    by_parent = {}
    for d in departments:
        by_parent.setdefault(d.parent_id, []).append(d)
    rows = []

    def walk(parent_id, depth):
        for d in by_parent.get(parent_id, []):
            rows.append({"d": d, "depth": depth, "indent": depth * 20})
            walk(d.pk, depth + 1)

    walk(None, 0)
    return rows


class StructureView(PortalPermissionMixin, View):
    permission_required = "organization.view_department"

    def get(self, request):
        departments = list(
            Department.objects.annotate(n=Count("employees", filter=~Q(employees__status=Employee.Status.ARCHIVED))).select_related("parent")
        )
        return render(request, "portal/structure/index.html", {
            "rows": _tree(departments),
            "positions": Position.objects.annotate(n=Count("employees")),
            "institutions": Institution.objects.annotate(n=Count("employees", filter=~Q(employees__status=Employee.Status.ARCHIVED))),
            "can_edit": request.user.has_perm("organization.change_department"),
            "can_edit_institutions": request.user.has_perm("organization.change_institution"),
            "can_add_institution": request.user.has_perm("organization.add_institution"),
        })


class _OrgFormView(PortalPermissionMixin, View):
    form_class = None
    model = None
    template_name = "portal/structure/form.html"
    title = ""

    def get_object(self, pk):
        return get_object_or_404(self.model, pk=pk) if pk else None

    def get(self, request, pk=None):
        obj = self.get_object(pk)
        return render(request, self.template_name, {"form": self.form_class(instance=obj), "title": self.title, "obj": obj})

    def post(self, request, pk=None):
        obj = self.get_object(pk)
        form = self.form_class(request.POST, instance=obj)
        if form.is_valid():
            changed = sorted(form.changed_data)
            saved = form.save()
            record(
                AuditLog.Action.ORG_CHANGED, request=request, user=request.user, object_type=self.model.__name__, object_id=saved.pk,
                meta={"created": obj is None, "fields": changed},
            )
            messages.success(request, _("Saqlandi."))
            return redirect("employees:structure")
        return render(request, self.template_name, {"form": form, "title": self.title, "obj": obj})


class DepartmentFormView(_OrgFormView):
    form_class = DepartmentForm
    model = Department
    title = _("Bo‘lim")

    @property
    def permission_required(self):
        return "organization.change_department" if self.kwargs.get("pk") else "organization.add_department"


class PositionFormView(_OrgFormView):
    form_class = PositionForm
    model = Position
    title = _("Lavozim")

    @property
    def permission_required(self):
        return "organization.change_position" if self.kwargs.get("pk") else "organization.add_position"


class InstitutionFormView(_OrgFormView):
    form_class = InstitutionForm
    model = Institution
    title = _("Ta’lim muassasasi")

    @property
    def permission_required(self):
        return "organization.change_institution" if self.kwargs.get("pk") else "organization.add_institution"
