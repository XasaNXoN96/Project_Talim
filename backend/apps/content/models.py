from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class NewsCategory(TimeStampedModel):
    name = models.CharField("nomi", max_length=100, unique=True)
    slug = models.SlugField("slug", max_length=120, unique=True)

    class Meta:
        verbose_name = "yangilik kategoriyasi"
        verbose_name_plural = "yangilik kategoriyalari"
        ordering = ["name"]

    def __str__(self):
        return self.name


class NewsQuerySet(models.QuerySet):
    def published(self):
        """The ONLY queryset public pages may use: published and already due."""
        return self.filter(status=News.Status.PUBLISHED, publish_at__lte=timezone.now())


class News(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        REVIEW = "review", "Tekshiruvda"
        PUBLISHED = "published", "Nashr etilgan"
        ARCHIVED = "archived", "Arxiv"

    title = models.CharField("sarlavha", max_length=300)
    slug = models.SlugField("slug", max_length=320, unique=True)
    excerpt = models.TextField("qisqa tavsif", blank=True)
    # Plain text only on Day 1: rendered escaped. Rich text arrives together with an HTML sanitiser.
    body = models.TextField("matn")
    category = models.ForeignKey(NewsCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="news")
    status = models.CharField("holat", max_length=16, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField("nashr sanasi", null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = NewsQuerySet.as_manager()

    class Meta:
        verbose_name = "yangilik"
        verbose_name_plural = "yangiliklar"
        ordering = ["-publish_at", "-created_at"]
        permissions = [("publish_news", "Yangilikni nashr etish")]
        indexes = [models.Index(fields=["status", "-publish_at"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="published") | Q(publish_at__isnull=False),
                name="news_published_requires_date",
            )
        ]

    def __str__(self):
        return self.title
