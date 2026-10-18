import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts import services
from apps.accounts.testing import login_with_two_factor, make_user

from .models import Department, Employee, Institution


def url(name, *args):
    return reverse(f"employees:{name}", args=args)


def image_bytes(fmt="PNG", size=(900, 600), color=(200, 30, 30), **save):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt, **save)
    return out.getvalue()


def upload(name, data, ctype):
    return SimpleUploadedFile(name, data, content_type=ctype)


@override_settings(DOCUMENT_SCAN_MODE="disabled")
class PhotoTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.hr = make_user("hrista", role="hr")
        self.worker = make_user("worker", role="employee")
        self.dept = Department.objects.create(name="Bo‘lim")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        self.emp = Employee.objects.create(last_name="Karimov", first_name="A", department=self.dept, institution=self.s1, status="active")
        self.hr_client = self.client_for(self.hr)

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def form(self, **extra):
        data = {"last_name": "Karimov", "first_name": "A", "middle_name": "", "department": str(self.dept.pk), "position": "",
                "institution": str(self.s1.pk), "status": "active"}
        data.update(extra)
        return data

    def put(self, name, data, ctype, **extra):
        return self.hr_client.post(url("edit", self.emp.pk), self.form(photo_upload=upload(name, data, ctype), **extra))

    def test_png_is_reencoded_to_small_jpeg_in_private_storage(self):
        r = self.put("me.png", image_bytes(), "image/png")
        self.assertEqual(r.status_code, 302)
        self.emp.refresh_from_db()
        self.assertTrue(self.emp.photo.name.endswith(".jpg"))
        self.assertNotIn("me", self.emp.photo.name)  # random name, never the client's
        with self.emp.photo.storage.open(self.emp.photo.name, "rb") as fh:
            stored = Image.open(io.BytesIO(fh.read()))
        self.assertEqual((stored.format, stored.size), ("JPEG", (512, 512)))
        with self.assertRaises(ValueError):
            self.emp.photo.url  # no public address

    def test_exif_metadata_is_dropped(self):
        exif = Image.Exif()
        exif[0x010F] = "SecretCamera"
        out = io.BytesIO()
        Image.new("RGB", (300, 300), (1, 2, 3)).save(out, "JPEG", exif=exif)
        self.assertEqual(self.put("p.jpg", out.getvalue(), "image/jpeg").status_code, 302)
        self.emp.refresh_from_db()
        with self.emp.photo.storage.open(self.emp.photo.name, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"SecretCamera", raw)
        self.assertEqual(len(Image.open(io.BytesIO(raw)).getexif()), 0)

    def test_non_images_and_active_content_are_refused(self):
        for name, data, ctype in (
            ("a.txt", b"hello", "text/plain"),
            ("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
            ("a.png", b"<html>not a png</html>", "image/png"),
            ("a.pdf", b"%PDF-1.4 x", "application/pdf"),
        ):
            r = self.put(name, data, ctype)
            self.assertEqual(r.status_code, 200, name)  # form re-shown with an error
            self.emp.refresh_from_db()
            self.assertFalse(self.emp.photo, name)

    def test_too_large_file_is_refused(self):
        big = image_bytes("BMP", size=(100, 100))  # content irrelevant, size check comes first
        r = self.put("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 1), "image/png")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Employee.objects.get(pk=self.emp.pk).photo)
        self.assertTrue(big)

    def test_photo_view_serves_jpeg_privately_and_only_to_the_directory_audience(self):
        self.put("me.png", image_bytes(), "image/png")
        r = self.hr_client.get(url("photo", self.emp.pk))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", r["Cache-Control"])
        self.assertEqual(Client().get(url("photo", self.emp.pk)).status_code, 302)  # anonymous -> login
        # a director of ANOTHER institution must not get it
        services.create_user(make_user("boss", role="admin"), username="dir2", email="d2@example.test", first_name="D", last_name="D",
                             role="school_director", department=None, institution=self.s2, request=None)
        from django.contrib.auth import get_user_model

        other = self.client_for(get_user_model().objects.get(username="dir2"))
        self.assertEqual(other.get(url("photo", self.emp.pk)).status_code, 404)
        dir1 = services.create_user(make_user("boss2", role="admin"), username="dir1", email="d1@example.test", first_name="D", last_name="E",
                                    role="school_director", department=None, institution=self.s1, request=None)
        self.assertEqual(self.client_for(dir1).get(url("photo", self.emp.pk)).status_code, 200)

    def test_no_photo_is_404_and_list_shows_img_only_with_photo(self):
        self.assertEqual(self.hr_client.get(url("photo", self.emp.pk)).status_code, 404)
        self.assertNotContains(self.hr_client.get(url("list")), "/photo/")
        self.put("me.png", image_bytes(), "image/png")
        self.assertContains(self.hr_client.get(url("list")), url("photo", self.emp.pk))

    def test_replace_and_clear_delete_the_old_file(self):
        self.put("a.png", image_bytes(), "image/png")
        self.emp.refresh_from_db()
        first = self.emp.photo.name
        self.put("b.png", image_bytes(color=(0, 200, 0)), "image/png")
        self.emp.refresh_from_db()
        second = self.emp.photo.name
        self.assertNotEqual(first, second)
        self.assertFalse(self.emp.photo.storage.exists(first))
        r = self.hr_client.post(url("edit", self.emp.pk), self.form(photo_clear="on"))
        self.assertEqual(r.status_code, 302)
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.photo)
        self.assertFalse(self.emp.photo.storage.exists(second))
