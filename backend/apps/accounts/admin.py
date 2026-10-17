from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.defaults import permission_denied
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.access.models import RoleAssignment
from apps.access.roles import RoleCode
from apps.audit.admin_mixins import AdminAuditMixin, NoCreate, NoDelete

from apps.audit.models import AuditLog
from apps.audit.services import record

from .models import User


class RoleAssignmentInline(admin.TabularInline):
    """Read-only here: roles are assigned in the portal, where the rules (who may hand out privileged roles, scope, last administrator) are enforced."""

    model = RoleAssignment
    extra = 0
    autocomplete_fields = ()
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
class UserAdmin(AdminAuditMixin, NoCreate, NoDelete, DjangoUserAdmin):
    """Policy (superusers only): no add and no delete here (the portal creates, invites and deactivates people, with its checks and audit);
    no password setting here (it would skip the force-change, lockout and session rules): use the portal's invitation / forced change;
    roles (groups) are read-only here and assigned in the portal. Allowed, with an audit entry: name, e-mail, locale, active flag, the staff and
    superuser flags, and personal permissions (the way to grant an exception such as content.approve_own_news to one person)."""

    audited_m2m = ("user_permissions",)
    readonly_fields = ("groups", "last_login", "date_joined")
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + ((_("Qo‘shimcha"), {"fields": ("locale", "must_change_password")}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + ((None, {"fields": ("email",)}),)
    inlines = [RoleAssignmentInline]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        return _translate_permission_labels(field) if db_field.name == "user_permissions" else field

    def user_change_password(self, request, id, form_url=""):
        record(AuditLog.Action.ADMIN_BLOCKED, request=request, user=request.user, object_type="User", object_id=id, meta={"via": "django_admin", "what": "set_password"})
        # a RETURNED 403 (not a raised one): requests run in a transaction and a raised exception would roll the audit entry back
        return permission_denied(request, PermissionDenied())  # passwords are set by the person (invitation / reset) or forced to change in the portal


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(AdminAuditMixin, DjangoGroupAdmin):
    """The six role groups are defined in code (apps.access.roles) and changed only there + `seed_roles`: name and permissions are read-only here and they
    cannot be deleted. Other groups are editable with an audit entry listing the permissions added and removed."""

    audited_m2m = ("permissions",)

    def get_readonly_fields(self, request, obj=None):
        base = tuple(super().get_readonly_fields(request, obj))
        return base + ("name", "permissions") if obj is not None and obj.name in RoleCode.values else base

    def has_delete_permission(self, request, obj=None):
        return not (obj is not None and obj.name in RoleCode.values) and super().has_delete_permission(request, obj)

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
