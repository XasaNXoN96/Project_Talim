from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.access.models import RoleAssignment

from .models import User


class RoleAssignmentInline(admin.TabularInline):
    model = RoleAssignment
    extra = 0
    autocomplete_fields = ()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (("Qo‘shimcha", {"fields": ("locale", "must_change_password")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + ((None, {"fields": ("email",)}),)
    inlines = [RoleAssignmentInline]
