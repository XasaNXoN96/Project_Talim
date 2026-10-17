"""Active sessions: listing, ending one, ending the others, and how they interact with passwords, blocking, 2FA and roles."""
import datetime

from django.contrib.sessions.models import Session
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog

from . import sessions as ls
from .models import UserSession
from .testing import PASSWORD, login_with_two_factor, make_user
from .twofactor import VERIFIED_KEY

CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
SAFARI_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
LIST, END_OTHERS = reverse("accounts:sessions"), reverse("accounts:sessions_end_others")
PROTECTED = reverse("portal:dashboard")


def end_url(pk):
    return reverse("accounts:session_end", args=[pk])


class Base(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.alice, self.bob = make_user("alice", role="employee"), make_user("bob", role="employee")
        self.admin = make_user("boss", role="admin")

    def login(self, user, ua=CHROME_WIN, ip="203.0.113.7", csrf=False):
        c = Client(HTTP_USER_AGENT=ua, REMOTE_ADDR=ip, enforce_csrf_checks=csrf)
        login_with_two_factor(c, user)
        c.get(PROTECTED)  # a first request, as a real browser would make
        return c

    def row_of(self, c):
        return UserSession.objects.get(session_key=c.session.session_key)

    def alive(self, c):
        return c.get(PROTECTED).status_code == 200

    def actions(self):
        return list(AuditLog.objects.filter(action__in=["session_ended", "sessions_ended_others"]).values_list("action", flat=True))


class Listing(Base):
    def test_a_user_sees_their_own_sessions_with_only_what_is_really_known(self):
        a1, a2 = self.login(self.alice), self.login(self.alice, ua=FIREFOX_LINUX, ip="198.51.100.9")
        r = a1.get(LIST)
        self.assertEqual(r.status_code, 200)
        items = r.context["sessions"]
        self.assertEqual(len(items), 2)
        cur = next(i for i in items if i["current"])
        other = next(i for i in items if not i["current"])
        self.assertEqual((cur["row"].browser, cur["row"].os, cur["row"].ip), ("Chrome", "Windows", "203.0.113.7"))
        self.assertEqual((other["row"].browser, other["row"].os, other["row"].ip), ("Firefox", "Linux", "198.51.100.9"))
        self.assertEqual(r.context["others"], 1)
        self.assertTrue(items[0]["current"])  # the current session comes first
        html = r.content.decode()
        for needle in ("Chrome", "Windows", "Firefox", "203.0.113.7"):
            self.assertIn(needle, html)
        self.assertTrue(a2.session.session_key)

    def test_no_session_key_cookie_or_raw_user_agent_ever_reaches_the_page_or_the_url(self):
        a1, a2 = self.login(self.alice), self.login(self.alice, ua=FIREFOX_LINUX)
        html = a1.get(LIST).content.decode() + a1.get(end_url(self.row_of(a2).pk)).content.decode() + a1.get(END_OTHERS).content.decode()
        for key in (a1.session.session_key, a2.session.session_key, a1.cookies["sessionid"].value):
            self.assertNotIn(key, html)
        self.assertNotIn(CHROME_WIN, html)
        self.assertNotIn("Mozilla/5.0", html)
        self.assertNotIn(a2.session.session_key, end_url(self.row_of(a2).pk))

    def test_nothing_is_invented_when_the_browser_says_nothing(self):
        c = self.login(self.alice, ua="curl/8.0", ip="203.0.113.7")
        row = self.row_of(c)
        self.assertEqual((row.browser, row.os), ("", ""))
        self.assertContains(c.get(LIST), "Noma’lum brauzer")
        row2 = self.row_of(self.login(self.alice, ua=""))
        self.assertEqual((row2.browser, row2.os), ("", ""))

    def test_agent_labels_come_from_a_fixed_vocabulary_so_hostile_headers_cannot_inject_markup(self):
        for ua, want in ((CHROME_WIN, ("Chrome", "Windows")), (FIREFOX_LINUX, ("Firefox", "Linux")), (SAFARI_IOS, ("Safari", "iOS")),
                         ("Mozilla/5.0 (Linux; Android 14) Chrome/126.0 Mobile Safari/537.36", ("Chrome", "Android")),
                         ("Mozilla/5.0 (Windows NT 10.0) Chrome/126.0 Safari/537.36 Edg/126.0", ("Edge", "Windows")),
                         ("<script>alert(1)</script>" * 40, ("", ""))):
            self.assertEqual(ls.describe_agent(ua), want)
        c = self.login(self.alice, ua="<script>alert(1)</script> Chrome/1 " + "A" * 5000)
        row = self.row_of(c)
        self.assertEqual(row.browser, "Chrome")
        self.assertNotIn("<script>", c.get(LIST).content.decode())
        UserSession.objects.filter(pk=row.pk).update(browser="<script>alert(2)</script>")  # even a tampered row is escaped
        self.assertNotIn("<script>alert(2)", c.get(LIST).content.decode())

    def test_only_sessions_the_server_still_accepts_are_listed(self):
        a1, a2, a3 = self.login(self.alice), self.login(self.alice), self.login(self.alice)
        Session.objects.filter(session_key=a2.session.session_key).update(expire_date=timezone.now() - datetime.timedelta(minutes=1))
        Session.objects.filter(session_key=a3.session.session_key).delete()
        self.assertEqual(len(a1.get(LIST).context["sessions"]), 1)

    def test_a_session_that_began_before_the_feature_appears_after_its_next_request(self):
        c = Client(HTTP_USER_AGENT=FIREFOX_LINUX)
        login_with_two_factor(c, self.alice)
        UserSession.objects.all().delete()  # as if it predates the feature
        c.get(PROTECTED)
        self.assertEqual(UserSession.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(len(c.get(LIST).context["sessions"]), 1)

    def test_last_activity_is_refreshed_at_most_every_five_minutes(self):
        c = self.login(self.alice)
        row = self.row_of(c)
        first = row.last_seen_at
        c.get(PROTECTED)
        self.assertEqual(self.row_of(c).last_seen_at, first)  # too soon: no write
        UserSession.objects.filter(pk=row.pk).update(last_seen_at=timezone.now() - datetime.timedelta(minutes=6))
        old = self.row_of(c).last_seen_at
        c.get(PROTECTED)
        self.assertGreater(self.row_of(c).last_seen_at, old)
        self.assertEqual(self.row_of(c).first_seen_at, row.first_seen_at)

    def test_logging_out_removes_the_row(self):
        c = self.login(self.alice)
        key = c.session.session_key
        c.post(reverse("accounts:logout"))
        self.assertFalse(UserSession.objects.filter(session_key=key).exists())

    def test_the_real_login_flow_creates_the_row_with_the_browser_it_came_from(self):
        c = Client(HTTP_USER_AGENT=SAFARI_IOS, REMOTE_ADDR="192.0.2.44")
        r = c.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD})
        self.assertEqual(r.status_code, 302)
        row = UserSession.objects.get(user=self.alice)
        self.assertEqual((row.browser, row.os, row.ip, row.session_key), ("Safari", "iOS", "192.0.2.44", c.session.session_key))


