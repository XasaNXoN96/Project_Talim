"""The achievement workflow: ONE place that decides which status change is allowed, for whom, and what it leaves behind.

    draft ──submit──▶ submitted ──save_draft──▶ prepared ──publish──▶ published ──unpublish──▶ prepared
      ▲                 │   │                       ▲                      │
      │◀──withdraw──────┘   └─request_changes─▶ changes_requested ─submit─▶ (submitted)
      └ archive from any state except archived ▶ archived ──restore──▶ prepared

A school (the director) writes and submits its own items. Whoever holds `publish_achievement` checks them, may complete them, and either
saves them as a ready draft or publishes. Publishing is NEVER one click: the publisher must have opened the preview of the CURRENT version
first (the preview hands out a token; publish refuses a missing or stale token). Every step is checked on the server inside a transaction
that locks the row; every step writes a review row, an audit record and the notifications that apply."""
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.notifications.models import Notification
from apps.notifications.services import notify_achievement
from apps.organization.access import own_institution_id

from .models import Achievement, AchievementReview

S = Achievement.Status
A = AchievementReview.Action
COMMENT_MAX = 2000


class WorkflowError(Exception):
    """A refusal with a message that is safe to show to the user."""


@dataclass(frozen=True)
class Step:
    sources: frozenset
    target: str
    review_action: str
    needs_comment: bool = False
    success: str = ""


STEPS = {
    "submit": Step(frozenset({S.DRAFT, S.CHANGES_REQUESTED}), S.SUBMITTED, A.SUBMIT, success=_("Yutuq tekshiruvga yuborildi.")),
    "withdraw": Step(frozenset({S.SUBMITTED}), S.DRAFT, A.WITHDRAW, success=_("Yutuq qoralamaga qaytarildi.")),
    "request_changes": Step(frozenset({S.SUBMITTED}), S.CHANGES_REQUESTED, A.REQUEST_CHANGES, needs_comment=True, success=_("Yutuq tuzatishga qaytarildi.")),
    "save_draft": Step(frozenset({S.SUBMITTED, S.DRAFT}), S.PREPARED, A.SAVE_DRAFT, success=_("Yutuq tayyor qoralama sifatida saqlandi. U hali ochiq saytda ko‘rinmaydi.")),
    "publish": Step(frozenset({S.SUBMITTED, S.PREPARED, S.DRAFT}), S.PUBLISHED, A.PUBLISH, success=_("Yutuq nashr etildi.")),
    "unpublish": Step(frozenset({S.PUBLISHED}), S.PREPARED, A.UNPUBLISH, success=_("Yutuq nashrdan olindi va tayyor qoralamaga qaytarildi.")),
    "archive": Step(frozenset({S.DRAFT, S.SUBMITTED, S.CHANGES_REQUESTED, S.PREPARED, S.PUBLISHED}), S.ARCHIVED, A.ARCHIVE, success=_("Yutuq arxivlandi.")),
    "restore": Step(frozenset({S.ARCHIVED}), S.PREPARED, A.RESTORE, success=_("Yutuq arxivdan tayyor qoralamaga qaytarildi.")),
}
SCHOOL_STEPS = {"submit", "withdraw"}
STAFF_STEPS = set(STEPS) - SCHOOL_STEPS


def is_staff(user):
    return user.is_authenticated and user.is_active and user.has_perm("achievements.publish_achievement")


def school_id(user):
    """The institution a school user (not staff) works for; None if they have none."""
    return own_institution_id(user) if user.is_authenticated and user.is_active else None


def visible_achievements(user):
    """What this person may open in the portal. Everything else is a 404. Staff see everything that was SENT (plus their own drafts);
    a school sees every item of its own institution."""
    if not (user.is_authenticated and user.is_active and user.has_perm("achievements.view_achievement")):
        return Achievement.objects.none()
    qs = Achievement.objects.all()
    if is_staff(user):
        return qs.exclude(Q(status=S.DRAFT) & ~Q(created_by_id=user.pk))
    sid = school_id(user)
    return qs.filter(institution_id=sid) if sid else qs.none()


def _is_school_of(user, a):
    sid = school_id(user)
    return sid is not None and sid == a.institution_id


