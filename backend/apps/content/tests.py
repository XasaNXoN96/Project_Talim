from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import News, NewsCategory

NOW = timezone.now


def news(title, status="published", when=None, slug=None, body="Matn", **kw):
    if when is None and status == "published":
        when = NOW() - timedelta(hours=1)
    return News.objects.create(title=title, slug=slug or title.lower().replace(" ", "-"), status=status, publish_at=when, body=body, **kw)


class NewsVisibilityTests(TestCase):
    def setUp(self):
        self.ok = news("Chop etilgan yangilik")
        news("Qoralama yangilik", status="draft")
        news("Tekshiruvdagi yangilik", status="review")
        news("Arxivlangan yangilik", status="archived", when=NOW() - timedelta(days=3))
        news("Kelajak yangiligi", status="published", when=NOW() + timedelta(days=2))

    def test_published_queryset_only_returns_due_published(self):
        self.assertEqual(list(News.objects.published()), [self.ok])

    def test_home_shows_only_published(self):
        response = self.client.get(reverse("content:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chop etilgan yangilik")
        for hidden in ("Qoralama", "Tekshiruvdagi", "Arxivlangan", "Kelajak"):
            self.assertNotContains(response, hidden)

    def test_list_shows_only_published(self):
        response = self.client.get(reverse("content:news_list"))
        self.assertContains(response, "Chop etilgan yangilik")
        self.assertNotContains(response, "Qoralama")

    def test_detail_of_published_item(self):
        response = self.client.get(reverse("content:news_detail", args=[self.ok.slug]))
        self.assertEqual(response.status_code, 200)

    def test_detail_of_unpublished_items_is_404(self):
        for item in News.objects.exclude(pk=self.ok.pk):
            self.assertEqual(self.client.get(reverse("content:news_detail", args=[item.slug])).status_code, 404, msg=item.title)


class NewsRenderingTests(TestCase):
    def test_empty_state_when_no_news(self):
        self.assertContains(self.client.get(reverse("content:home")), "Hozircha yangiliklar yo‘q")
        self.assertContains(self.client.get(reverse("content:news_list")), "Hozircha yangiliklar yo‘q")

    def test_body_is_escaped(self):
        item = news("Xavfsizlik", body="<script>alert(1)</script>")
        response = self.client.get(reverse("content:news_detail", args=[item.slug]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_pagination(self):
        for i in range(15):
            news(f"Yangilik {i}", slug=f"y-{i}")
        first = self.client.get(reverse("content:news_list"))
        self.assertEqual(len(first.context["news_list"]), 12)
        self.assertEqual(len(self.client.get(reverse("content:news_list") + "?page=2").context["news_list"]), 3)

    def test_category_is_shown(self):
        cat = NewsCategory.objects.create(name="Tadbirlar", slug="tadbirlar")
        news("Toifali", category=cat)
        self.assertContains(self.client.get(reverse("content:news_list")), "Tadbirlar")


class NewsConstraintTests(TestCase):
    def test_published_requires_a_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            News.objects.create(title="Sanasiz", slug="sanasiz", body="x", status="published", publish_at=None)

    def test_slug_unique(self):
        news("Bir", slug="bir")
        with self.assertRaises(IntegrityError), transaction.atomic():
            news("Ikki", slug="bir")
