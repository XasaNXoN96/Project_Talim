"""User administration rules. Views call these; the rules live here so they cannot be bypassed by a different view.

Every function raises ActionNotAllowed with a message fit to show the operator, and writes an audit entry that names
the ACTOR and the target (ids, never passwords or tokens).
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext, override
from django.utils.translation import gettext_lazy as _

from apps.access.models import RoleAssignment
from apps.access.roles import PRIVILEGED_ROLES, ROLE_SCOPE, RoleCode
from apps.access.services import has_role
from apps.audit.models import AuditLog
from apps.audit.services import record

from . import throttle
from .notifications import notify_security_event
from .sessions import invalidate_user_sessions

from apps.core.locale import user_language

logger = logging.getLogger(__name__)
User = get_user_model()


class ActionNotAllowed(Exception):
    """The operation would break a safety rule. The message is shown to the operator."""


def _meta(target, **extra):
    return {"target_id": str(target.pk), "target": target.get_username(), **extra}


def _guard_target(actor, target):
    if target.is_superuser and not actor.is_superuser:
        raise ActionNotAllowed(_("Superuser hisoblarini bu sahifadan o‘zgartirib bo‘lmaydi."))


def active_admin_count(excluding=None):
    qs = User.objects.filter(is_active=True, role_assignments__role__name=RoleCode.ADMIN).distinct()
    if excluding is not None:
        qs = qs.exclude(pk=excluding.pk)
    return qs.count()


def _holds_admin(user):
    return user.role_assignments.filter(role__name=RoleCode.ADMIN).exists()


def create_user(actor, *, username, email, first_name, last_name, role, department, request):
    if role in PRIVILEGED_ROLES and not has_role(actor, RoleCode.ADMIN):
        raise ActionNotAllowed(_("Bu rolni faqat administrator bera oladi."))
    with transaction.atomic():
        user = User(username=username, email=email, first_name=first_name, last_name=last_name, is_active=True)
        user.set_unusable_password()  # the person sets their own password through the invitation link
        user.save()
        _assign(actor, user, role, department, request)
        record(AuditLog.Action.USER_CREATED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user, role=role))
    return user


def update_user(actor, user, *, email, first_name, last_name, locale, request):
    _guard_target(actor, user)
    changed = [f for f, v in (("email", email), ("first_name", first_name), ("last_name", last_name), ("locale", locale)) if getattr(user, f) != v]
    user.email, user.first_name, user.last_name, user.locale = email, first_name, last_name, locale
    user.save()
    record(AuditLog.Action.USER_UPDATED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user, fields=changed))


def _assign(actor, user, role_name, department, request):
    if role_name not in RoleCode.values:
        raise ActionNotAllowed(_("Noma’lum rol."))
    scope = ROLE_SCOPE[role_name]
    if scope == "department" and department is None:
        raise ActionNotAllowed(_("Bo‘lim boshlig‘i roli uchun bo‘lim ko‘rsatilishi shart."))
    if scope != "department":
        department = None
    assignment = RoleAssignment(user=user, role=Group.objects.get(name=role_name), scope=scope, department=department)
    assignment._audit_actor, assignment._audit_request = actor, request
    assignment.save()
    return assignment


def assign_role(actor, user, *, role, department, request):
    _guard_target(actor, user)
    if role in PRIVILEGED_ROLES and not has_role(actor, RoleCode.ADMIN):
        raise ActionNotAllowed(_("Bu rolni faqat administrator bera oladi."))
    if RoleAssignment.objects.filter(user=user, role__name=role, department=department if ROLE_SCOPE.get(role) == "department" else None).exists():
        raise ActionNotAllowed(_("Bu rol allaqachon biriktirilgan."))
    return _assign(actor, user, role, department, request)


def revoke_role(actor, assignment, request):
    user = assignment.user
    _guard_target(actor, user)
    if assignment.role.name in PRIVILEGED_ROLES and not has_role(actor, RoleCode.ADMIN):
        raise ActionNotAllowed(_("Bu rolni faqat administrator olib tashlay oladi."))
    if assignment.role.name == RoleCode.ADMIN:
        if user.pk == actor.pk:
            raise ActionNotAllowed(_("O‘zingizning administrator rolingizni olib tashlab bo‘lmaydi."))
        if user.is_active and active_admin_count(excluding=user) == 0:
            raise ActionNotAllowed(_("Oxirgi administratorning rolini olib tashlab bo‘lmaydi."))
    assignment._audit_actor, assignment._audit_request = actor, request
    assignment.delete()


def deactivate_user(actor, user, request):
    _guard_target(actor, user)
    if user.pk == actor.pk:
        raise ActionNotAllowed(_("O‘zingizni o‘chirib bo‘lmaydi."))
    if _holds_admin(user) and user.is_active and active_admin_count(excluding=user) == 0:
        raise ActionNotAllowed(_("Oxirgi administratorni o‘chirib bo‘lmaydi."))
    user.is_active = False
    user.save(update_fields=["is_active"])
    closed = invalidate_user_sessions(user)
    record(AuditLog.Action.USER_DEACTIVATED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user, sessions_closed=closed))


def reactivate_user(actor, user, request):
    _guard_target(actor, user)
    user.is_active = True
    user.save(update_fields=["is_active"])
    record(AuditLog.Action.USER_REACTIVATED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user))


def unlock_keys(user):
    return [
        throttle.Key("login:user", str(user.pk)),
        throttle.Key("login:identifier", user.get_username().strip().lower()[:254]),
        throttle.Key("login:identifier", user.email.strip().lower()[:254]),
        throttle.Key("otp:user", str(user.pk)),
        throttle.Key("pwchange:user", str(user.pk)),
    ]


def unlock_account(actor, user, request):
    _guard_target(actor, user)
    throttle.clear(unlock_keys(user))  # IP counters are deliberately left alone: they belong to the address, not the account
    record(AuditLog.Action.ACCOUNT_UNLOCKED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user))


def is_account_locked(user):
    return any(throttle.is_locked(key) for key in unlock_keys(user))


def force_password_change(actor, user, request):
    _guard_target(actor, user)
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])
    record(AuditLog.Action.PASSWORD_CHANGE_FORCED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user))


def send_invitation(actor, user, request):
    """E-mail a one-time link to set the first password (the same mechanism and lifetime as a password reset)."""
    _guard_target(actor, user)
    if not user.is_active:
        raise ActionNotAllowed(_("Faol bo‘lmagan hisobga taklif yuborib bo‘lmaydi."))
    if not user.email:
        raise ActionNotAllowed(_("Foydalanuvchining e-pochtasi ko‘rsatilmagan."))
    if not throttle.reserve([throttle.Key("invite:user", str(user.pk), "keep")]).allowed:
        raise ActionNotAllowed(_("Taklifnomalar juda ko‘p yuborildi. Keyinroq urinib ko‘ring."))
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    link = request.build_absolute_uri(reverse("accounts:password_reset_confirm", args=[uid, default_token_generator.make_token(user)]))
    with override(user_language(user)):  # written in the invited person's language
        body = gettext(
            "Assalomu alaykum, %(name)s!\n\n"
            "Siz uchun %(site)s xodimlar portalida hisob yaratildi.\n"
            "Login: %(login)s\n\n"
            "Parolni o‘rnatish uchun havolaga o‘ting (30 daqiqa amal qiladi, faqat bir marta ishlaydi):\n\n%(link)s\n\n"
            "Havola muddati tugasa, kirish sahifasidagi «Parolni unutdingizmi?» orqali yangisini so‘rang.\n"
        ) % {"name": user.get_full_name() or user.get_username(), "site": settings.TWO_FACTOR_ISSUER, "login": user.get_username(), "link": link}
        subject = gettext("%(site)s: portalga taklif") % {"site": settings.TWO_FACTOR_ISSUER}
    try:
        EmailMessage(subject, body, to=[user.email]).send()
    except Exception as exc:  # noqa: BLE001
        logger.error("Invitation e-mail could not be sent (%s)", type(exc).__name__)
        raise ActionNotAllowed(_("Xatni yuborib bo‘lmadi. Pochta sozlamalarini tekshiring.")) from exc
    record(AuditLog.Action.USER_INVITED, request=request, user=actor, object_type="User", object_id=user.pk, meta=_meta(user))
