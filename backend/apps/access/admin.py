from django.contrib import admin

from apps.audit.admin_mixins import ReadOnlyAdmin

from .models import RoleAssignment


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(ReadOnlyAdmin, admin.ModelAdmin):
    """View only. Assigning and revoking roles happens in the portal (users:role_add / users:role_remove), which enforces who may hand out
    privileged roles, the scope rules and the last-administrator rule, and writes the audit entry."""

    list_display = ("user", "role", "scope", "department")
    list_filter = ("role", "scope")