class Isolation(Base):
    def test_another_users_sessions_are_neither_listed_nor_reachable_by_id(self):
        a, b = self.login(self.alice), self.login(self.bob, ip="198.51.100.77")
        self.assertEqual(len(a.get(LIST).context["sessions"]), 1)
        self.assertNotIn("198.51.100.77", a.get(LIST).content.decode())
        bob_row = self.row_of(b)
        self.assertEqual(a.get(end_url(bob_row.pk)).status_code, 404)
        before = AuditLog.objects.count()
        self.assertEqual(a.post(end_url(bob_row.pk)).status_code, 404)  # a direct POST with a swapped id
        self.assertTrue(self.alive(b))
        self.assertTrue(UserSession.objects.filter(pk=bob_row.pk).exists())
        self.assertEqual(AuditLog.objects.count(), before)
        for pk in ("11111111-2222-3333-4444-555555555555",):
            self.assertEqual(a.post(end_url(pk)).status_code, 404)  # nonexistent looks the same as someone else's
        self.assertEqual(a.get("/accounts/security/sessions/not-a-uuid/end/").status_code, 404)

    def test_ending_others_never_touches_other_accounts_even_untracked_ones(self):
        a1, a2, b = self.login(self.alice), self.login(self.alice), self.login(self.bob)
        UserSession.objects.all().delete()  # nothing tracked: the sweep must not depend on the index
        a1.post(END_OTHERS)
        self.assertTrue(self.alive(b))
        self.assertFalse(self.alive(a2))
        self.assertTrue(self.alive(a1))

    def test_the_session_key_cannot_be_moved_to_another_account(self):
        a = self.login(self.alice)
        row = self.row_of(a)
        UserSession.objects.filter(pk=row.pk).update(user=self.bob)  # corrupted index
        self.assertEqual(ls.active_sessions(self.bob, None), [])  # never listed for the wrong account
        a.get(PROTECTED)  # the next request repairs it under the real owner
        self.assertEqual(len(a.get(LIST).context["sessions"]), 1)
        self.assertEqual(ls.active_sessions(self.bob, None), [])


