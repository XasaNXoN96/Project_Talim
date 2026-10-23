"""Chat rules. The views only call these; they cannot be bypassed by another view."""
import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import NOTICE_VERSION, ChatNoticeAcceptance, Conversation, Message

User = get_user_model()
MAX_BODY = 2000
RATE_LIMIT = 20  # messages per minute and person


class ChatError(Exception):
    """A refusal with a message that is safe to show."""


def chat_users():
    """Accounts that may chat: active and holding use_chat (directly, through a role, or as superuser)."""
    from django.contrib.auth.models import Permission

    perm = Permission.objects.filter(content_type__app_label="chat", codename="use_chat").first()
    if perm is None:
        return User.objects.none()
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(user_permissions=perm) | Q(groups__permissions=perm)).distinct()


def has_accepted(user):
    return ChatNoticeAcceptance.objects.filter(user=user, version=NOTICE_VERSION).exists()


def accept_notice(user):
    ChatNoticeAcceptance.objects.update_or_create(user=user, defaults={"version": NOTICE_VERSION})


def my_conversations(user):
    return Conversation.objects.filter(Q(user_low=user) | Q(user_high=user)).select_related("user_low", "user_high")


def start(user, other):
    """The one conversation between the two accounts (created if missing)."""
    if other.pk == user.pk:
        raise ChatError(_("O‘zingiz bilan suhbat ochib bo‘lmaydi."))
    if not chat_users().filter(pk=other.pk).exists():
        raise ChatError(_("Bu foydalanuvchi bilan yozishib bo‘lmaydi."))
    low, high = sorted((user, other), key=lambda u: u.pk)
    try:
        with transaction.atomic():
            conv, _created = Conversation.objects.get_or_create(user_low=low, user_high=high)
    except IntegrityError:  # two people opened it at the same moment
        conv = Conversation.objects.get(user_low=low, user_high=high)
    return conv


@transaction.atomic
def send(user, conv, body):
    if not conv.has(user):
        raise ChatError(_("Bu suhbat sizniki emas."))
    if not conv.other(user).is_active:
        raise ChatError(_("Suhbatdosh faol emas: unga yozib bo‘lmaydi."))
    body = (body or "").strip()
    if not body:
        raise ChatError(_("Xabar bo‘sh."))
    if len(body) > MAX_BODY:
        raise ChatError(_("Xabar juda uzun."))
    since = timezone.now() - datetime.timedelta(minutes=1)
    if Message.objects.filter(sender=user, created_at__gte=since).count() >= RATE_LIMIT:
        raise ChatError(_("Juda tez yozyapsiz. Bir daqiqadan keyin qayta urinib ko‘ring."))
    msg = Message.objects.create(conversation=conv, sender=user, body=body)
    Conversation.objects.filter(pk=conv.pk).update(last_message_at=msg.created_at)
    return msg


def mark_read(user, conv):
    """The messages the OTHER person wrote are read once their recipient opens the conversation."""
    Message.objects.filter(conversation=conv, read_at__isnull=True).exclude(sender=user).update(read_at=timezone.now())


def unread_count(user):
    if not getattr(user, "is_authenticated", False):
        return 0
    return Message.objects.filter(read_at__isnull=True).filter(Q(conversation__user_low=user) | Q(conversation__user_high=user)).exclude(sender=user).count()


def summaries(user):
    """[(conversation, other user, last message, unread)] for the inbox, newest first."""
    out = []
    convs = list(my_conversations(user).annotate(unread=Count("messages", filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=user))))
    last = {m.conversation_id: m for m in Message.objects.filter(conversation__in=convs).order_by("conversation_id", "-created_at").distinct("conversation_id")}
    for c in convs:
        out.append((c, c.other(user), last.get(c.pk), c.unread))
    return out
