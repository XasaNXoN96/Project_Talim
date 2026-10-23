from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel

NOTICE_VERSION = 1  # raise it when the notice text changes: everybody has to accept again


class Conversation(TimeStampedModel):
    """A one-to-one conversation between two accounts. The pair is stored in a fixed order (low < high), so there is exactly one per pair.

    Nothing here is ever edited or deleted by users: the whole correspondence is kept, and administrators with `audit_chat` can read it
    (every such reading is written to the audit log). Participants are told so before they can use the chat."""

    user_low = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    user_high = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("suhbat")
        verbose_name_plural = _("suhbatlar")
        ordering = ["-last_message_at", "-created_at"]
        permissions = [
            ("use_chat", _("Chatdan foydalanish")),
            ("audit_chat", _("Barcha suhbatlarni ko‘rish (har bir ko‘rish jurnalga yoziladi)")),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(user_low__lt=F("user_high")), name="chat_pair_is_ordered"),
            models.UniqueConstraint(fields=["user_low", "user_high"], name="chat_one_conversation_per_pair"),
        ]

    def other(self, user):
        return self.user_high if self.user_low_id == user.pk else self.user_low

    def has(self, user):
        return user.pk in (self.user_low_id, self.user_high_id)


class Message(UUIDModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=2000)  # plain text, shown escaped
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)  # when the OTHER participant opened it

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"]), models.Index(fields=["conversation", "read_at"])]


class ChatNoticeAcceptance(models.Model):
    """The person has read that the correspondence is kept and may be read by administrators."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    version = models.PositiveSmallIntegerField(default=NOTICE_VERSION)
    accepted_at = models.DateTimeField(auto_now_add=True)
