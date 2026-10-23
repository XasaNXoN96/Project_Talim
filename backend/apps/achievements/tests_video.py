import struct

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts import services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.documents.tests_scanner import FakeClamd, scanning
from apps.organization.models import Institution

from . import videos
from .models import Achievement, AchievementVideo

GPS = b"\xa9xyz+41.2345+069.1234/ iPhone secret location"


def box(kind, payload=b""):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mp4(*, udta=True, meta=False, mdat=b"V" * 400, brand=b"isom"):
    moov = box(b"mvhd", b"\0" * 20)
    if udta:
        moov += box(b"udta", box(b"\xa9xyz", GPS))
    if meta:
        moov += box(b"meta", b"\0\0\0\0" + box(b"keys", b"com.apple.quicktime.location.ISO6709"))
    ftyp = box(b"ftyp", brand + b"\0\0\0\0" + brand)
    return ftyp + box(b"moov", moov) + box(b"mdat", mdat)


def webm():
    return b"\x1a\x45\xdf\xa3" + b"\x93\x42\x82\x84webm" + b"\x00" * 200


def up(name, data, ctype="video/mp4"):
    return SimpleUploadedFile(name, data, content_type=ctype)


@override_settings(DOCUMENT_SCAN_MODE="disabled")
class VideoUploadTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.s1, self.s2 = Institution.objects.create(name="1-maktab", kind="school"), Institution.objects.create(name="2-maktab", kind="school")
        mk = lambda n, i: services.create_user(self.admin, username=n, email=f"{n}@example.test", first_name=n, last_name="D", role="school_director", department=None, institution=i, request=None)
        self.d1, self.d2 = mk("dir1", self.s1), mk("dir2", self.s2)
        self.c1, self.c2, self.ca = Client(), Client(), Client()
        for c, u in ((self.c1, self.d1), (self.c2, self.d2), (self.ca, self.admin)):
            login_with_two_factor(c, u)
        r = self.c1.post(reverse("achievements:create"), self.data())
        self.a = Achievement.objects.get()

    def data(self, **extra):
        d = {"kind": "medal", "title": "Olimpiada", "person_kind": "teacher", "person_name": "Karimov", "person_position": "", "level": "republic",
             "awarded_on": "2026-05-01", "description": "T", "video_url": "", "consent_confirmed": "on"}
        d.update(extra)
        return d

    def put(self, name, data, ctype="video/mp4", client=None, **extra):
        return (client or self.c1).post(reverse("achievements:edit", args=[self.a.pk]), self.data(new_video=up(name, data, ctype), **extra))

    def reasons(self):
        return [a.meta.get("reason") for a in AuditLog.objects.filter(action="document_upload_rejected")]

    # ---- what is accepted ---------------------------------------------------------------------------------------
    def test_mp4_is_stored_privately_and_the_camera_position_is_wiped_in_place(self):
        raw = mp4(meta=True)
        self.assertEqual(self.put("holiday.MP4", raw).status_code, 302)
        v = AchievementVideo.objects.get(achievement=self.a)
        self.assertEqual((v.content_type, v.size), ("video/mp4", len(raw)))
        self.assertTrue(v.file.name.endswith(".mp4"))
        self.assertNotIn("holiday", v.file.name)  # a random name, never the client's
        with self.assertRaises(ValueError):
            v.file.url
        with v.file.storage.open(v.file.name, "rb") as fh:
            stored = fh.read()
        self.assertEqual(len(stored), len(raw))  # same length: no offset moved
        self.assertNotIn(b"iPhone secret location", stored)
        self.assertNotIn(b"ISO6709", stored)
        self.assertNotIn(b"udta", stored)
        self.assertIn(b"free", stored)
        self.assertEqual(stored[-400:], b"V" * 400)  # the media data is untouched
        videos.check_mp4_structure(stored)  # still a well-formed file

    def test_webm_is_accepted(self):
        self.assertEqual(self.put("clip.webm", webm(), "video/webm").status_code, 302)
        self.assertEqual(AchievementVideo.objects.get().content_type, "video/webm")

    def test_a_new_video_replaces_the_old_one_and_the_old_file_is_erased(self):
        self.put("a.mp4", mp4())
        first = AchievementVideo.objects.get()
        old = first.file.name
        self.put("b.mp4", mp4(mdat=b"W" * 300))
        self.assertEqual(AchievementVideo.objects.count(), 1)
        v = AchievementVideo.objects.get()
        self.assertNotEqual(v.file.name, old)
        self.assertFalse(v.file.storage.exists(old))

    def test_removing_the_video_erases_the_file(self):
        self.put("a.mp4", mp4())
        v = AchievementVideo.objects.get()
        name = v.file.name
        r = self.c1.post(reverse("achievements:edit", args=[self.a.pk]), self.data(remove_video="on"))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AchievementVideo.objects.exists())
        self.assertFalse(v.file.storage.exists(name))

    def test_a_video_invalidates_a_preview_taken_before_it(self):
        from . import workflow

        self.c1.post(reverse("achievements:step", args=[self.a.pk, "submit"]))
        self.a.refresh_from_db()
        before = workflow.version_token(self.a)
        self.put("a.mp4", mp4(), client=self.ca, institution=str(self.s1.pk))
        self.a.refresh_from_db()
        self.assertNotEqual(before, workflow.version_token(self.a))

    # ---- what is refused ----------------------------------------------------------------------------------------
    def test_refusals(self):
        cases = {
            "bad_extension": [("clip.exe", mp4()), ("clip.txt", b"hello"), ("clip", mp4()), ("clip.mp4.exe", mp4())],
            "content_mismatch": [("clip.mp4", webm()), ("clip.webm", mp4()), ("clip.mp4", b"MZ\x90\x00" + b"\0" * 200), ("clip.mp4", b"<html>x</html>"), ("clip.mp4", mp4(brand=b"zzzz"))],
            "corrupt": [("clip.mp4", mp4()[:-50]), ("clip.mp4", box(b"ftyp", b"isom\0\0\0\0isom") + box(b"mdat", b"x" * 50))],
        }
        for reason, items in cases.items():
            for name, data in items:
                r = self.put(name, data)
                self.assertEqual(r.status_code, 200, (reason, name))  # the form comes back with an error
        self.assertFalse(AchievementVideo.objects.exists())
        got = self.reasons()
        for reason in cases:
            self.assertIn(reason, got)

    @override_settings(ACHIEVEMENT_VIDEO_MAX_BYTES=600)
    def test_too_large(self):
        self.assertEqual(self.put("a.mp4", mp4(mdat=b"V" * 2000)).status_code, 200)
        self.assertFalse(AchievementVideo.objects.exists())
        self.assertIn("too_large", self.reasons())

    def test_a_truncated_structure_inside_moov_is_refused_when_wiping(self):
        bad = box(b"ftyp", b"isom\0\0\0\0isom") + struct.pack(">I4s", 200, b"moov") + b"\0" * 10 + box(b"mdat", b"x")
        self.assertEqual(self.put("a.mp4", bad).status_code, 200)

    def test_other_schools_and_roles_cannot_attach_to_this_achievement(self):
        self.assertEqual(self.put("a.mp4", mp4(), client=self.c2).status_code, 404)
        self.assertFalse(AchievementVideo.objects.exists())

    # ---- antivirus ----------------------------------------------------------------------------------------------
    def test_antivirus_verdicts(self):
        for behaviour, expected_reason in (("found", "malware"), ("hangup", "scan_unavailable"), ("garbage", "scan_error")):
            fake = FakeClamd(behaviour).start()
            try:
                with scanning(fake):
                    r = self.put("a.mp4", mp4())
            finally:
                fake.stop()
            self.assertEqual(r.status_code, 200, behaviour)
            self.assertFalse(AchievementVideo.objects.exists(), behaviour)
            self.assertIn(expected_reason, self.reasons(), behaviour)
        self.assertTrue(AuditLog.objects.filter(action="file_threat_detected").exists())
        fake = FakeClamd("ok").start()
        try:
            with scanning(fake):
                self.assertEqual(self.put("a.mp4", mp4()).status_code, 302)
        finally:
            fake.stop()
        self.assertEqual(AchievementVideo.objects.get().scan_status, "clean")

    # ---- serving ------------------------------------------------------------------------------------------------
    def publish(self):
        self.c1.post(reverse("achievements:step", args=[self.a.pk, "submit"]))
        self.ca.get(reverse("achievements:preview", args=[self.a.pk]))
        self.ca.post(reverse("achievements:step", args=[self.a.pk, "publish"]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "published")

    def test_ranges_and_headers(self):
        self.put("a.mp4", mp4())
        v = AchievementVideo.objects.get()
        url = reverse("achievements:video", args=[v.pk])
        with v.file.storage.open(v.file.name, "rb") as fh:
            blob = fh.read()
        r = self.c1.get(url)
        self.assertEqual((r.status_code, r["Content-Type"], r["Accept-Ranges"], r["X-Content-Type-Options"]), (200, "video/mp4", "bytes", "nosniff"))
        self.assertEqual(b"".join(r.streaming_content), blob)
        self.assertIn("private", r["Cache-Control"])
        r = self.c1.get(url, HTTP_RANGE="bytes=0-9")
        self.assertEqual((r.status_code, r["Content-Range"], r["Content-Length"]), (206, f"bytes 0-9/{len(blob)}", "10"))
        self.assertEqual(b"".join(r.streaming_content), blob[:10])
        r = self.c1.get(url, HTTP_RANGE="bytes=-5")
        self.assertEqual(b"".join(r.streaming_content), blob[-5:])
        r = self.c1.get(url, HTTP_RANGE=f"bytes={len(blob) - 3}-")
        self.assertEqual(b"".join(r.streaming_content), blob[-3:])
        r = self.c1.get(url, HTTP_RANGE="bytes=0-99999999")
        self.assertEqual((r.status_code, int(r["Content-Length"])), (206, len(blob)))
        for bad in (f"bytes={len(blob)}-", "bytes=5-2", "bytes=abc", "bytes=-0", "bytes=-", "items=0-5"):
            r = self.c1.get(url, HTTP_RANGE=bad)
            self.assertEqual((r.status_code, r["Content-Range"]), (416, f"bytes */{len(blob)}"), bad)

    def test_who_can_fetch_the_portal_video(self):
        self.put("a.mp4", mp4())
        v = AchievementVideo.objects.get()
        url = reverse("achievements:video", args=[v.pk])
        self.assertEqual(self.c1.get(url).status_code, 200)  # its own school
        self.assertEqual(self.c2.get(url).status_code, 404)  # another school
        self.assertEqual(self.ca.get(url).status_code, 404)  # an unsent draft is not for the administrator either
        self.assertEqual(Client().get(url).status_code, 302)  # anonymous: sign in
        self.c1.post(reverse("achievements:step", args=[self.a.pk, "submit"]))
        self.assertEqual(self.ca.get(url).status_code, 200)

    def test_the_public_video_exists_only_once_published(self):
        self.put("a.mp4", mp4())
        v = AchievementVideo.objects.get()
        public = reverse("achievements_public:video", args=[v.pk])
        anon = Client()
        self.assertEqual(anon.get(public).status_code, 404)
        self.publish()
        r = anon.get(public)
        self.assertEqual((r.status_code, r["Content-Type"], r["Accept-Ranges"]), (200, "video/mp4", "bytes"))
        self.assertIn("public", r["Cache-Control"])
        self.assertEqual(anon.get(public, HTTP_RANGE="bytes=0-3").status_code, 206)
        page = anon.get(reverse("achievements_public:detail", args=[self.a.slug])).content.decode()
        self.assertIn("<video", page)
        self.assertIn(public, page)
        self.ca.post(reverse("achievements:step", args=[self.a.pk, "unpublish"]))
        self.assertEqual(anon.get(public).status_code, 404)  # taken down: the file is gone from the public site at once

    def test_the_preview_plays_the_video_through_the_portal_route(self):
        self.put("a.mp4", mp4())
        v = AchievementVideo.objects.get()
        self.c1.post(reverse("achievements:step", args=[self.a.pk, "submit"]))
        body = self.ca.get(reverse("achievements:preview", args=[self.a.pk])).content.decode()
        self.assertIn(reverse("achievements:video", args=[v.pk]), body)
        self.assertNotIn(reverse("achievements_public:video", args=[v.pk]), body)

    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        import re

        self.put("a.mp4", mp4())
        self.c1.get(reverse("achievements:detail", args=[self.a.pk]))  # shows (and clears) the one-off "saved" messages, written in the language of the POST
        for lang in ("ru", "en"):
            self.ca.cookies["django_language"] = lang
            self.c1.cookies["django_language"] = lang
            for page in (reverse("achievements:edit", args=[self.a.pk]), reverse("achievements:detail", args=[self.a.pk])):
                html = re.sub(r'<form class="lang-switch".*?</form>', "", self.c1.get(page).content.decode(), flags=re.S)
                html = re.sub(r"1-maktab|Olimpiada|Karimov", "", html)
                self.assertNotIn("‘", html, (lang, page))
                self.assertNotIn("’", html, (lang, page))
