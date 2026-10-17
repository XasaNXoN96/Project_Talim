"""The news approval workflow: ONE place that decides which status change is allowed, for whom, and what it leaves behind.

    draft ──submit──▶ review ──approve──▶ approved ──publish──▶ published ──unpublish──▶ draft
      ▲                 │  │                                        │
      │◀──withdraw──────┘  └──request_changes──▶ changes_requested  └─archive─▶ archived ──restore──▶ draft
      └──────────────────────submit──────────────────────┘
Editing an approved item sends it back to draft (it must be reviewed again); editing a review item is refused (withdraw first).

Every call is checked on the server, inside a transaction that locks the news row, so two editors deciding at once cannot both succeed:
the second one finds the status already changed and is refused. Decisions carry the version (updated_at) the editor actually read;
if the text changed in the meantime the decision is refused. Every change writes a NewsReview row (who, when, result, comment), an audit
record, and the notifications that apply. The caller (a view) only translates WorkflowError into a message."""
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
from apps.notifications.services import notify_news

from .models import News, NewsReview

S = News.Status
A = NewsReview.Action
K = Notification.Kind


class WorkflowError(Exception):
    """A refusal with a message that is safe to show to the user."""


@dataclass(frozen=True)
class Step:
    sources: frozenset
    target: str
    review_action: str
    audit_action: str
    permission: str  # the global permission needed; object-level rules are in check_actor()
    needs_comment: bool = False
    question: str = ""
    success: str = ""
    decision: bool = False  # a reviewer's decision on a particular version of the text


STEPS = {
    "submit": Step(frozenset({S.DRAFT, S.CHANGES_REQUESTED}), S.REVIEW, A.SUBMIT, AuditLog.Action.NEWS_SUBMITTED, "content.change_news",
                   question=_("Yangilikni tekshiruvga yuborasizmi? Tekshiruv tugaguncha uni tahrirlab bo‘lmaydi."), success=_("Yangilik tekshiruvga yuborildi.")),
    "withdraw": Step(frozenset({S.REVIEW}), S.DRAFT, A.WITHDRAW, AuditLog.Action.NEWS_WITHDRAWN, "content.change_news",
                     question=_("Yangilikni tekshiruvdan qaytarib olasizmi? U qoralamaga qaytadi."), success=_("Yangilik qoralamaga qaytarildi.")),
    "request_changes": Step(frozenset({S.REVIEW}), S.CHANGES_REQUESTED, A.REQUEST_CHANGES, AuditLog.Action.NEWS_CHANGES_REQUESTED, "content.review_news",
                            needs_comment=True, decision=True, question=_("Yangilikni tuzatishga qaytarasizmi? Muallif sizning izohingizni ko‘radi."),
                            success=_("Yangilik tuzatishga qaytarildi.")),
    "approve": Step(frozenset({S.REVIEW}), S.APPROVED, A.APPROVE, AuditLog.Action.NEWS_APPROVED, "content.review_news",
                    decision=True, question=_("Yangilikni ma’qullaysizmi? Shundan keyin vakolatli xodim uni nashr eta oladi."), success=_("Yangilik ma’qullandi.")),
    "publish": Step(frozenset({S.APPROVED}), S.PUBLISHED, A.PUBLISH, AuditLog.Action.NEWS_PUBLISHED, "content.publish_news",
                    question=_("Yangilikni nashr etasizmi? U ochiq saytda barcha uchun ko‘rinadi."), success=_("Yangilik nashr etildi.")),
    "unpublish": Step(frozenset({S.PUBLISHED}), S.DRAFT, A.UNPUBLISH, AuditLog.Action.NEWS_UNPUBLISHED, "content.publish_news",
                      question=_("Yangilikni nashrdan olasizmi? U ochiq saytdan yo‘qoladi va qoralamaga qaytadi."), success=_("Yangilik nashrdan olindi.")),
    "archive": Step(frozenset({S.DRAFT, S.REVIEW, S.CHANGES_REQUESTED, S.APPROVED, S.PUBLISHED}), S.ARCHIVED, A.ARCHIVE, AuditLog.Action.NEWS_ARCHIVED,
                    "content.publish_news", question=_("Yangilikni arxivlaysizmi? U ochiq saytdan yo‘qoladi."), success=_("Yangilik arxivlandi.")),
    "restore": Step(frozenset({S.ARCHIVED}), S.DRAFT, A.RESTORE, AuditLog.Action.NEWS_RESTORED, "content.publish_news",
                    question=_("Yangilikni arxivdan qoralamaga qaytarasizmi?"), success=_("Yangilik arxivdan qoralamaga qaytarildi.")),
}

