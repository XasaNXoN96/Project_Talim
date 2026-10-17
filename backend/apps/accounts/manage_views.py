"""User and role administration screens. Rules live in services.py; these views only check permissions and show results."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from apps.access.models import RoleAssignment
from apps.access.roles import PRIVILEGED_ROLES, ROLE_HINTS, RoleCode
from apps.access.services import has_role
from apps.core.mixins import PortalPermissionMixin

from . import services
from .manage_forms import RoleAssignForm, UserCreateForm, UserEditForm
from .twofactor import has_confirmed_device, requires_two_factor

User = get_user_model()


def _allowed_roles(actor):
    if has_role(actor, RoleCode.ADMIN) or actor.is_superuser:
        return [c for c, label in RoleCode.choices]
    return [c for c, label in RoleCode.choices if c not in PRIVILEGED_ROLES]


def _is_admin(actor):
    return actor.is_superuser or has_role(actor, RoleCode.ADMIN)


class UserListView(PortalPermissionMixin, ListView):
    template_name = "portal/users/list.html"
    permission_required = "accounts.view_user"
    paginate_by = 30
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.prefetch_related("role_assignments__role").order_by("last_name", "first_name", "username")
        q = (self.request.GET.get("q") or "").strip()[:100]
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        status = self.request.GET.get("status")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        role = self.request.GET.get("role")
        if role in RoleCode.values:
            qs = qs.filter(role_assignments__role__name=role).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(q=self.request.GET.get("q", ""), status=self.request.GET.get("status", ""), role=self.request.GET.get("role", ""), roles=RoleCode.choices)
        return ctx


class UserCreateView(PortalPermissionMixin, View):
    permission_required = "accounts.manage_users"

    def get(self, request):
        return render(request, "portal/users/form.html", {"form": UserCreateForm(allowed_roles=_allowed_roles(request.user)), "creating": True})

    def post(self, request):
        form = UserCreateForm(request.POST, allowed_roles=_allowed_roles(request.user))
        if form.is_valid():
            try:
                user = services.create_user(request.user, request=request, **form.cleaned_data)
            except services.ActionNotAllowed as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, _("Foydalanuvchi yaratildi. Endi unga taklifnoma yuboring."))
                return redirect("users:detail", pk=user.pk)
        return render(request, "portal/users/form.html", {"form": form, "creating": True})


class UserDetailView(PortalPermissionMixin, View):
    permission_required = "accounts.view_user"

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        actor = request.user
        ctx = {
            "target": target,
            "assignments": target.role_assignments.select_related("role", "department"),
            "has_2fa": has_confirmed_device(target),
            "twofa_required": requires_two_factor(target),
            "locked": services.is_account_locked(target),
            "can_manage": actor.has_perm("accounts.manage_users"),
            "can_assign": actor.has_perm("accounts.assign_roles"),
            "can_unlock": actor.has_perm("accounts.unlock_accounts"),
            "assign_form": RoleAssignForm(allowed_roles=_allowed_roles(actor)),
            "role_hints": [(RoleCode(c).label, ROLE_HINTS[c]) for c in _allowed_roles(actor) if c in ROLE_HINTS],
            "is_self": target.pk == actor.pk,
        }
        return render(request, "portal/users/detail.html", ctx)


class UserEditView(PortalPermissionMixin, View):
    permission_required = "accounts.manage_users"

    def _target(self, pk):
        return get_object_or_404(User, pk=pk)

    def get(self, request, pk):
        t = self._target(pk)
        form = UserEditForm(initial={"email": t.email, "first_name": t.first_name, "last_name": t.last_name, "locale": t.locale}, user=t)
        return render(request, "portal/users/form.html", {"form": form, "target": t})

    def post(self, request, pk):
        t = self._target(pk)
        form = UserEditForm(request.POST, user=t)
        if form.is_valid():
            try:
                services.update_user(request.user, t, request=request, **form.cleaned_data)
            except services.ActionNotAllowed as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, _("Ma’lumotlar saqlandi."))
                return redirect("users:detail", pk=t.pk)
        return render(request, "portal/users/form.html", {"form": form, "target": t})


class UserActionView(PortalPermissionMixin, View):
    """POST-only state changes. Each action names the permission it needs; the rules are enforced in services."""

    http_method_names = ["post"]
    permission_required = "accounts.view_user"
    ACTIONS = {
        "deactivate": ("accounts.manage_users", services.deactivate_user, _("Foydalanuvchi o‘chirildi (faolsizlantirildi).")),
        "reactivate": ("accounts.manage_users", services.reactivate_user, _("Foydalanuvchi qayta faollashtirildi.")),
        "unlock": ("accounts.unlock_accounts", services.unlock_account, _("Hisob blokdan chiqarildi.")),
        "force_password": ("accounts.manage_users", services.force_password_change, _("Keyingi kirishda parolni almashtirish talab qilinadi.")),
        "invite": ("accounts.manage_users", services.send_invitation, _("Taklifnoma yuborildi.")),
    }

    def post(self, request, pk, action):
        if action not in self.ACTIONS:
            raise Http404
        perm, func, ok_message = self.ACTIONS[action]
        if not request.user.has_perm(perm):
            raise PermissionDenied
        target = get_object_or_404(User, pk=pk)
        try:
            func(request.user, target, request)
        except services.ActionNotAllowed as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, ok_message)
        return redirect("users:detail", pk=target.pk)


class RoleAssignView(PortalPermissionMixin, View):
    http_method_names = ["post"]
    permission_required = "accounts.assign_roles"

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = RoleAssignForm(request.POST, allowed_roles=_allowed_roles(request.user))
        if not form.is_valid():
            messages.error(request, _("Rol yoki bo‘lim noto‘g‘ri tanlangan."))
        else:
            try:
                services.assign_role(request.user, target, request=request, **form.cleaned_data)
            except services.ActionNotAllowed as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, _("Rol biriktirildi."))
        return redirect("users:detail", pk=target.pk)


class RoleRevokeView(PortalPermissionMixin, View):
    http_method_names = ["post"]
    permission_required = "accounts.assign_roles"

    def post(self, request, pk, assignment_id):
        assignment = get_object_or_404(RoleAssignment.objects.select_related("role", "user"), pk=assignment_id, user_id=pk)
        target_pk = assignment.user_id
        try:
            services.revoke_role(request.user, assignment, request)
        except services.ActionNotAllowed as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Rol olib tashlandi."))
        return redirect("users:detail", pk=target_pk)
