"""Public appeals: form rules, spam guards, status look-up by code + phone tail, and the portal side (who may read / answer)."""
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user

from .models import Appeal

GOOD = {"full_name": "Karimov Anvar", "phone": "+998 90 123 45 67", "email": "", "subject": "general", "message": "Maktab hovlisi haqida savolim bor, javob bering."}


class PublicAppealTests(TestCase):
    def setUp(self):
        cache.clear()
        self.c = Client()

    def test_form_page_opens_without_login(self):
        self.assertEqual(self.c.get(reverse("appeals:create")).status_code, 200)

    def test_valid_appeal_is_saved_and_code_shown(self):
        r = self.c.post(reverse("appeals:create"), GOOD)
        self.assertEqual(r.status_code, 200)
        a = Appeal.objects.get()
        self.assertTrue(a.code.startswith("M-") and len(a.code) == 10)
        self.assertContains(r, a.code)
        self.assertEqual(a.status, "new")

    def test_invalid_input_is_refused(self):
        for bad in ({**GOOD, "phone": "abc"}, {**GOOD, "full_name": "A"}, {**GOOD, "message": "qisqa"}):
            r = self.c.post(reverse("appeals:create"), bad)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.context["form"].errors)
        self.assertEqual(Appeal.objects.count(), 0)

    def test_honeypot_blocks_bots(self):
        r = self.c.post(reverse("appeals:create"), {**GOOD, "website": "http://spam.example"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Appeal.objects.count(), 0)

    def test_send_rate_limit(self):
        for _i in range(5):
            self.assertEqual(self.c.post(reverse("appeals:create"), GOOD).status_code, 200)
        self.assertEqual(self.c.post(reverse("appeals:create"), GOOD).status_code, 429)
        self.assertEqual(Appeal.objects.count(), 5)

    def test_status_needs_code_and_phone_tail(self):
        a = Appeal.objects.create(full_name="X Y Z", phone="+998 90 123 45 67", message="Savol matni bu yerda", answer="Javob matni", status="answered")
        ok = self.c.post(reverse("appeals:status"), {"code": a.code.lower(), "phone_tail": "4567"})
        self.assertContains(ok, "Javob matni")
        wrong_tail = self.c.post(reverse("appeals:status"), {"code": a.code, "phone_tail": "0000"})
        wrong_code = self.c.post(reverse("appeals:status"), {"code": "M-NOSUCH99", "phone_tail": "4567"})
        self.assertNotContains(wrong_tail, "Javob matni")
        self.assertEqual(wrong_tail.context["form"].non_field_errors(), wrong_code.context["form"].non_field_errors())  # nothing reveals which codes exist

    def test_status_lookup_rate_limit(self):
        for _i in range(10):
            self.c.post(reverse("appeals:status"), {"code": "M-AAAAAAAA", "phone_tail": "1111"})
        self.assertEqual(self.c.post(reverse("appeals:status"), {"code": "M-AAAAAAAA", "phone_tail": "1111"}).status_code, 429)


class PortalAppealTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command("seed_roles", verbosity=0)
        self.appeal = Appeal.objects.create(full_name="Q W E", phone="+998 91 000 11 22", message="Murojaat matni yetarlicha uzun")

    def client_for(self, role):
        user = make_user(f"u_{role}", role="employee")
        if role != "employee":  # make_user already gives the basic employee role
            RoleAssignment.objects.create(user=user, role=Group.objects.get(name=role), scope="all")
        c = Client()
        login_with_two_factor(c, user)
        return c

    def test_admin_reads_and_answers(self):
        c = self.client_for("admin")
        self.assertContains(c.get(reverse("appeals_admin:list")), self.appeal.code)
        self.assertEqual(c.get(reverse("appeals_admin:detail", args=[self.appeal.pk])).status_code, 200)
        self.appeal.refresh_from_db()
        self.assertEqual(self.appeal.status, "in_progress")  # opening takes it into work
        c.post(reverse("appeals_admin:detail", args=[self.appeal.pk]), {"status": "answered", "answer": "Rahmat, hal qilindi."})
        self.appeal.refresh_from_db()
        self.assertEqual((self.appeal.status, self.appeal.answer), ("answered", "Rahmat, hal qilindi."))
        self.assertIsNotNone(self.appeal.answered_by)

    def test_answer_text_is_required_for_final_status(self):
        c = self.client_for("admin")
        r = c.post(reverse("appeals_admin:detail", args=[self.appeal.pk]), {"status": "answered", "answer": " "})
        self.assertTrue(r.context["form"].errors)

    def test_roles_without_permission_get_403(self):
        for role in ("employee", "hr", "news_author"):
            c = self.client_for(role)
            self.assertEqual(c.get(reverse("appeals_admin:list")).status_code, 403, role)
            self.assertEqual(c.post(reverse("appeals_admin:detail", args=[self.appeal.pk]), {"status": "answered", "answer": "x"}).status_code, 403, role)

    def test_anonymous_is_sent_to_sign_in(self):
        r = Client().get(reverse("appeals_admin:list"))
        self.assertEqual(r.status_code, 302)