# Statuses in which the text may be edited at all, and by whom (see can_edit)
EDITABLE_BY_WRITER = frozenset({S.DRAFT, S.CHANGES_REQUESTED, S.APPROVED})
COMMENT_MAX = 2000


def version_token(news):
    """What a reviewer's decision refers to. Changes whenever the item is saved."""
    return str(int(news.updated_at.timestamp() * 1_000_000))


def is_author(news, user):
    return news.author_id is not None and news.author_id == user.pk


def holds_explicitly(user, perm):
    """True only if the permission was GIVEN to this user (directly or through a group). A superuser's blanket right does not count: nobody
    approves their own item by being 'all-powerful'; the exception must be a deliberate grant."""
    app, codename = perm.split(".")
    return (user.is_active and (user.user_permissions.filter(content_type__app_label=app, codename=codename).exists()
                                or user.groups.filter(permissions__content_type__app_label=app, permissions__codename=codename).exists()))


def is_staff_for_news(user):
    return user.has_perm("content.review_news") or user.has_perm("content.publish_news")


def visible_news(user):
    """The items this person may see in the portal at all (list, preview, history, steps). Everything else is a 404, not a 403.
    Own items always; a reviewer also what has been submitted (not other people's drafts); a publisher what is approved or already out;
    people who write AND review/publish (content manager, administrator) see all. Rights themselves are checked separately."""
    qs = News.objects.all()
    if user.has_perm("content.change_news") and is_staff_for_news(user):
        return qs
    q = Q(author_id=user.pk)
    if user.has_perm("content.review_news"):
        q |= Q(status__in=[S.REVIEW, S.CHANGES_REQUESTED, S.APPROVED, S.PUBLISHED, S.ARCHIVED])
    if user.has_perm("content.publish_news"):
        q |= Q(status__in=[S.APPROVED, S.PUBLISHED, S.ARCHIVED])
    return qs.filter(q)


def can_see_internal(user, news):
    """Internal editorial notes: editorial staff only, and never the author of that very item (nor anyone who merely holds view_news)."""
    return is_staff_for_news(user) and not is_author(news, user)


def history_for(news, user):
    """The review history as this person may see it: author-facing comments for everyone who can see the item, internal notes only for staff."""
    show = can_see_internal(user, news)
    rows = list(news.reviews.select_related("actor"))
    for r in rows:
        if not show:
            r.internal_note = ""  # never rely on the template to hide it
    return rows


def can_edit(news, user):
    """Writers edit their own drafts (anyone's, if they also review or publish). Public or archived content needs the publishing right.
    An item under review is frozen: its reviewer must see the text that was submitted."""
    if not user.has_perm("content.change_news"):
        return False
    if news.status in EDITABLE_BY_WRITER:
        return is_author(news, user) or is_staff_for_news(user)
    return user.has_perm("content.publish_news") and news.status in (S.PUBLISHED, S.ARCHIVED)


def check_actor(step_name, news, user):
    step = STEPS[step_name]
    if not user.has_perm(step.permission):
        raise WorkflowError(_("Bu amal uchun ruxsatingiz yo‘q."))
    if step_name in ("submit", "withdraw") and not (is_author(news, user) or is_staff_for_news(user)):
        raise WorkflowError(_("Bu amal uchun ruxsatingiz yo‘q."))
    if step.decision and is_author(news, user) and not holds_explicitly(user, "content.approve_own_news"):
        raise WorkflowError(_("O‘z yangiligingizni ma’qullay yoki qaytara olmaysiz: uni boshqa tekshiruvchi ko‘rishi kerak."))


