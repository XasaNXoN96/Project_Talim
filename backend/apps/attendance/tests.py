import datetime
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.organization.models import Department, Employee, Institution

from . import services
from .models import AttendanceEvent, AttendanceNoticeAcceptance, WorkZone

LAT, LON = "40.850000", "68.350000"       # the zone centre
NEAR = ("40.850300", "68.350300")          # ~45 m away: inside a 150 m zone
FAR = ("40.900000", "68.500000")           # kilometres away


def url(name, *args):
    return reverse(f"attendance:{name}", args=args)


class AttendanceBase(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.dept = Department.objects.create(name="Bo‘lim A")
        self.other_dept = Department.objects.create(name="Bo‘lim B")
        self.s1 = Institution.objects.create(name="1-maktab", kind="school")
        self.s2 = Institution.objects.create(name="2-maktab", kind="school")
        self.zone = WorkZone.objects.create(name="1-maktab hovlisi", institution=self.s1, latitude=LAT, longitude=LON, radius_m=150)
        self.admin = make_user("boss", role="admin")
        self.hr = make_user("hrista", role="hr")
        self.emp = make_user("emp", role="employee")
        self.emp_b = make_user("emp_b", role="employee")
        self.head = make_user("head", role="employee")
        RoleAssignment.objects.create(user=self.head, role=Group.objects.get(name="department_head"), scope="department", department=self.dept)
        self.director = make_user("dir1", role="employee")
        RoleAssignment.objects.create(user=self.director, role=Group.objects.get(name="school_director"), scope="institution")
        mk = lambda u, d, i=None, **k: Employee.objects.create(last_name=u.username.title(), first_name="X", department=d, user=u, institution=i, status="active", **k)
        self.card = mk(self.emp, self.dept, self.s1)
        self.card_b = mk(self.emp_b, self.other_dept)
        self.card_head = mk(self.head, self.dept)
        self.card_dir = mk(self.director, self.dept, self.s1)
        self.card_admin = mk(self.admin, self.dept)
        for u in (self.admin, self.hr, self.emp, self.emp_b, self.head, self.director):
            AttendanceNoticeAcceptance.objects.create(user=u)

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c


class ServiceTests(AttendanceBase):
    T0 = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)

    def press(self, kind, where=NEAR, **kw):
        kw.setdefault("now", self.T0)
        return services.clock(self.emp, kind, lat=where[0] if where else None, lon=where[1] if where else None, accuracy=kw.pop("accuracy", 20), **kw)

    def test_inside_the_zone_is_recorded_with_the_flag(self):
        ev = self.press("in")
        self.assertTrue(ev.inside_zone)
        self.assertEqual(ev.zone, self.zone)
        self.assertEqual(ev.distance_m, 0)
        self.assertIsNotNone(ev.latitude)

    def test_outside_needs_a_reason_and_is_flagged_with_it(self):
        with self.assertRaises(services.AttendanceError) as cm:
            self.press("in", FAR)
        self.assertIn("tashqaridasiz", str(cm.exception))
        self.assertEqual(AttendanceEvent.objects.count(), 0)
        ev = self.press("in", FAR, note="Rahbar topshirig‘i")
        self.assertIs(ev.inside_zone, False)
        self.assertGreater(ev.distance_m, 1000)

    @override_settings(ATTENDANCE_REQUIRE_LOCATION=True)
    def test_a_press_without_a_position_is_refused_when_a_zone_applies(self):
        with self.assertRaises(services.AttendanceError):
            self.press("in", None)

    @override_settings(ATTENDANCE_REQUIRE_LOCATION=False)
    def test_the_requirement_can_be_switched_off(self):
        ev = self.press("in", None)
        self.assertIsNone(ev.inside_zone)

    def test_a_person_without_a_zone_never_has_a_position_stored(self):
        WorkZone.objects.update(is_active=False)
        ev = self.press("in")
        self.assertIsNone(ev.latitude)
        self.assertIsNone(ev.inside_zone)

    def test_the_zone_of_another_institution_does_not_apply(self):
        WorkZone.objects.create(name="Boshqa", institution=self.s2, latitude="41.000000", longitude="69.000000", radius_m=100)
        ev = self.press("in")  # still measured against the own institution's zone
        self.assertEqual(ev.zone, self.zone)

    def test_a_poor_reading_and_nonsense_coordinates_are_refused(self):
        with self.assertRaises(services.AttendanceError):
            self.press("in", accuracy=900)
        for bad in (("abc", "1"), ("95", "10"), ("10", "200"), ("nan", "10"), ("40.1", None)):
            with self.assertRaises(services.AttendanceError, msg=bad):
                services.clock(self.emp, "in", lat=bad[0], lon=bad[1], accuracy=10, now=self.T0)

    def test_in_and_out_must_alternate(self):
        with self.assertRaises(services.AttendanceError):
            self.press("out")
        self.press("in")
        with self.assertRaises(services.AttendanceError):
            self.press("in", now=self.T0 + datetime.timedelta(minutes=5))
        self.press("out", now=self.T0 + datetime.timedelta(hours=8))
        with self.assertRaises(services.AttendanceError):
            self.press("out", now=self.T0 + datetime.timedelta(hours=9))

    def test_a_double_click_is_refused(self):
        self.press("in")
        with self.assertRaises(services.AttendanceError):
            self.press("out", now=self.T0 + datetime.timedelta(seconds=5))

    def test_a_forgotten_checkout_does_not_lock_the_next_day(self):
        self.press("in")
        ev = self.press("in", now=self.T0 + datetime.timedelta(days=1))
        self.assertEqual(ev.kind, "in")

    def test_people_who_cannot_press_are_refused(self):
        stray = make_user("nocard", role="employee")
        with self.assertRaises(services.AttendanceError):
            services.clock(stray, "in", lat=NEAR[0], lon=NEAR[1], now=self.T0)
        Employee.objects.filter(pk=self.card.pk).update(status="archived")
        with self.assertRaises(services.AttendanceError):
            self.press("in")

    def test_coordinates_are_wiped_after_the_retention_period_but_times_stay(self):
        old = self.press("in", now=timezone.now() - datetime.timedelta(days=91))
        new = self.press("out", now=timezone.now() - datetime.timedelta(days=5))
        self.assertEqual(services.purge_locations(), 1)
        old.refresh_from_db(), new.refresh_from_db()
        self.assertIsNone(old.latitude)
        self.assertTrue(old.inside_zone)       # the flag stays
        self.assertIsNotNone(new.latitude)

    def test_the_wipe_job_is_registered_and_runs(self):
        from apps.core import jobs

        self.assertIn("purge_attendance_locations", jobs.JOBS)
        self.press("in", now=timezone.now() - datetime.timedelta(days=200))
        call_command("purge_attendance_locations", verbosity=0)
        self.assertIsNone(AttendanceEvent.objects.get().latitude)

    def test_days_are_paired_into_worked_time(self):
        self.press("in")
        self.press("out", now=self.T0 + datetime.timedelta(hours=8, minutes=30))
        day = services.build_days(AttendanceEvent.objects.all())[0]
        self.assertEqual(day["worked_label"], "8:30")
        self.assertFalse(day["open"])
        self.press("in", now=self.T0 + datetime.timedelta(hours=9))
        self.assertTrue(services.build_days(AttendanceEvent.objects.all())[0]["open"])

    def test_distance_helper(self):
        self.assertLess(services.haversine_m(40.85, 68.35, 40.85, 68.35), 0.01)
        self.assertAlmostEqual(services.haversine_m(0, 0, 0, 1), 111195, delta=200)


