"""Public directory pages: institutions, staff on the site, search; privacy of the staff photo."""
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.acceptance import new_storage_name
from apps.organization.models import Department, Employee, Institution, Position

JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300") + b"\x00" * 60 + b"\xff\xd9"


class DirectoryTests(TestCase):
    def setUp(self):
        self.c = Client()
        self.pub = Institution.objects.create(name="1-sonli maktab", kind="school", is_published=True, address="Markaziy ko‘cha 1")
        self.hidden = Institution.objects.create(name="Yopiq muassasa", kind="school", is_published=False)
        dept = Department.objects.create(name="D")
        pos = Position.objects.create(name="Matematika o‘qituvchisi")
        self.shown = Employee.objects.create(last_name="Aliyev", first_name="Jasur", department=dept, position=pos, institution=self.pub, status="active", show_on_site=True)
        self.shown.photo.save(new_storage_name("jpg"), ContentFile(JPEG), save=True)
        self.private = Employee.objects.create(last_name="Gizli", first_name="Odam", department=dept, institution=self.pub, status="active", show_on_site=False)
        self.private.photo.save(new_storage_name("jpg"), ContentFile(JPEG), save=True)

    def test_only_published_institutions_are_listed(self):
        r = self.c.get(reverse("content:institutions"))
        self.assertContains(r, "1-sonli maktab")
        self.assertNotContains(r, "Yopiq muassasa")
        self.assertEqual(self.c.get(reverse("content:institution", args=[self.hidden.pk])).status_code, 404)
        self.assertEqual(self.c.get(reverse("content:institution", args=[self.pub.pk])).status_code, 200)

    def test_institution_filters(self):
        self.assertNotContains(self.c.get(reverse("content:institutions"), {"q": "zzz"}), "1-sonli maktab")
        self.assertContains(self.c.get(reverse("content:institutions"), {"q": "Markaziy"}), "1-sonli maktab")
        self.assertContains(self.c.get(reverse("content:institutions"), {"kind": "school"}), "1-sonli maktab")

    def test_only_marked_staff_appear_with_public_photo(self):
        r = self.c.get(reverse("content:teachers"))
        self.assertContains(r, "Aliyev")
        self.assertNotContains(r, "Gizli")
        self.assertEqual(self.c.get(reverse("content:teacher_photo", args=[self.shown.pk])).status_code, 200)
        self.assertEqual(self.c.get(reverse("content:teacher_photo", args=[self.private.pk])).status_code, 404)

    def test_archived_person_disappears(self):
        Employee.objects.filter(pk=self.shown.pk).update(status="archived")
        self.assertNotContains(self.c.get(reverse("content:teachers")), "Aliyev")
        self.assertEqual(self.c.get(reverse("content:teacher_photo", args=[self.shown.pk])).status_code, 404)

    def test_teacher_filter_ignores_garbage(self):
        self.assertEqual(self.c.get(reverse("content:teachers"), {"inst": "'; drop"}).status_code, 200)

    def test_search(self):
        r = self.c.get(reverse("content:search"), {"q": "maktab"})
        self.assertContains(r, "1-sonli maktab")
        self.assertNotContains(r, "Yopiq")
        self.assertContains(self.c.get(reverse("content:search"), {"q": "Aliyev"}), "Aliyev")
        self.assertContains(self.c.get(reverse("content:search"), {"q": "Gizli"}), "Hech narsa topilmadi")  # the typed word is echoed in the box; no result card exists
        self.assertEqual(self.c.get(reverse("content:search"), {"q": "a"}).status_code, 200)
