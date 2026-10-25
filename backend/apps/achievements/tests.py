import io
import re

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts import services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.documents.storage import new_storage_name
from apps.notifications.models import Notification
from apps.organization.models import Department, Institution

from .models import Achievement, AchievementImage

User = get_user_model()


def png(size=(1200, 800)):
    out = io.BytesIO()
    Image.new("RGB", size, (180, 40, 40)).save(out, "PNG")
    return out.getvalue()


def f(name, data, ctype="image/png"):
    return SimpleUploadedFile(name, data, content_type=ctype)


@override_settings(DOCUMENT_SCAN_MODE="disabled")
class AchievementTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        mk = lambda n, i: services.create_user(self.admin, username=n, email=f"{n}@example.test", first_name=n, last_name="D", role="school_director", department=None, institution=i, request=None)
        self.d1, self.d2 = mk("dir1", self.s1), mk("dir2", self.s2)
        self.ca, self.c1, self.c2 = Client(), Client(), Client()
        for c, u in ((self.ca, self.admin), (self.c1, self.d1), (self.c2, self.d2)):
            login_with_two_factor(c, u)

    def data(self, **extra):
        d = {"kind": "medal", "title": "Respublika olimpiadasi, 1-o‘rin", "person_kind": "teacher", "person_name": "Karimov Vali", "person_position": "Matematika",
             "level": "republic", "awarded_on": "2026-05-01", "description": "Tavsif matni", "video_url": "", "consent_confirmed": "on"}
        d.update(extra)
        return d

    def create(self, client=None, **extra):
        r = (client or self.c1).post(reverse("achievements:create"), self.data(**extra))
        self.assertEqual(r.status_code, 302, getattr(r, "content", b"")[:300])
        return Achievement.objects.latest("created_at")

    def step(self, client, a, name, **post):
        return client.post(reverse("achievements:step", args=[a.pk, name]), post)

    # ---- the school side -------------------------------------------------------------------------------------
    def test_school_creates_in_its_own_institution_as_draft(self):
        a = self.create(institution=str(self.s2.pk))  # a smuggled institution is ignored
        self.assertEqual((a.institution, a.status, a.created_by), (self.s1, "draft", self.d1))
        self.assertTrue(AuditLog.objects.filter(action="achievement_created", object_id=str(a.pk)).exists())

    def test_pictures_are_validated_reencoded_limited_and_private(self):
        a = self.create()
        r = self.c1.post(reverse("achievements:edit", args=[a.pk]), self.data(new_images=[f("a.png", png()), f("b.png", png((300, 300)))]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(a.images.count(), 2)
        im = a.images.first()
        with im.file.storage.open(im.file.name, "rb") as fh:
            stored = Image.open(io.BytesIO(fh.read()))
        self.assertEqual(stored.format, "JPEG")
        self.assertLessEqual(max(stored.size), 1600)
        with self.assertRaises(ValueError):
            im.file.url
        bad = self.c1.post(reverse("achievements:edit", args=[a.pk]), self.data(new_images=[f("x.svg", b"<svg><script>1</script></svg>", "image/svg+xml")]))
        self.assertEqual(bad.status_code, 200)
        many = self.c1.post(reverse("achievements:edit", args=[a.pk]), self.data(new_images=[f(f"{i}.png", png((50, 50))) for i in range(4)]))
        self.assertEqual(many.status_code, 200)  # 2 + 4 > 5
        self.assertEqual(a.images.count(), 2)

    def test_video_is_a_https_link_only(self):
        for url in ("http://example.test/v", "javascript:alert(1)", "ftp://example.test/v"):
            r = self.c1.post(reverse("achievements:create"), self.data(video_url=url))
            self.assertEqual(r.status_code, 200, url)
        self.assertEqual(Achievement.objects.count(), 0)
        a = self.create(video_url="https://example.test/video")
        self.assertEqual(a.video_url, "https://example.test/video")

    def test_submit_needs_consent_and_notifies_the_administrators(self):
        a = self.create(consent_confirmed="")
        self.step(self.c1, a, "submit")
        a.refresh_from_db()
        self.assertEqual(a.status, "draft")  # refused: no consent
        self.c1.post(reverse("achievements:edit", args=[a.pk]), self.data())
        self.assertEqual(self.step(self.c1, a, "submit").status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, "submitted")
        self.assertTrue(Notification.objects.filter(user=self.admin, achievement=a, kind="achievement_submitted").exists())
        self.assertFalse(Notification.objects.filter(user=self.d1, achievement=a).exists())

    def test_school_cannot_edit_after_submit_and_cannot_see_others(self):
        a = self.create()
        self.step(self.c1, a, "submit")
        self.assertEqual(self.c1.get(reverse("achievements:edit", args=[a.pk])).status_code, 403)
        self.assertEqual(self.c2.get(reverse("achievements:detail", args=[a.pk])).status_code, 404)
        self.assertNotIn("Respublika", self.c2.get(reverse("achievements:list")).content.decode())
        self.assertEqual(self.step(self.c2, a, "withdraw").status_code, 404)
        self.assertEqual(self.step(self.c1, a, "publish").status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, "submitted")  # a school cannot publish

    # ---- the administrator side ------------------------------------------------------------------------------
    def submitted(self):
        a = self.create()
        self.step(self.c1, a, "submit")
        a.refresh_from_db()
        return a

    def test_admin_does_not_see_unsent_school_drafts(self):
        a = self.create()
        self.assertEqual(self.ca.get(reverse("achievements:detail", args=[a.pk])).status_code, 404)
        self.step(self.c1, a, "submit")
        self.assertEqual(self.ca.get(reverse("achievements:detail", args=[a.pk])).status_code, 200)

    def test_publish_is_never_one_click(self):
        a = self.submitted()
        self.step(self.ca, a, "publish")  # no preview opened yet
        a.refresh_from_db()
        self.assertEqual(a.status, "submitted")
        self.assertEqual(Achievement.objects.published().count(), 0)
        self.assertEqual(self.ca.get(reverse("achievements:preview", args=[a.pk])).status_code, 200)
        self.step(self.ca, a, "publish")
        a.refresh_from_db()
        self.assertEqual(a.status, "published")
        self.assertIsNotNone(a.publish_at)
        self.assertEqual(Achievement.objects.published().count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.d1, achievement=a, kind="achievement_published").exists())

    def test_a_change_after_the_preview_invalidates_it(self):
        a = self.submitted()
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.ca.post(reverse("achievements:edit", args=[a.pk]), self.data(title="Boshqa sarlavha", institution=str(self.s1.pk)))  # the admin completes/corrects it
        self.step(self.ca, a, "publish")
        a.refresh_from_db()
        self.assertEqual(a.status, "submitted")  # the preview showed the old text: refused
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        a.refresh_from_db()
        self.assertEqual(a.status, "published")

    def test_save_as_draft_keeps_it_private_and_it_can_be_published_later(self):
        a = self.submitted()
        self.assertEqual(self.step(self.ca, a, "save_draft").status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, "prepared")
        self.assertEqual(Client().get(reverse("achievements_public:detail", args=[a.slug])).status_code, 404)
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        a.refresh_from_db()
        self.assertEqual(a.status, "published")

    def test_request_changes_needs_a_comment_and_returns_it_to_the_school(self):
        a = self.submitted()
        self.step(self.ca, a, "request_changes", comment="")
        a.refresh_from_db()
        self.assertEqual(a.status, "submitted")
        self.step(self.ca, a, "request_changes", comment="Rasmni almashtiring")
        a.refresh_from_db()
        self.assertEqual(a.status, "changes_requested")
        self.assertTrue(Notification.objects.filter(user=self.d1, achievement=a, kind="achievement_returned").exists())
        body = self.c1.get(reverse("achievements:detail", args=[a.pk])).content.decode()
        self.assertIn("Rasmni almashtiring", body)  # the author sees the comment
        self.assertEqual(self.c1.get(reverse("achievements:edit", args=[a.pk])).status_code, 200)

    def test_unpublish_archive_restore(self):
        a = self.submitted()
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        self.step(self.ca, a, "unpublish")
        a.refresh_from_db()
        self.assertEqual(a.status, "prepared")
        self.step(self.ca, a, "archive")
        a.refresh_from_db()
        self.assertEqual(a.status, "archived")
        self.step(self.ca, a, "restore")
        a.refresh_from_db()
        self.assertEqual(a.status, "prepared")
        self.assertEqual(a.reviews.count(), 5)  # submit, publish, unpublish, archive, restore: an append-only history
        self.assertEqual(Achievement.objects.published().count(), 0)

    def test_published_state_requires_a_date_in_the_database(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Achievement.objects.create(institution=self.s1, title="x", person_name="y", status="published")

    # ---- the public site -------------------------------------------------------------------------------------
    def test_public_pages_show_only_published_and_images_follow_the_same_rule(self):
        a = self.create()
        self.c1.post(reverse("achievements:edit", args=[a.pk]), self.data(new_images=[f("a.png", png())]))
        self.step(self.c1, a, "submit")
        im = a.images.first()
        anon = Client()
        self.assertNotIn(a.title, anon.get(reverse("achievements_public:list")).content.decode())
        self.assertEqual(anon.get(reverse("achievements_public:detail", args=[a.slug])).status_code, 404)
        self.assertEqual(anon.get(reverse("achievements_public:image", args=[im.pk])).status_code, 404)
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        self.assertIn(a.title, anon.get(reverse("achievements_public:list")).content.decode())
        detail = anon.get(reverse("achievements_public:detail", args=[a.slug]))
        self.assertContains(detail, "Karimov Vali")
        r = anon.get(reverse("achievements_public:image", args=[im.pk]))
        self.assertEqual((r.status_code, r["Content-Type"], r["X-Content-Type-Options"]), (200, "image/jpeg", "nosniff"))
        self.assertIn(a.title, anon.get(reverse("content:home")).content.decode())  # the home page shows it too

    def test_preview_is_what_the_public_sees(self):
        a = self.submitted()
        pv = self.ca.get(reverse("achievements:preview", args=[a.pk])).content.decode()
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        pub = Client().get(reverse("achievements_public:detail", args=[a.slug])).content.decode()
        strip = lambda h: re.sub(r"\s+", " ", re.search(r"<h1>.*?</h1>.*?(?=</article>|<div class=\"row wrap\" style=\"margin-top:20px\">)", h, re.S).group(0))
        self.assertEqual(strip(pv), strip(pub))

    def test_description_is_escaped(self):
        a = self.create(description="<script>alert(1)</script>")
        self.step(self.c1, a, "submit")
        self.ca.get(reverse("achievements:preview", args=[a.pk]))
        self.step(self.ca, a, "publish")
        body = Client().get(reverse("achievements_public:detail", args=[a.slug])).content.decode()
        self.assertNotIn("<script>alert(1)</script>", body)

    def test_a_director_without_an_institution_cannot_send(self):
        from apps.organization.models import Employee

        Employee.objects.filter(user=self.d1).update(institution=None)
        self.assertEqual(self.c1.get(reverse("achievements:create")).status_code, 403)

    def test_other_roles_have_no_access(self):
        w = make_user("worker", role="employee")
        c = Client()
        login_with_two_factor(c, w)
        for name in ("achievements:list", "achievements:create"):
            self.assertEqual(c.get(reverse(name)).status_code, 403, name)


@override_settings(DOCUMENT_SCAN_MODE="disabled")
class AchievementLanguageTests(TestCase):
    """Every achievement page speaks Russian and English: no Uzbek interface text (the Uzbek apostrophes are the tell-tale)."""

    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        call_command("seed_roles", verbosity=0)
        admin = make_user("boss", role="admin")
        school = Institution.objects.create(name="School 1", kind="school")
        d = services.create_user(admin, username="dir1", email="d1@example.test", first_name="Dir", last_name="One", role="school_director", department=None, institution=school, request=None)
        a = Achievement.objects.create(institution=school, created_by=d, title="Olympiad", person_name="Ivan Petrov", status="submitted", consent_confirmed=True, level="republic")
        from django.core.files.base import ContentFile

        im = AchievementImage(achievement=a)
        im.file.save(new_storage_name("jpg"), ContentFile(png((40, 40))), save=False)
        im.save()
        pub = Achievement.objects.create(institution=school, created_by=d, title="Medalist", person_name="Anna", status="published", consent_confirmed=True, publish_at=a.created_at)
        for lang in ("ru", "en"):
            c = Client()
            login_with_two_factor(c, admin)
            c.cookies["django_language"] = lang
            pages = [reverse("achievements:list"), reverse("achievements:create"), reverse("achievements:detail", args=[a.pk]), reverse("achievements:edit", args=[a.pk]),
                     reverse("achievements:preview", args=[a.pk]), reverse("achievements_public:list"), reverse("achievements_public:detail", args=[pub.slug]), reverse("notifications:list")]
            for url in pages:
                body = re.sub(r'<form class="lang-switch".*?</form>', "", c.get(url).content.decode(), flags=re.S)  # "O‘zbekcha" is a language's own name
                self.assertNotIn("‘", body, (lang, url))
                self.assertNotIn("’", body, (lang, url))