class EndingOne(Base):
    def test_ending_another_session_revokes_it_for_real_and_leaves_this_one_alone(self):
        a1, a2 = self.login(self.alice), self.login(self.alice, ua=FIREFOX_LINUX)
        target = self.row_of(a2)
        ask = a1.get(end_url(target.pk))
        self.assertEqual(ask.status_code, 200)
        self.assertTrue(self.alive(a2))  # asking changes nothing
        r = a1.post(end_url(target.pk))
        self.assertRedirects(r, LIST, fetch_redirect_response=False)
        self.assertFalse(Session.objects.filter(session_key=a2.session.session_key).exists())
        self.assertFalse(UserSession.objects.filter(pk=target.pk).exists())
        again = a2.get(PROTECTED)
        self.assertEqual(again.status_code, 302)
        self.assertIn("/accounts/login/", again["Location"])
        self.assertEqual(a2.post(reverse("tasks:create")).status_code, 302)  # any protected URL
        page = a1.get(LIST)  # the success message shows on the next page
        self.assertContains(page, "Sessiya yakunlandi")
        self.assertEqual(len(page.context["sessions"]), 1)
        self.assertTrue(self.alive(a1))

    def test_the_audit_entry_names_the_action_and_the_row_but_no_secrets(self):
        a1, a2 = self.login(self.alice), self.login(self.alice, ua=FIREFOX_LINUX)
        target = self.row_of(a2)
        key2 = a2.session.session_key
        a1.post(end_url(target.pk))
        e = AuditLog.objects.get(action="session_ended")
        self.assertEqual((e.user, e.object_type, e.object_id, e.meta), (self.alice, "UserSession", str(target.pk), {}))
        for a in AuditLog.objects.all():
            blob = str(a.meta) + a.object_id
            self.assertNotIn(key2, blob)
            self.assertNotIn(a1.session.session_key, blob)
            self.assertNotIn("Firefox", blob)

    def test_the_current_session_cannot_be_ended_here_it_is_signing_out(self):
        a = self.login(self.alice)
        mine = self.row_of(a)
        self.assertRedirects(a.get(end_url(mine.pk)), LIST, fetch_redirect_response=False)
        a.post(end_url(mine.pk))
        self.assertTrue(self.alive(a))
        self.assertEqual(self.actions(), [])

    def test_an_already_ended_session_gives_a_calm_error_not_a_crash_or_a_second_audit_entry(self):
        a1, a2 = self.login(self.alice), self.login(self.alice)
        target = self.row_of(a2)
        Session.objects.filter(session_key=a2.session.session_key).delete()  # ended elsewhere meanwhile
        r = a1.post(end_url(target.pk), follow=True)
        self.assertContains(r, "allaqachon yakunlangan")
        self.assertEqual(self.actions(), [])
        self.assertEqual(a1.get(end_url(target.pk)).status_code, 404)


