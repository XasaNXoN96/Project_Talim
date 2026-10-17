import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext, override

from apps.core.locale import user_language

from .models import Notification

logger = logging.getLogger(__name__)


def notify(user, kind, task, *, actor=None, dedupe_key=""):
    """Create one in-app notification. Never notifies the actor about their own action, nor an inactive user.
    With a dedupe_key the call is idempotent. Returns the notification or None."""
    if not user.is_active or (actor is not None and user.pk == actor.pk):
        return None
    try:
        with transaction.atomic():
            if dedupe_key:
                obj, created = Notification.objects.get_or_create(
                    user=user, dedupe_key=dedupe_key, defaults={"kind": kind, "task": task, "title": task.title[:200]}
                )
                if not created:
                    return None
            else:
                obj = Notification.objects.create(user=user, kind=kind, task=task, title=task.title[:200])
    except IntegrityError:  # lost a race with a parallel run of the reminder command
        return None
    transaction.on_commit(lambda: send_email_copy(obj))
    return obj


def notify_news(user, kind, news, *, actor=None, dedupe_key=""):
    """Same rules as notify(), for a news item: not the actor, not an inactive user, optional idempotency key. The e-mail copy (if enabled) carries only the event and the title."""
    if not user.is_active or (actor is not None and user.pk == actor.pk):
        return None
    try:
        with transaction.atomic():
            if dedupe_key:
                obj, created = Notification.objects.get_or_create(user=user, dedupe_key=dedupe_key[:120], defaults={"kind": kind, "news": news, "title": news.title[:200]})
                if not created:
                    return None
            else:
                obj = Notification.objects.create(user=user, kind=kind, news=news, title=news.title[:200])
    except IntegrityError:
        return None
    transaction.on_commit(lambda: send_email_copy(obj))
    return obj


def send_email_copy(notification):
    """Separate, optional layer. OFF by default; needs NOTIFICATION_EMAILS_ENABLED and a configured e-mail backend.
    The message has no link and no description: just the event and the task title."""
    if not settings.NOTIFICATION_EMAILS_ENABLED or not notification.user.email:
        return False
    with override(user_language(notification.user)):
        kind = str(notification.get_kind_display())
        body = gettext("%(kind)s: %(title)s\n\nBatafsil ma’lumot uchun xodimlar portaliga kiring.") % {"kind": kind, "title": notification.title}
    try:
        EmailMessage(f"{settings.TWO_FACTOR_ISSUER}: {kind}", body, to=[notification.user.email]).send()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Notification e-mail failed (%s)", type(exc).__name__)
        return False


def unread_count(user):
    return Notification.objects.filter(user=user, read_at__isnull=True).count() if user.is_authenticated else 0


def mark_all_read(user):
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())