def version_token(a):
    """What a preview (and so a publish decision) refers to. Changes whenever the item or its pictures are saved."""
    return str(int(a.updated_at.timestamp() * 1_000_000))


def can_edit(a, user):
    if not user.has_perm("achievements.change_achievement"):
        return False
    if is_staff(user):
        return a.status in (S.SUBMITTED, S.PREPARED, S.CHANGES_REQUESTED) or (a.status == S.DRAFT and a.created_by_id == user.pk)
    return a.status in (S.DRAFT, S.CHANGES_REQUESTED) and _is_school_of(user, a)


def check_actor(step_name, a, user):
    if step_name in SCHOOL_STEPS:
        if not (user.has_perm("achievements.change_achievement") and (_is_school_of(user, a) or (is_staff(user) and a.created_by_id == user.pk))):
            raise WorkflowError(_("Bu amal uchun ruxsatingiz yo‘q."))
    elif not is_staff(user):
        raise WorkflowError(_("Bu amal uchun ruxsatingiz yo‘q."))
    if a.status == S.DRAFT and a.created_by_id != user.pk and not _is_school_of(user, a):
        raise WorkflowError(_("Bu amal uchun ruxsatingiz yo‘q."))  # nobody else works on a draft that was not sent


def allowed_steps(a, user):
    out = []
    for name, step in STEPS.items():
        if a.status not in step.sources:
            continue
        try:
            check_actor(name, a, user)
        except WorkflowError:
            continue
        out.append(name)
    return out


def _staff_users():
    perm = Permission.objects.filter(content_type__app_label="achievements", codename="publish_achievement").first()
    if perm is None:
        return get_user_model().objects.none()
    return get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(user_permissions=perm) | Q(groups__permissions=perm)).distinct()


@transaction.atomic
def perform(step_name, a_pk, user, *, comment="", previewed_token="", request=None):
    """Run one step. Returns the refreshed achievement. Raises WorkflowError."""
    if step_name not in STEPS:
        raise WorkflowError(_("Noma’lum amal."))
    a = Achievement.objects.select_for_update().get(pk=a_pk)
    step = STEPS[step_name]
    if a.status not in step.sources:
        raise WorkflowError(_("Yutuq holati o‘zgargan: sahifani yangilang."))
    check_actor(step_name, a, user)
    comment = (comment or "").strip()
    if step.needs_comment and not comment:
        raise WorkflowError(_("Muallif uchun izoh yozing."))
    if len(comment) > COMMENT_MAX:
        raise WorkflowError(_("Izoh juda uzun."))
    if step_name == "submit" and not a.consent_confirmed:
        raise WorkflowError(_("Yuborishdan oldin ishtirokchining nashrga roziligini tasdiqlang."))
    if step_name == "publish":
        if not previewed_token or previewed_token != version_token(a):
            raise WorkflowError(_("Nashr etishdan oldin yutuqning joriy ko‘rinishini oldindan ko‘rib chiqing."))
        if not a.consent_confirmed:
            raise WorkflowError(_("Nashrga rozilik tasdiqlanmagan: yutuqni tahrirlab, rozilikni belgilang."))
    old = a.status
    a.status = step.target
    if step_name == "publish":
        a.publish_at = timezone.now()
    a.save()
    AchievementReview.objects.create(achievement=a, actor=user, action=step.review_action, from_status=old, to_status=step.target, comment=comment)
    record(
        AuditLog.Action.ACHIEVEMENT_PUBLISHED if step_name == "publish" else AuditLog.Action.ACHIEVEMENT_STEP,
        request=request, user=user, object_type="Achievement", object_id=a.pk, meta={"step": step_name, "from": old, "to": step.target},
    )
    K = Notification.Kind
    if step_name == "submit":
        for staff in _staff_users():
            notify_achievement(staff, K.ACHIEVEMENT_SUBMITTED, a, actor=user)
    elif step_name in ("request_changes", "publish") and a.created_by_id:
        kind = K.ACHIEVEMENT_RETURNED if step_name == "request_changes" else K.ACHIEVEMENT_PUBLISHED
        notify_achievement(a.created_by, kind, a, actor=user)
    return a