class EndingOthers(Base):
    def test_all_other_sessions_end_and_this_one_stays_signed_in(self):
        a1, a2, a3, b = self.login(self.alice), self.login(self.alice), self.login(self.alice, ua=SAFARI_IOS), self.login(self.bob)
        self.assertContains(a1.get(END_OTHERS), "2")
        self.assertTrue(self.alive(a2))  # the confirmation page changes nothing
        r = a1.post(END_OTHERS)
        self.assertRedirects(r, LIST, fetch_redirect_response=False)
        self.assertFalse(self.alive(a2))
        self.assertFalse(self.alive(a3))
        self.assertTrue(self.alive(a1))
        self.assertTrue(self.alive(b))
        self.assertEqual(UserSession.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(a1.get(LIST).context["others"], 0)
        e = AuditLog.objects.get(action="sessions_ended_others")
        self.assertEqual((e.user, e.meta), (self.alice, {"closed": 2}))

    def test_with_no_other_session_it_says_so(self):
        a = self.login(self.alice)
        r = a.post(END_OTHERS, follow=True)
        self.assertContains(r, "boshqa sessiya yo‘q")
        self.assertTrue(self.alive(a))


class Protection(Base):
    def test_anonymous_visitors_are_sent_to_login(self):
        a = self.login(self.alice)
        row = self.row_of(a)
        for method, u in (("get", LIST), ("get", END_OTHERS), ("post", END_OTHERS), ("get", end_url(row.pk)), ("post", end_url(row.pk))):
            r = getattr(Client(), method)(u)
            self.assertEqual(r.status_code, 302, u)
            self.assertIn("/accounts/login/", r["Location"])
        self.assertTrue(self.alive(a))

    def test_csrf_is_enforced_on_both_changing_requests(self):
        a1, a2 = self.login(self.alice, csrf=True), self.login(self.alice)
        self.assertEqual(a1.post(end_url(self.row_of(a2).pk)).status_code, 403)
        self.assertEqual(a1.post(END_OTHERS).status_code, 403)
        self.assertTrue(self.alive(a2))
        self.assertEqual(self.actions(), [])

    def test_only_reading_methods_and_post_are_accepted(self):
        a = self.login(self.alice)
        for u in (LIST, END_OTHERS):
            for m in ("put", "patch", "delete"):
                self.assertEqual(getattr(a, m)(u).status_code, 405, (m, u))
        self.assertEqual(a.post(LIST).status_code, 405)
        self.assertEqual(a.head(LIST).status_code, 200)
        self.assertEqual(a.options(LIST).status_code, 200)

    def test_a_user_who_must_change_the_password_cannot_use_these_pages_first(self):
        c = self.login(self.alice)
        self.alice.must_change_password = True
        self.alice.save()
        r = c.get(LIST)
        self.assertEqual(r.status_code, 302)
        self.assertIn("password-change", r["Location"])

    def test_the_left_over_row_of_a_revoked_session_gives_nobody_access(self):
        self.login(self.alice)
        a2 = self.login(self.alice)
        Session.objects.filter(session_key=a2.session.session_key).delete()
        self.assertFalse(self.alive(a2))  # the index row alone grants nothing


class PasswordsBlockingAndRecovery(Base):
    def test_changing_the_password_closes_the_other_sessions_and_keeps_this_one(self):
        a1, a2, b = self.login(self.alice), self.login(self.alice, ua=FIREFOX_LINUX), self.login(self.bob)
        r = a1.post(reverse("accounts:password_change"), {"old_password": PASSWORD, "new_password1": "Yangi-Parol-98765!", "new_password2": "Yangi-Parol-98765!"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.alive(a2))
        self.assertTrue(self.alive(a1))
        self.assertTrue(self.alive(b))
        items = a1.get(LIST).context["sessions"]
        self.assertEqual(len(items), 1)  # the key rotated with the password; the list follows the new one
        self.assertTrue(items[0]["current"])
        self.assertEqual(UserSession.objects.filter(user=self.alice).count(), 1)

    def test_blocking_a_user_ends_every_session_at_once_and_clears_the_index(self):
        a1, a2 = self.login(self.alice), self.login(self.alice)
        adm = self.login(self.admin)
        r = adm.post(reverse("users:action", args=[self.alice.pk, "deactivate"]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.alive(a1))
        self.assertFalse(self.alive(a2))
        self.assertEqual(UserSession.objects.filter(user=self.alice).count(), 0)
        self.assertEqual(Session.objects.filter(session_key__in=[a1.session.session_key]).count(), 0)
        self.assertTrue(self.alive(adm))

    def test_a_blocked_user_with_a_surviving_cookie_still_gets_nothing(self):
        a = self.login(self.alice)
        self.alice.is_active = False
        self.alice.save()  # the row and session are still there ...
        self.assertEqual(a.get(PROTECTED).status_code, 302)  # ... but Django refuses an inactive user
        self.assertEqual(a.get(LIST).status_code, 302)

    def test_completing_a_password_reset_closes_all_sessions_and_the_index(self):
        a1, a2 = self.login(self.alice), self.login(self.alice)
        Client().post(reverse("accounts:password_reset"), {"email": self.alice.email})
        import re

        link = re.search(r"/accounts/reset/[^\s]+", mail.outbox[-1].body).group(0)
        c = Client()
        url = c.get(link, follow=True).redirect_chain[-1][0]
        c.post(url, {"new_password1": "Boshqa-Parol-24680!", "new_password2": "Boshqa-Parol-24680!"})
        self.assertFalse(self.alive(a1))
        self.assertFalse(self.alive(a2))
        self.assertEqual(UserSession.objects.filter(user=self.alice).count(), 0)

    def test_forcing_a_password_change_does_not_close_sessions_but_confines_them(self):
        a = self.login(self.alice)
        adm = self.login(self.admin)
        adm.post(reverse("users:action", args=[self.alice.pk, "force_password"]))
        r = a.get(PROTECTED)
        self.assertEqual(r.status_code, 302)  # confined to the password change page, not signed out
        self.assertIn("password-change", r["Location"])
        self.assertTrue(Session.objects.filter(session_key=a.session.session_key).exists())


class PrivilegedAccounts(Base):
    def test_privileged_users_use_the_same_pages_and_ending_sessions_cannot_bypass_two_factor(self):
        a1, a2 = self.login(self.admin), self.login(self.admin, ua=FIREFOX_LINUX)
        self.assertEqual(len(a1.get(LIST).context["sessions"]), 2)
        a1.post(end_url(self.row_of(a2).pk))
        self.assertFalse(self.alive(a2))
        self.assertTrue(self.alive(a1))
        # a privileged session that did not pass the second factor gets no sessions page at all
        c = Client()
        c.force_login(self.admin)
        r = c.get(LIST)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        s = c.session
        self.assertFalse(s.get(VERIFIED_KEY))

    def test_an_administrator_cannot_end_a_users_session_through_the_self_service_route(self):
        a, adm = self.login(self.alice), self.login(self.admin)
        row = self.row_of(a)
        self.assertEqual(adm.post(end_url(row.pk)).status_code, 404)
        self.assertTrue(self.alive(a))


class Languages(Base):
    def test_pages_messages_and_confirmations_follow_the_language(self):
        for lang, title, ok, ask in (("ru", "Активные сессии", "Сессия завершена.", "Завершить сессию"), ("en", "Active sessions", "Session ended.", "End session"),
                                      ("uz", "Faol sessiyalar", "Sessiya yakunlandi.", "Sessiyani yakunlash")):
            a1, a2 = self.login(self.alice), self.login(self.alice)
            a1.cookies["django_language"] = lang
            page = a1.get(LIST)
            self.assertContains(page, f'<html lang="{lang}">')
            self.assertContains(page, title)
            self.assertContains(a1.get(end_url(self.row_of(a2).pk)), ask)
            done = a1.post(end_url(self.row_of(a2).pk), follow=True)
            self.assertContains(done, ok)
            if lang != "uz":
                body = a1.get(LIST).content.decode()
                for word in ("Faol", "Yakunlash", "Joriy", "faollik", "Xavfsizlik"):
                    self.assertNotIn(word, body, (lang, word))
            UserSession.objects.filter(user=self.alice).delete()

    def test_the_security_page_links_to_the_sessions_page(self):
        a = self.login(self.alice)
        self.assertContains(a.get(reverse("accounts:security")), LIST)
