from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.documents.storage import PrivateStorage


class NewsCategory(TimeStampedModel):
    name = models.CharField(_("nomi"), max_length=100, unique=True)
    slug = models.SlugField("slug", max_length=120, unique=True)

    class Meta:
        verbose_name = _("yangilik kategoriyasi")
        verbose_name_plural = _("yangilik kategoriyalari")
        ordering = ["name"]

    def __str__(self):
        return self.name


class NewsQuerySet(models.QuerySet):
    def published(self):
        """The ONLY queryset public pages may use: published and already due."""
        return self.filter(status=News.Status.PUBLISHED, publish_at__lte=timezone.now())


class News(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Qoralama")
        REVIEW = "review", _("Tekshiruvda")
        CHANGES_REQUESTED = "changes_requested", _("Tuzatish talab etiladi")
        APPROVED = "approved", _("Ma’qullangan")
        PUBLISHED = "published", _("Nashr etilgan")
        ARCHIVED = "archived", _("Arxiv")

    title = models.CharField(_("sarlavha"), max_length=300)
    slug = models.SlugField("slug", max_length=320, unique=True)
    excerpt = models.TextField(_("qisqa tavsif"), blank=True)
    # Plain text only on Day 1: rendered escaped. Rich text arrives together with an HTML sanitiser.
    body = models.TextField(_("matn"))
    category = models.ForeignKey(NewsCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="news")
    status = models.CharField(_("holat"), max_length=24, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField(_("nashr sanasi"), null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # Cover picture: re-encoded JPEG in the private storage (like achievement pictures), served only through the views; public only once published.
    cover = models.FileField(storage=PrivateStorage(), max_length=120, blank=True)

    objects = NewsQuerySet.as_manager()

    class Meta:
        verbose_name = _("yangilik")
        verbose_name_plural = _("yangiliklar")
        ordering = ["-publish_at", "-created_at"]
        permissions = [
            ("publish_news", _("Yangilikni nashr etish")),
            ("review_news", _("Yangilikni tekshirish: ma’qullash yoki tuzatishga qaytarish")),
            # Deliberately granted to NO default role: whoever wrote a news item cannot be the one who approves it.
            ("approve_own_news", _("O‘z yangiligini ma’qullash (istisno)")),
        ]
        indexes = [models.Index(fields=["status", "-publish_at"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="published") | Q(publish_at__isnull=False),
                name="news_published_requires_date",
            )
        ]

    def __str__(self):
        return self.title


class NewsReview(TimeStampedModel):
    """Append-only history of the approval workflow: who did what to which news, when, with which comment.
    Rows are written by apps.content.workflow only; there is no view or form that edits or deletes them."""

    class Action(models.TextChoices):
        SUBMIT = "submit", _("Tekshiruvga yuborildi")
        WITHDRAW = "withdraw", _("Tekshiruvdan qaytarib olindi")
        REQUEST_CHANGES = "request_changes", _("Tuzatishga qaytarildi")
        APPROVE = "approve", _("Ma’qullandi")
        PUBLISH = "publish", _("Nashr etildi")
        UNPUBLISH = "unpublish", _("Nashrdan olindi")
        ARCHIVE = "archive", _("Arxivlandi")
        RESTORE = "restore", _("Arxivdan qaytarildi")
        EDIT_RESET = "edit_reset", _("Ma’qullangandan keyin o‘zgartirildi: qayta tekshiruv kerak")

    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="reviews")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=24, choices=Action.choices)
    from_status = models.CharField(max_length=24)
    to_status = models.CharField(max_length=24)
    # comment: written FOR the author (shown to everyone who may see the item, including the author).
    # internal_note: editorial staff only; never shown to the author or to people who merely hold view_news (added on day 19;
    # every older row keeps its text in `comment`, where it was always visible to the author, and has an empty internal_note).
    comment = models.TextField(blank=True, max_length=2000)
    internal_note = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["news", "created_at"])]
