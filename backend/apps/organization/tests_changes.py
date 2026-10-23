from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.notifications.models import Notification

from . import changes
from .models import Department, Employee, EmployeeChangeRequest

S = EmployeeChangeRequest.Status


def url(name, *args):
    return reverse(f"employees:{name}", args=args)


class ChangeRequestTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.dept = Department.objects.create(name="Dept")
        self.worker = make_user("worker", role="employee")
        self.other = make_user("other", role="employee")
        self.hr = make_user("hrista", role="hr")
        self.hr2 = make_user("hrista2", role="hr")
        self.card = Employee.objects.create(last_name="Karimov", first_name="Vali", department=self.dept, user=self.worker, status="active",
                                            work_phone="+998 71 111 22 33", personal_phone="+998 90 555 66 77", birth_date="1990-05-17", work_email="v@work.example.test")
        Employee.objects.create(last_name="Hr", first_name="One", department=self.dept, user=self.hr, status="active", work_phone="+998 1")
        self.cw, self.ch, self.ch2, self.co = (self.client_for(u) for u in (self.worker, self.hr, self.hr2, self.other))

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def form(self, **extra):
        d = {"last_name": "Karimov", "first_name": "Vali", "middle_name": "", "work_phone": "+998 71 111 22 33", "work_email": "v@work.example.test",
             "personal_phone": "+998 90 555 66 77", "birth_date": "1990-05-17"}
        d.update(extra)
        return d

    def ask(self, client=None, **extra):
        return (client or self.cw).post(url("me_edit"), self.form(**extra))

    def open_request(self):
        return EmployeeChangeRequest.objects.get(employee=self.card, status=S.PENDING)

    def test_a_request_changes_nothing_until_it_is_approved(self):
        self.assertEqual(self.ask(work_phone="+998 71 999 00 00", birth_date="1991-05-17").status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.work_phone, "+998 71 111 22 33")  # unchanged
        req = self.open_request()
        self.assertEqual(sorted(req.fields), ["birth_date", "work_phone"])
        self.assertEqual(req.changes["work_phone"], "+998 71 999 00 00")
        self.assertEqual(req.old_values["birth_date"], "1990-05-17")
        self.assertTrue(Notification.objects.filter(user=self.hr, change_request=req, kind="profile_change_asked").exists())
        self.assertFalse(Notification.objects.filter(user=self.worker, change_request=req).exists())

    def test_nothing_to_change_and_invalid_values_are_refused(self):
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(self.ask(work_email="not-an-email").status_code, 200)
        self.assertEqual(self.ask(birth_date="31-31-2000").status_code, 200)
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    def test_only_the_listed_fields_can_be_asked_for(self):
        self.ask(work_phone="+998 1", department=str(self.dept.pk), position="x", status="archived", institution="x", hired_at="2000-01-01", user="1")
        req = self.open_request()
        self.assertEqual(req.fields, ["work_phone"])
        self.assertEqual(set(req.changes), {"work_phone"})

    def test_a_new_request_replaces_the_open_one(self):
        self.ask(work_phone="+998 1")
        first = self.open_request()
        self.ask(work_phone="+998 2", first_name="Valijon")
        first.refresh_from_db()
        self.assertEqual((first.status, first.changes, first.old_values), (S.CANCELLED, {}, {}))
        self.assertEqual(EmployeeChangeRequest.objects.filter(status=S.PENDING).count(), 1)
        self.assertEqual(sorted(self.open_request().fields), ["first_name", "work_phone"])

    def test_approval_applies_the_change_and_forgets_the_values(self):
        self.ask(work_phone="+998 71 999 00 00", middle_name="Aliyevich", birth_date="")
        req = self.open_request()
        self.assertEqual(self.ch.post(url("change_decide", req.pk, "approve")).status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual((self.card.work_phone, self.card.middle_name, self.card.birth_date), ("+998 71 999 00 00", "Aliyevich", None))
        req.refresh_from_db()
        self.assertEqual((req.status, req.decided_by, req.changes, req.old_values), (S.APPROVED, self.hr, {}, {}))
        self.assertEqual(sorted(req.fields), ["birth_date", "middle_name", "work_phone"])  # names stay, values do not
        self.assertTrue(Notification.objects.filter(user=self.worker, change_request=req, kind="profile_change_done").exists())
        for a in AuditLog.objects.filter(object_type="EmployeeChangeRequest"):
            self.assertNotIn("999", str(a.meta))
            self.assertNotIn("Aliyevich", str(a.meta))

    def test_rejection_needs_a_comment_and_leaves_the_card_alone(self):
        self.ask(work_phone="+998 71 999 00 00")
        req = self.open_request()
        self.ch.post(url("change_decide", req.pk, "reject"), {"comment": ""})
        req.refresh_from_db()
        self.assertEqual(req.status, S.PENDING)
        self.ch.post(url("change_decide", req.pk, "reject"), {"comment": "Nomer noto‘g‘ri"})
        req.refresh_from_db()
        self.card.refresh_from_db()
        self.assertEqual((req.status, self.card.work_phone), (S.REJECTED, "+998 71 111 22 33"))
        self.assertTrue(Notification.objects.filter(user=self.worker, change_request=req, kind="profile_change_denied").exists())
        self.assertContains(self.cw.get(url("me_edit")), "Nomer noto‘g‘ri")  # the person reads the reason

    def test_nobody_decides_on_their_own_request(self):
        hr_card = Employee.objects.get(user=self.hr)
        self.ask(self.ch, last_name="Hr", first_name="Two", middle_name="", work_phone="+998 1", personal_phone="", birth_date="")
        req = EmployeeChangeRequest.objects.get(employee=hr_card, status=S.PENDING)
        self.ch.post(url("change_decide", req.pk, "approve"))
        req.refresh_from_db()
        self.assertEqual(req.status, S.PENDING)  # refused
        self.ch2.post(url("change_decide", req.pk, "approve"))
        req.refresh_from_db()
        self.assertEqual(req.status, S.APPROVED)

    def test_an_employee_cannot_decide_or_list_and_a_decided_request_cannot_be_decided_again(self):
        self.ask(work_phone="+998 1")
        req = self.open_request()
        self.assertEqual(self.cw.post(url("change_decide", req.pk, "approve")).status_code, 403)
        self.assertEqual(self.cw.get(url("change_list")).status_code, 403)
        self.ch.post(url("change_decide", req.pk, "approve"))
        with self.assertRaises(changes.ChangeError):
            changes.approve(req.pk, self.hr2)
        with self.assertRaises(changes.ChangeError):
            changes.reject(req.pk, self.hr2, "x")

    def test_privacy_of_the_request_itself(self):
        self.ask(work_phone="+998 71 999 00 00")
        req = self.open_request()
        self.assertEqual(self.co.get(url("change_detail", req.pk)).status_code, 404)  # another employee
        self.assertContains(self.cw.get(url("change_detail", req.pk)), "+998 71 999 00 00")  # the person
        self.assertContains(self.ch.get(url("change_detail", req.pk)), "+998 71 999 00 00")  # a reviewer
        self.assertContains(self.ch.get(url("change_list")), "Karimov")
        self.assertEqual(self.co.post(url("change_cancel", req.pk)).status_code, 404)

    def test_the_person_can_cancel_their_own_request(self):
        self.ask(work_phone="+998 1")
        req = self.open_request()
        self.assertEqual(self.cw.post(url("change_cancel", req.pk)).status_code, 302)
        req.refresh_from_db()
        self.assertEqual((req.status, req.changes), (S.CANCELLED, {}))

    def test_a_card_is_required_and_an_archived_card_is_refused(self):
        self.assertEqual(self.client_for(make_user("nocard", role="employee")).get(url("me_edit")).status_code, 404)
        Employee.objects.filter(pk=self.card.pk).update(status="archived")
        self.assertEqual(self.ask(work_phone="+998 1").status_code, 200)
        self.assertFalse(EmployeeChangeRequest.objects.exists())

    def test_buttons(self):
        self.assertContains(self.cw.get(url("detail", self.card.pk)), url("me_edit"))
        self.assertNotContains(self.cw.get(url("list")), url("change_list"))
        self.assertContains(self.ch.get(url("list")), url("change_list"))


class ChangeRequestLanguageTests(ChangeRequestTests):
    """The new pages speak Russian and English: no Uzbek apostrophes in the interface."""

    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        import re

        self.ask(work_phone="+998 1")
        req = self.open_request()
        self.cw.get(url("me_edit"))  # shows (and so clears) the one-off "request sent" message, which was written in the language of the POST
        for lang in ("ru", "en"):
            for client, pages in ((self.cw, [url("me_edit"), url("change_detail", req.pk), url("notifications:list") if False else reverse("notifications:list")]),
                                  (self.ch, [url("change_list"), url("change_detail", req.pk), url("list")])):
                client.cookies["django_language"] = lang
                for page in pages:
                    body = re.sub(r'<form class="lang-switch".*?</form>', "", client.get(page).content.decode(), flags=re.S)
                    self.assertNotIn("‘", body, (lang, page))
                    self.assertNotIn("’", body, (lang, page))
