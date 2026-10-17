from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.access.models import RoleAssignment

from .models import User


class RoleAssignmentInline(admin.TabularInline):
    model = RoleAssignment
    extra = 0
    autocomplete_fields = ()


PERMISSION_ACTIONS = {
    "add": _("Qo‘shish: %(model)s"), "change": _("O‘zgartirish: %(model)s"),
    "delete": _("O‘chirish: %(model)s"), "view": _("Ko‘rish: %(model)s"),
}


def permission_label(permission):
    """Permission names are stored in the database (in English for Django's four standard ones, with the Uzbek model name
    inside; in Uzbek for ours). Show them in the active language: standard ones are rebuilt from a translatable template
    and the translated model name, custom ones go through the catalogs."""
    ct = permission.content_type
    model = ct.model_class()
    action, _sep, rest = permission.codename.partition("_")
    if model is not None and action in PERMISSION_ACTIONS and rest == model._meta.model_name:
        return f"{ct} | " + str(PERMISSION_ACTIONS[action]) % {"model": model._meta.verbose_name}
    return f"{ct} | {gettext(permission.name)}"


def _translate_permission_labels(formfield):
    if formfield is not None:
        formfield.label_from_instance = permission_label
    return formfield


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + ((_("Qo‘shimcha"), {"fields": ("locale", "must_change_password")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + ((None, {"fields": ("email",)}),)
    inlines = [RoleAssignmentInline]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        return _translate_permission_labels(field) if db_field.name == "user_permissions" else field


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        return _translate_permission_labels(field) if db_field.name == "permissions" else field


def _admin_login_redirect(request, extra_context=None):
    """The stock admin login would authenticate with a password alone: no lockout, no second factor.
    Every sign-in goes through apps.accounts LoginView instead (which then validates the `next` target)."""
    if request.user.is_authenticated:
        # Already signed in but not allowed into the admin (no is_staff): answer 403. Redirecting to the sign-in page
        # would bounce the user back here forever.
        raise PermissionDenied
    target = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('accounts:login')}?{urlencode({'next': target})}")


admin.site.login = _admin_login_redirect
