"""A person's request to correct their own data: ONE place for what may happen, to whom, and what it leaves behind.

    pending ──approve──▶ approved        (the data of the card is changed, now)
       │   └──reject───▶ rejected        (comment for the person is required)
       └──cancel (by the person) ──▶ cancelled

Rules: one open request per person (a new submission replaces the open one); only the listed self-editable fields; nobody decides on
their OWN request; a decision is made under a row lock so two reviewers cannot both decide. A decision empties the stored old/new values
(personal data) and keeps only the field names. Audit entries and notifications never carry the values."""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.notifications.models import Notification
from apps.notifications.services import notify_change

from .models import SELF_EDITABLE_FIELDS, Employee, EmployeeChangeRequest

S = EmployeeChangeRequest.Status
COMMENT_MAX = 1000


class ChangeError(Exception):
    """A refusal with a message that is safe to show."""


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def current_values(employee, fields=SELF_EDITABLE_FIELDS):
    return {f: _text(getattr(employee, f)) for f in fields}


def _reviewers():
    perm = Permission.objects.filter(content_type__app_label="organization", codename="review_employee_change").first()
    if perm is None:
        return get_user_model().objects.none()
    return get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(user_permissions=perm) | Q(groups__permissions=perm)).distinct()


@transaction.atomic
def submit(employee, user, new_values, *, request=None):
    """`new_values` = {field: cleaned value} for the fields that really differ. Replaces the person's open request."""
    if employee.user_id != user.pk:
        raise ChangeError(_("Faqat o‘z ma’lumotingizni o‘zgartirishni so‘rashingiz mumkin."))
    if employee.status == Employee.Status.ARCHIVED:
        raise ChangeError(_("Arxivdagi karta uchun so‘rov yuborib bo‘lmaydi."))
    fields = [f for f in SELF_EDITABLE_FIELDS if f in new_values]
    if not fields:
        raise ChangeError(_("O‘zgarish topilmadi: avval ma’lumotni o‘zgartiring."))
    EmployeeChangeRequest.objects.select_for_update().filter(employee=employee, status=S.PENDING).update(
        status=S.CANCELLED, decided_at=timezone.now(), fields=[], changes={}, old_values={}, decision_comment=""
    )
    old = current_values(employee, fields)
    req = EmployeeChangeRequest.objects.create(
        employee=employee, requested_by=user, fields=fields, changes={f: _text(new_values[f]) for f in fields}, old_values=old
    )
    record(AuditLog.Action.PROFILE_CHANGE_REQUESTED, request=request, user=user, object_type="EmployeeChangeRequest", object_id=req.pk, meta={"fields": fields})
    for reviewer in _reviewers():
        notify_change(reviewer, Notification.Kind.PROFILE_CHANGE_ASKED, req, actor=user)
    return req


def _lock_open(pk):
    req = EmployeeChangeRequest.objects.select_for_update().select_related("employee").get(pk=pk)
    if req.status != S.PENDING:
        raise ChangeError(_("So‘rov holati o‘zgargan: sahifani yangilang."))
    return req


def _finish(req, status, actor, comment, request, action_label):
    req.status = status
    req.decided_by, req.decided_at, req.decision_comment = actor, timezone.now(), comment
    req.changes, req.old_values = {}, {}  # personal data is not kept after the decision
    req.save()
    record(AuditLog.Action.PROFILE_CHANGE_DECIDED, request=request, user=actor, object_type="EmployeeChangeRequest", object_id=req.pk,
           meta={"decision": action_label, "fields": req.fields})


def _check_reviewer(req, actor):
    if not actor.has_perm("organization.review_employee_change"):
        raise ChangeError(_("Bu amal uchun ruxsatingiz yo‘q."))
    if req.requested_by_id == actor.pk:
        raise ChangeError(_("O‘z so‘rovingizni o‘zingiz tasdiqlay yoki rad eta olmaysiz: uni boshqa xodim ko‘rib chiqishi kerak."))


@transaction.atomic
def approve(pk, actor, *, request=None):
    req = _lock_open(pk)
    _check_reviewer(req, actor)
    employee = Employee.objects.select_for_update().get(pk=req.employee_id)
    for name, raw in req.changes.items():
        if name not in SELF_EDITABLE_FIELDS:
            continue  # defence in depth: a tampered row can never touch other fields
        field = Employee._meta.get_field(name)
        try:
            setattr(employee, name, field.clean(None if (raw == "" and field.null) else raw, employee))
        except ValidationError as exc:
            raise ChangeError(_("Qiymat yaroqsiz: so‘rovni rad eting yoki xodimdan qayta yuborishni so‘rang.")) from exc
    employee.save()
    _finish(req, S.APPROVED, actor, "", request, "approved")
    if req.requested_by_id and req.requested_by.is_active:
        notify_change(req.requested_by, Notification.Kind.PROFILE_CHANGE_DONE, req, actor=actor)
    return req


@transaction.atomic
def reject(pk, actor, comment, *, request=None):
    req = _lock_open(pk)
    _check_reviewer(req, actor)
    comment = (comment or "").strip()
    if not comment:
        raise ChangeError(_("Rad etish sababini yozing: xodim uni ko‘radi."))
    if len(comment) > COMMENT_MAX:
        raise ChangeError(_("Izoh juda uzun."))
    _finish(req, S.REJECTED, actor, comment, request, "rejected")
    if req.requested_by_id and req.requested_by.is_active:
        notify_change(req.requested_by, Notification.Kind.PROFILE_CHANGE_DENIED, req, actor=actor)
    return req


@transaction.atomic
def cancel(pk, user, *, request=None):
    req = _lock_open(pk)
    if req.requested_by_id != user.pk:
        raise ChangeError(_("Bu amal uchun ruxsatingiz yo‘q."))
    _finish(req, S.CANCELLED, user, "", request, "cancelled")
    return req