def allowed_steps(news, user):
    """What the interface may offer. The same checks run again when the step is performed."""
    out = []
    for name, step in STEPS.items():
        if news.status not in step.sources:
            continue
        try:
            check_actor(name, news, user)
        except WorkflowError:
            continue
        out.append(name)
    return out


def _reviewers(news):
    """Active users who may review: staff/superusers or holders of review_news (directly or through a group), minus the author unless allowed."""
    User = get_user_model()
    perm = Permission.objects.get(content_type__app_label="content", codename="review_news")
    own = Permission.objects.get(content_type__app_label="content", codename="approve_own_news")
    qs = User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(user_permissions=perm) | Q(groups__permissions=perm)).distinct()
    if news.author_id:
        allowed_own = User.objects.filter(Q(is_superuser=True) | Q(user_permissions=own) | Q(groups__permissions=own)).values("pk")
        qs = qs.exclude(Q(pk=news.author_id) & ~Q(pk__in=allowed_own))
    return qs


@transaction.atomic
def perform(step_name, news_pk, user, request=None, comment="", version=None, note=""):
    """Do one step or raise WorkflowError. Returns the news."""
    step = STEPS[step_name]
    comment = (comment or "").strip()
    note = (note or "").strip() if step.decision else ""
    news = visible_news(user).select_for_update().get(pk=news_pk)  # DoesNotExist for an item this person may not see: the view answers 404
    if news.status not in step.sources:
        raise WorkflowError(_("Bu amalni hozirgi holatda bajarib bo‘lmaydi."))  # also: a double click / the other editor was faster
    check_actor(step_name, news, user)
    if step.needs_comment and not comment:
        raise WorkflowError(_("Qaytarish uchun izoh yozing."))
    if len(comment) > COMMENT_MAX or len(note) > COMMENT_MAX:
        raise WorkflowError(_("Izoh juda uzun."))
    if step.decision and version != version_token(news):  # a missing version is refused too: a crafted request cannot skip the check
        raise WorkflowError(_("Yangilik siz ko‘rganingizdan keyin o‘zgargan. Sahifani yangilab, qayta ko‘rib chiqing."))
    before = news.status
    news.status = step.target
    fields = ["status", "updated_at"]
    if step.target == S.PUBLISHED:
        if news.publish_at is None or news.publish_at <= timezone.now():
            news.publish_at = timezone.now()  # a future date is a schedule and stays
        fields.append("publish_at")
    news.save(update_fields=fields)
    finish(news, step, user, request, before, comment, note)
    return news


def finish(news, step, user, request, before, comment, note=""):
    NewsReview.objects.create(news=news, actor=user, action=step.review_action, from_status=before, to_status=news.status, comment=comment, internal_note=note)
    meta = {"from": before, "to": news.status}
    if comment:
        meta["comment_length"] = len(comment)  # the text itself lives in NewsReview, not in the audit log
    if note:
        meta["note_length"] = len(note)
    record(step.audit_action, request=request, user=user, object_type="News", object_id=news.pk, meta=meta)
    if step.review_action == A.SUBMIT:
        for reviewer in _reviewers(news):
            notify_news(reviewer, K.NEWS_SUBMITTED, news, actor=user, dedupe_key=f"news-submit-{news.pk}-{news.updated_at.timestamp()}")
    elif step.review_action == A.REQUEST_CHANGES and news.author:
        notify_news(news.author, K.NEWS_CHANGES_REQUESTED, news, actor=user)
    elif step.review_action == A.APPROVE and news.author:
        notify_news(news.author, K.NEWS_APPROVED, news, actor=user)


def reset_after_edit(news, user, request, changed_fields):
    """Called by the edit view inside its transaction: text changed after approval -> back to draft, with a history row."""
    if news.status != S.APPROVED or not changed_fields:
        return False
    before = news.status
    news.status = S.DRAFT
    news.save(update_fields=["status", "updated_at"])
    NewsReview.objects.create(news=news, actor=user, action=A.EDIT_RESET, from_status=before, to_status=news.status)
    return True
