import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone

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


def send_email_copy(notification):
    """Separate, optional layer. OFF by default; needs NOTIFICATION_EMAILS_ENABLED and a configured e-mail backend.
    The message has no link and no description: just the event and the task title."""
    if not settings.NOTIFICATION_EMAILS_ENABLED or not notification.user.email:
        return False
    body = f"{notification.get_kind_display()}: {notification.title}\n\nBatafsil ma’lumot uchun xodimlar portaliga kiring."
    try:
        EmailMessage(f"{settings.TWO_FACTOR_ISSUER}: {notification.get_kind_display()}", body, to=[notification.user.email]).send()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Notification e-mail failed (%s)", type(exc).__name__)
        return False


def unread_count(user):
    return Notification.objects.filter(user=user, read_at__isnull=True).count() if user.is_authenticated else 0


def mark_all_read(user):
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())
