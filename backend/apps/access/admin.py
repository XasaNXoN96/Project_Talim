from django.contrib import admin

from .models import RoleAssignment


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "scope", "department")
    list_filter = ("role", "scope")
