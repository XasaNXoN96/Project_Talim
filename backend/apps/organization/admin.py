from django.contrib import admin

from apps.audit.admin_mixins import AdminAuditMixin, NoDelete

from .models import Department, Employee, Institution, Position


@admin.register(Department)
class DepartmentAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ("name", "parent", "is_active")
    search_fields = ("name",)


@admin.register(Position)
class PositionAdmin(AdminAuditMixin, admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(AdminAuditMixin, NoDelete, admin.ModelAdmin):
    """Edits are audited (field names only, never values: the card holds personal data). No delete: employees are archived in the portal."""

    list_display = ("last_name", "first_name", "department", "position", "status")
    list_filter = ("status", "department")
    search_fields = ("last_name", "first_name")


@admin.register(Institution)
class InstitutionAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ("name", "kind", "is_published")
    list_filter = ("kind", "is_published")
    search_fields = ("name",)