class ViewTests(AttendanceBase):
    def post_press(self, user, kind="in", where=NEAR, **extra):
        return self.client_for(user).post(url("clock"), {"kind": kind, "lat": where[0], "lon": where[1], "acc": "15", **extra})

    def test_the_notice_comes_first(self):
        AttendanceNoticeAcceptance.objects.filter(user=self.emp).delete()
        c = self.client_for(self.emp)
        self.assertRedirects(c.get(url("clock")), url("notice"), fetch_redirect_response=False)
        self.assertRedirects(c.post(url("clock"), {"kind": "in"}), url("notice"), fetch_redirect_response=False)
        self.assertEqual(AttendanceEvent.objects.count(), 0)
        c.post(url("notice"), {"agree": "1"})
        self.assertEqual(c.get(url("clock")).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="attendance_notice_accepted").exists())

    def test_a_press_is_saved_and_logged_without_coordinates(self):
        r = self.post_press(self.emp)
        self.assertRedirects(r, url("clock"), fetch_redirect_response=False)
        ev = AttendanceEvent.objects.get()
        entry = AuditLog.objects.get(action="attendance_clocked")
        self.assertEqual(entry.meta, {"kind": "in", "inside": True})
        self.assertNotIn(str(ev.latitude), str(entry.meta))

    def test_only_the_clock_page_may_use_the_position(self):
        c = self.client_for(self.emp)
        self.assertIn("geolocation=(self)", c.get(url("clock"))["Permissions-Policy"])
        for page in (reverse("portal:dashboard"), url("notice")):
            self.assertIn("geolocation=()", c.get(page)["Permissions-Policy"])

    def test_the_menu_shows_the_real_pages(self):
        body = self.client_for(self.emp).get(reverse("portal:dashboard")).content.decode()
        self.assertIn(url("clock"), body)
        self.assertNotIn(url("zones"), body)          # the zone page is not for an ordinary employee
        self.assertIn(url("zones"), self.client_for(self.admin).get(reverse("portal:dashboard")).content.decode())

    def test_who_may_open_what(self):
        for user, team, zones in ((self.emp, 403, 403), (self.head, 200, 403), (self.director, 200, 403), (self.hr, 200, 200), (self.admin, 200, 200)):
            c = self.client_for(user)
            self.assertEqual(c.get(url("team")).status_code, team, user.username)
            self.assertEqual(c.get(url("zones")).status_code, zones, user.username)
        self.assertEqual(Client().get(url("clock")).status_code, 302)

    def test_zones_can_only_be_changed_by_an_administrator(self):
        data = {"name": "Yangi", "institution": "", "latitude": "40.1", "longitude": "68.1", "radius_m": "100", "is_active": "on"}
        self.assertEqual(self.client_for(self.hr).post(url("zone_new"), data).status_code, 403)
        self.assertEqual(self.client_for(self.emp).post(url("zone_new"), data).status_code, 403)
        r = self.client_for(self.admin).post(url("zone_new"), data)
        self.assertRedirects(r, url("zones"), fetch_redirect_response=False)
        bad = dict(data, radius_m="5", latitude="95")
        self.assertEqual(self.client_for(self.admin).post(url("zone_new"), bad).status_code, 200)
        self.assertEqual(WorkZone.objects.filter(name="Yangi").count(), 1)
        self.assertEqual(self.client_for(self.admin).get(url("zone_edit", self.zone.pk)).status_code, 200)

    def test_the_team_is_limited_by_scope(self):
        self.assertEqual(set(services.team_employees(self.head)), {self.card, self.card_head, self.card_dir, self.card_admin})   # only the own department
        self.assertEqual(set(services.team_employees(self.director)), {self.card, self.card_dir})                                # only the own institution
        self.assertEqual(set(services.team_employees(self.hr)), set(Employee.objects.filter(user__isnull=False)))
        self.assertFalse(services.team_employees(self.emp).exists())
        # somebody out of scope does not exist for the person
        self.assertEqual(self.client_for(self.head).get(url("member", self.card_b.pk)).status_code, 404)
        self.assertEqual(self.client_for(self.director).get(url("member", self.card_b.pk)).status_code, 404)
        self.assertEqual(self.client_for(self.director).get(url("member", self.card.pk)).status_code, 200)

    def test_looking_at_the_team_is_logged(self):
        self.client_for(self.hr).get(url("team"))
        self.client_for(self.hr).get(url("member", self.card.pk))
        self.assertEqual(AuditLog.objects.filter(action="attendance_team_viewed", user=self.hr).count(), 2)

    def test_exact_coordinates_only_for_those_who_may_correct(self):
        self.post_press(self.emp)
        ev = AttendanceEvent.objects.get()
        text = f"{ev.latitude}, {ev.longitude}"
        self.assertNotIn(text, self.client_for(self.director).get(url("member", self.card.pk)).content.decode())
        self.assertIn(text, self.client_for(self.hr).get(url("member", self.card.pk)).content.decode())

    def test_correction_needs_the_permission_and_a_reason_and_keeps_history(self):
        self.post_press(self.emp)
        at = (timezone.localtime() - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        data = {"kind": "out", "at": at, "note": "Unutgan edi"}
        self.assertEqual(self.client_for(self.director).post(url("correct", self.card.pk), data).status_code, 403)
        self.client_for(self.hr).post(url("correct", self.card.pk), dict(data, note=""))
        self.assertEqual(AttendanceEvent.objects.count(), 1)
        r = self.client_for(self.hr).post(url("correct", self.card.pk), data)
        self.assertRedirects(r, url("member", self.card.pk), fetch_redirect_response=False)
        self.assertEqual(AttendanceEvent.objects.count(), 2)          # added, nothing replaced
        manual = AttendanceEvent.objects.get(source="manual")
        self.assertEqual(manual.created_by, self.hr)
        self.assertTrue(AuditLog.objects.filter(action="attendance_corrected").exists())
        future = (timezone.localtime() + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        self.client_for(self.hr).post(url("correct", self.card.pk), dict(data, at=future))
        self.assertEqual(AttendanceEvent.objects.count(), 2)

    def test_an_outside_press_needs_the_note_in_the_form_too(self):
        r = self.post_press(self.emp, where=FAR)
        self.assertRedirects(r, url("clock"), fetch_redirect_response=False)
        self.assertEqual(AttendanceEvent.objects.count(), 0)
        self.post_press(self.emp, where=FAR, note="Seminar")
        self.assertIs(AttendanceEvent.objects.get().inside_zone, False)

    def test_the_zone_schematic_hides_names_and_respects_scope(self):
        self.post_press(self.emp)
        body = self.client_for(self.hr).get(url("zone_detail", self.zone.pk)).content.decode()
        self.assertIn("zp-in", body)
        self.assertNotIn("Emp X", body)
        self.assertIn("40.850", body.split("openstreetmap")[1][:80])   # no decimal comma in a link
        self.assertNotRegex(body, r'cx="\d+,\d')
        self.assertEqual(self.client_for(self.emp).get(url("zone_detail", self.zone.pk)).status_code, 403)
