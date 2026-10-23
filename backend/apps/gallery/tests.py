import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts import services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.achievements.tests_video import GPS, mp4, webm
from apps.audit.models import AuditLog
from apps.organization.models import Institution

from .models import MediaItem


def png(size=(1800, 1200), color=(30, 90, 160)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def up(name, data, ctype="image/png"):
    return SimpleUploadedFile(name, data, content_type=ctype)


@override_settings(DOCUMENT_SCAN_MODE="disabled")
class GalleryTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.cm = make_user("content", role="content_manager")
        self.worker = make_user("worker", role="employee")
        self.sys = make_user("sysadm", role="sysadmin")
        self.school = Institution.objects.create(name="1-maktab", kind="school")
        self.director = services.create_user(self.admin, username="dir1", email="d1@example.test", first_name="D", last_name="D", role="school_director", department=None, institution=self.school, request=None)
        self.c = {u.username: self.client_for(u) for u in (self.admin, self.cm, self.worker, self.sys, self.director)}
        self.anon = Client()

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def upload_photos(self, who="boss", n=2, **extra):
        data = {"files": [up(f"p{i}.png", png((1800 + i, 1200))) for i in range(n)], "title": "Tadbir", "institution": "", "taken_on": "", "consent_confirmed": "on"}
        data.update(extra)
        return self.c[who].post(reverse("gallery:upload_photos"), data)

    def publish_all(self):
        ids = [str(i.pk) for i in MediaItem.objects.filter(status="draft")]
        return self.c["boss"].post(reverse("gallery:bulk"), {"action": "publish", "ids": ids})

    # ---- photos ---------------------------------------------------------------------------------------------------
    def test_photos_are_stored_as_a_full_jpeg_and_a_thumbnail_in_private_storage(self):
        self.assertEqual(self.upload_photos(n=3).status_code, 302)
        items = list(MediaItem.objects.all())
        self.assertEqual(len(items), 3)
        for m in items:
            self.assertEqual((m.kind, m.status, m.content_type, m.title), ("photo", "draft", "image/jpeg", "Tadbir"))
            self.assertTrue(m.consent_confirmed)
            self.assertNotIn("p0", m.file.name)  # random names, never the client's
            with m.file.storage.open(m.file.name, "rb") as fh:
                full = Image.open(io.BytesIO(fh.read()))
            with m.thumb.storage.open(m.thumb.name, "rb") as fh:
                thumb = Image.open(io.BytesIO(fh.read()))
            self.assertEqual((full.format, max(full.size)), ("JPEG", 1600))
            self.assertEqual((thumb.format, max(thumb.size)), ("JPEG", 480))
            with self.assertRaises(ValueError):
                m.file.url
        log = AuditLog.objects.get(action="media_uploaded")
        self.assertEqual((log.meta["kind"], log.meta["count"]), ("photo", 3))

    def test_one_bad_file_refuses_the_whole_batch_and_saves_nothing(self):
        r = self.c["boss"].post(reverse("gallery:upload_photos"), {"files": [up("a.png", png((300, 300))), up("b.svg", b"<svg><script>1</script></svg>", "image/svg+xml")], "title": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MediaItem.objects.count(), 0)
        r = self.c["boss"].post(reverse("gallery:upload_photos"), {"files": [up(f"{i}.png", png((50, 50))) for i in range(13)], "title": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MediaItem.objects.count(), 0)
        self.assertEqual(self.c["boss"].post(reverse("gallery:upload_photos"), {"title": "x"}).status_code, 200)  # no file at all

    # ---- videos ---------------------------------------------------------------------------------------------------
    def test_video_is_checked_wiped_of_gps_and_needs_a_title(self):
        r = self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(), "video/mp4"), "title": "", "consent_confirmed": "on"})
        self.assertEqual(r.status_code, 200)  # a video needs a title
        r = self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(meta=True), "video/mp4"), "title": "Konsert", "consent_confirmed": "on"})
        self.assertEqual(r.status_code, 302)
        m = MediaItem.objects.get()
        self.assertEqual((m.kind, m.content_type, m.status), ("video", "video/mp4", "draft"))
        with m.file.storage.open(m.file.name, "rb") as fh:
            stored = fh.read()
        self.assertNotIn(b"iPhone secret location", stored)
        self.assertNotIn(b"ISO6709", stored)
        for name, data, ctype in (("v.exe", mp4(), "video/mp4"), ("v.mp4", webm(), "video/webm"), ("v.mp4", mp4()[:-30], "video/mp4")):
            self.c["boss"].post(reverse("gallery:upload_video"), {"file": up(name, data, ctype), "title": "x"})
        self.assertEqual(MediaItem.objects.count(), 1)

    @override_settings(MEDIA_VIDEO_MAX_BYTES=600)
    def test_video_size_cap(self):
        r = self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(mdat=b"V" * 3000), "video/mp4"), "title": "Katta"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MediaItem.objects.count(), 0)

    def test_webm_works(self):
        self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.webm", webm(), "video/webm"), "title": "Klip"})
        self.assertEqual(MediaItem.objects.get().content_type, "video/webm")

    # ---- publishing -----------------------------------------------------------------------------------------------
    def test_publishing_needs_the_consent_and_is_done_in_bulk(self):
        self.upload_photos(n=2, consent_confirmed="")
        self.assertEqual(MediaItem.objects.filter(consent_confirmed=True).count(), 0)
        r = self.publish_all()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(MediaItem.objects.published().count(), 0)  # skipped: no consent
        first = MediaItem.objects.first()
        self.c["boss"].post(reverse("gallery:edit", args=[first.pk]), {"title": "Tadbir", "institution": "", "taken_on": "", "consent_confirmed": "on"})
        self.publish_all()
        self.assertEqual(MediaItem.objects.published().count(), 1)
        self.assertEqual(MediaItem.objects.published().get().pk, first.pk)
        self.assertIsNotNone(first.__class__.objects.get(pk=first.pk).publish_at)
        self.c["boss"].post(reverse("gallery:bulk"), {"action": "unpublish", "ids": [str(first.pk)]})
        self.assertEqual(MediaItem.objects.published().count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="media_changed", meta__action="publish").exists())

    def test_the_database_refuses_a_published_item_without_consent_or_date(self):
        for extra in ({"consent_confirmed": False, "publish_at": __import__("django.utils.timezone", fromlist=["now"]).now()}, {"consent_confirmed": True, "publish_at": None}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                MediaItem.objects.create(kind="photo", content_type="image/jpeg", size=1, sha256="0" * 64, status="published", **extra)

    def test_a_published_item_cannot_lose_its_consent_and_a_video_keeps_its_title(self):
        self.upload_photos(n=1)
        self.publish_all()
        m = MediaItem.objects.get()
        r = self.c["boss"].post(reverse("gallery:edit", args=[m.pk]), {"title": "x", "institution": "", "taken_on": "", "consent_confirmed": ""})
        self.assertEqual(r.status_code, 200)
        m.refresh_from_db()
        self.assertTrue(m.consent_confirmed)
        self.c["boss"].post(reverse("gallery:bulk"), {"action": "unpublish", "ids": [str(m.pk)]})
        r = self.c["boss"].post(reverse("gallery:edit", args=[m.pk]), {"title": "Yangi", "institution": str(self.school.pk), "taken_on": "2026-05-01", "consent_confirmed": ""})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual((m.title, m.institution, m.consent_confirmed), ("Yangi", self.school, False))

    # ---- who sees what --------------------------------------------------------------------------------------------
    def test_drafts_are_for_the_staff_only_and_published_items_for_everybody_with_an_account(self):
        self.upload_photos(n=1)
        m = MediaItem.objects.get()
        for who in ("worker", "dir1"):
            self.assertNotIn(reverse("gallery:file", args=[m.pk, "thumb"]), self.c[who].get(reverse("gallery:list")).content.decode(), who)
            self.assertEqual(self.c[who].get(reverse("gallery:file", args=[m.pk, "thumb"])).status_code, 404, who)
        self.assertEqual(self.anon.get(reverse("gallery_public:file", args=[m.pk, "thumb"])).status_code, 404)
        for who in ("boss", "content"):
            self.assertEqual(self.c[who].get(reverse("gallery:file", args=[m.pk, "thumb"])).status_code, 200, who)
        self.publish_all()
        for who in ("worker", "dir1", "boss"):
            r = self.c[who].get(reverse("gallery:file", args=[m.pk, "full"]))
            self.assertEqual((r.status_code, r["Content-Type"], r["X-Content-Type-Options"]), (200, "image/jpeg", "nosniff"), who)
            self.assertIn("private", r["Cache-Control"])
        r = self.anon.get(reverse("gallery_public:file", args=[m.pk, "thumb"]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/jpeg"))
        self.assertEqual(self.anon.get(reverse("gallery_public:file", args=[m.pk, "huge"])).status_code, 404)
        self.assertEqual(self.c["sysadm"].get(reverse("gallery:list")).status_code, 403)  # no right to the gallery at all

    def test_only_the_staff_can_upload_publish_edit_or_delete(self):
        self.upload_photos(n=1)
        m = MediaItem.objects.get()
        for who in ("worker", "dir1", "sysadm"):
            self.assertEqual(self.c[who].get(reverse("gallery:upload_photos")).status_code, 403, who)
            self.assertEqual(self.c[who].get(reverse("gallery:upload_video")).status_code, 403, who)
            self.assertEqual(self.c[who].post(reverse("gallery:bulk"), {"action": "publish", "ids": [str(m.pk)]}).status_code, 403, who)
            self.assertEqual(self.c[who].get(reverse("gallery:delete", args=[m.pk])).status_code, 403, who)
        self.assertEqual(self.upload_photos(who="worker").status_code, 403)
        self.assertEqual(MediaItem.objects.published().count(), 0)
        self.assertEqual(self.c["content"].get(reverse("gallery:upload_photos")).status_code, 200)  # a content manager curates too

    def test_public_pages_list_only_published_items_in_the_right_tab(self):
        self.upload_photos(n=2)
        self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(), "video/mp4"), "title": "Konsert videosi", "consent_confirmed": "on"})
        body = self.anon.get(reverse("gallery_public:list")).content.decode()
        self.assertNotIn("data-lbx", body)
        self.publish_all()
        body = self.anon.get(reverse("gallery_public:list")).content.decode()
        self.assertEqual(body.count("data-lbx"), 2)
        self.assertNotIn("Konsert videosi", body)
        video = self.anon.get(reverse("gallery_public:list"), {"type": "video"}).content.decode()
        self.assertIn("Konsert videosi", video)
        self.assertIn("<video", video)
        self.assertEqual(video.count("data-lbx"), 0)

    def test_the_public_video_supports_ranges_and_disappears_when_unpublished(self):
        self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(), "video/mp4"), "title": "Klip", "consent_confirmed": "on"})
        m = MediaItem.objects.get()
        url = reverse("gallery_public:file", args=[m.pk, "full"])
        self.assertEqual(self.anon.get(url).status_code, 404)
        self.publish_all()
        r = self.anon.get(url, HTTP_RANGE="bytes=0-9")
        self.assertEqual((r.status_code, r["Content-Range"].split("/")[0], r["Accept-Ranges"]), (206, "bytes 0-9", "bytes"))
        self.assertEqual(self.anon.get(url, HTTP_RANGE="bytes=99999999-").status_code, 416)
        self.assertEqual(self.anon.get(reverse("gallery_public:file", args=[m.pk, "thumb"])).status_code, 404)  # a video has no thumbnail
        self.c["boss"].post(reverse("gallery:bulk"), {"action": "unpublish", "ids": [str(m.pk)]})
        self.assertEqual(self.anon.get(url).status_code, 404)

    # ---- deleting -------------------------------------------------------------------------------------------------
    def test_delete_asks_first_and_then_erases_the_files_from_the_disk(self):
        self.upload_photos(n=1)
        m = MediaItem.objects.get()
        names = [(m.file.storage, m.file.name), (m.thumb.storage, m.thumb.name)]
        page = self.c["boss"].get(reverse("gallery:delete", args=[m.pk]))
        self.assertContains(page, "butunlay")
        self.assertTrue(MediaItem.objects.exists())  # a GET never deletes
        self.assertEqual(self.c["boss"].post(reverse("gallery:delete", args=[m.pk])).status_code, 302)
        self.assertFalse(MediaItem.objects.exists())
        for storage, name in names:
            self.assertFalse(storage.exists(name))
        self.assertTrue(AuditLog.objects.filter(action="media_changed", meta__action="delete").exists())
        self.assertEqual(self.c["boss"].post(reverse("gallery:delete", args=[m.pk])).status_code, 404)

    def test_bulk_ignores_garbage_ids_and_unknown_actions(self):
        self.upload_photos(n=1)
        for post in ({"action": "publish", "ids": ["x", "1"]}, {"action": "nuke", "ids": [str(MediaItem.objects.get().pk)]}, {"action": "publish"}):
            self.assertEqual(self.c["boss"].post(reverse("gallery:bulk"), post).status_code, 302)
        self.assertEqual(MediaItem.objects.published().count(), 0)
        self.assertEqual(self.c["boss"].post(reverse("gallery:bulk"), {"action": "publish", "ids": [str(MediaItem.objects.get().pk)], "next": "https://evil.example/"}).status_code, 302)
        self.assertNotIn("evil", self.c["boss"].post(reverse("gallery:bulk"), {"action": "publish", "ids": [], "next": "https://evil.example/"})["Location"])  # no open redirect

    # ---- the home page ---------------------------------------------------------------------------------------------
    def test_home_shows_real_photos_when_there_are_some_and_the_samples_otherwise(self):
        sample = self.anon.get(reverse("content:home")).content.decode()
        self.assertIn('data-ph="hall"', sample)  # the sample gallery
        self.assertIn('class="video"', sample)  # and the sample video
        self.upload_photos(n=2)
        self.c["boss"].post(reverse("gallery:upload_video"), {"file": up("v.mp4", mp4(), "video/mp4"), "title": "Tantana videosi", "consent_confirmed": "on"})
        self.publish_all()
        body = self.anon.get(reverse("content:home")).content.decode()
        self.assertEqual(body.count("data-lbx"), 2)
        self.assertNotIn('data-ph="hall"', body)
        self.assertNotIn('class="video"', body)
        self.assertIn("Tantana videosi", body)
        self.assertIn("<video", body)
        self.assertIn(reverse("gallery_public:list"), body)

    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        self.upload_photos(n=1, title="Tadbir")
        self.publish_all()
        m = MediaItem.objects.get()
        self.c["boss"].get(reverse("gallery:list"))  # shows (and clears) the one-off messages written in the language of the POSTs
        for lang in ("ru", "en"):
            c = self.c["boss"]
            c.cookies["django_language"] = lang
            self.anon.cookies["django_language"] = lang
            pages = [(c, reverse("gallery:list")), (c, reverse("gallery:list") + "?type=video"), (c, reverse("gallery:upload_photos")), (c, reverse("gallery:upload_video")),
                     (c, reverse("gallery:edit", args=[m.pk])), (c, reverse("gallery:delete", args=[m.pk])), (self.anon, reverse("gallery_public:list")), (self.anon, reverse("content:home"))]
            for client, url in pages:
                html = re.sub(r'<form class="lang-switch".*?</form>', "", client.get(url).content.decode(), flags=re.S)
                html = re.sub(r"1-maktab|Tadbir", "", html)
                if url == reverse("content:home"):
                    html = re.sub(r"<section id=\"yutuqlar\".*?</section>", "", html, flags=re.S)  # sample cards of other sections are labelled "Namuna" and out of this test
                self.assertNotIn("‘", html, (lang, url))
                self.assertNotIn("’", html, (lang, url))
