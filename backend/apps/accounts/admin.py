from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
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


def _admin_login_redirect(request, extra_context=None):
    """The stock admin login would authenticate with a password alone: no lockout, no second factor.
    Every sign-in goes through apps.accounts LoginView instead (which then validates the `next` target)."""
    target = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}")


admin.site.login = _admin_login_redirect
