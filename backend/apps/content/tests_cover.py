import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.testing import login_with_two_factor, make_user

from .models import News


def png(size=(60, 40), color=(200, 30, 30)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


class CoverTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.cm = make_user("cm", role="content_manager")
        self.client_cm = Client()
        login_with_two_factor(self.client_cm, self.cm)

    def create(self, **extra):
        data = {"title": "Rasmli yangilik", "excerpt": "Q", "body": "Matn", **extra}
        r = self.client_cm.post(reverse("news_admin:create"), data)
        self.assertEqual(r.status_code, 302, r.content[:300])
        return News.objects.get(title="Rasmli yangilik")

    def test_a_picture_is_checked_re_encoded_and_stored_under_a_random_name(self):
        news = self.create(cover_new=SimpleUploadedFile("holiday.png", png(), content_type="image/png"))
        self.assertTrue(news.cover)
        self.assertRegex(news.cover.name, r"^[0-9a-f]{2}/[0-9a-f]{32}\.jpg$")
        self.assertNotIn("holiday", news.cover.name)
        with news.cover.storage.open(news.cover.name, "rb") as fh:
            self.assertEqual(Image.open(fh).format, "JPEG")

    def test_a_file_that_is_not_a_picture_is_refused_and_nothing_is_saved(self):
        r = self.client_cm.post(reverse("news_admin:create"), {"title": "Soxta", "excerpt": "", "body": "Matn", "cover_new": SimpleUploadedFile("a.png", b"<script>alert(1)</script>", content_type="image/png")})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(News.objects.filter(title="Soxta").exists())

    def test_only_a_published_cover_is_public_and_a_draft_is_for_the_portal_only(self):
        news = self.create(cover_new=SimpleUploadedFile("c.png", png(), content_type="image/png"))
        public, portal = reverse("content:news_cover", args=[news.pk]), reverse("news_admin:cover", args=[news.pk])
        self.assertEqual(Client().get(public).status_code, 404)             # a draft does not exist for the public
        self.assertEqual(Client().get(portal).status_code, 302)             # the portal asks to sign in
        r = self.client_cm.get(portal)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", r["Cache-Control"])
        News.objects.filter(pk=news.pk).update(status="published", publish_at=timezone.now())
        r = Client().get(public)
        self.assertEqual(r.status_code, 200)
        self.assertIn("public", r["Cache-Control"])
        page = Client().get(reverse("content:news_detail", args=[News.objects.get(pk=news.pk).slug])).content.decode()
        self.assertIn(public, page)
        self.assertIn(public, Client().get(reverse("content:news_list")).content.decode())

    def test_a_news_item_without_a_cover_has_none(self):
        news = self.create()
        News.objects.filter(pk=news.pk).update(status="published", publish_at=timezone.now())
        self.assertEqual(Client().get(reverse("content:news_cover", args=[news.pk])).status_code, 404)

    def test_replacing_and_removing_the_cover_deletes_the_old_file(self):
        news = self.create(cover_new=SimpleUploadedFile("c.png", png(), content_type="image/png"))
        old = news.cover.name
        storage = news.cover.storage
        edit = reverse("news_admin:edit", args=[news.pk])
        base = {"title": news.title, "excerpt": "Q", "body": "Matn"}
        self.client_cm.post(edit, {**base, "cover_new": SimpleUploadedFile("d.png", png(color=(0, 90, 200)), content_type="image/png")})
        news.refresh_from_db()
        self.assertNotEqual(news.cover.name, old)
        self.assertFalse(storage.exists(old))
        new = news.cover.name
        self.client_cm.post(edit, {**base, "cover_remove": "on"})
        news.refresh_from_db()
        self.assertFalse(news.cover)
        self.assertFalse(storage.exists(new))
