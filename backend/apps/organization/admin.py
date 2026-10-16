from django.contrib import admin

from .models import Department, Employee, Institution, Position


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active")
    search_fields = ("name",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "department", "position", "status")
    list_filter = ("status", "department")
    search_fields = ("last_name", "first_name")


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_published")
    list_filter = ("kind", "is_published")
    search_fields = ("name",)
