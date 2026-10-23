import re

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts import services as account_services
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.organization.models import Institution

from . import services
from .models import ChatNoticeAcceptance, Conversation, Message


def url(name, *args):
    return reverse(f"chat:{name}", args=args)


class ChatTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.admin = make_user("boss", role="admin")
        self.s1, self.s2 = Institution.objects.create(name="1-maktab", kind="school"), Institution.objects.create(name="2-maktab", kind="school")
        mk = lambda n, i: account_services.create_user(self.admin, username=n, email=f"{n}@example.test", first_name=n, last_name="Direktor", role="school_director", department=None, institution=i, request=None)
        self.d1, self.d2 = mk("dir1", self.s1), mk("dir2", self.s2)
        self.third = make_user("third", role="employee")
        self.sys = make_user("sysadm", role="sysadmin")
        self.c = {u.username: self.client_for(u) for u in (self.admin, self.d1, self.d2, self.third, self.sys)}

    def client_for(self, user):
        c = Client()
        login_with_two_factor(c, user)
        return c

    def accept(self, *users):
        for u in users:
            self.c[u.username].post(url("notice"), {"agree": "1"})

    def conv(self, a, b):
        self.accept(a)
        r = self.c[a.username].post(url("start"), {"user": str(b.pk)})
        self.assertEqual(r.status_code, 302, r.content[:200])
        return Conversation.objects.get(pk=re.search(r"/([0-9a-f-]{36})/", r["Location"]).group(1))

    # ---- the notice -------------------------------------------------------------------------------------------
    def test_nothing_works_before_the_notice_is_accepted(self):
        for name in ("inbox", "start"):
            r = self.c["dir1"].get(url(name)) if name == "inbox" else self.c["dir1"].post(url(name), {"user": str(self.d2.pk)})
            self.assertRedirects(r, url("notice"), fetch_redirect_response=False)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_the_notice_states_that_messages_are_kept_and_administrators_can_read_them(self):
        body = self.c["dir1"].get(url("notice")).content.decode()
        self.assertIn("saqlanadi", body)
        self.assertIn("Administrator", body)

    def test_accepting_needs_the_checkbox_and_is_audited(self):
        self.c["dir1"].post(url("notice"), {})
        self.assertFalse(services.has_accepted(self.d1))
        self.c["dir1"].post(url("notice"), {"agree": "1"})
        self.assertTrue(services.has_accepted(self.d1))
        self.assertTrue(AuditLog.objects.filter(action="chat_notice_accepted", user=self.d1).exists())

    def test_a_new_notice_version_has_to_be_accepted_again(self):
        self.accept(self.d1)
        ChatNoticeAcceptance.objects.filter(user=self.d1).update(version=0)
        self.assertRedirects(self.c["dir1"].get(url("inbox")), url("notice"), fetch_redirect_response=False)

    def test_accounts_without_use_chat_are_refused(self):
        for name in ("inbox", "notice"):
            self.assertEqual(self.c["sysadm"].get(url(name)).status_code, 403, name)
        self.assertEqual(Client().get(url("inbox")).status_code, 302)  # anonymous -> sign in

    # ---- talking ----------------------------------------------------------------------------------------------
    def test_one_conversation_per_pair_whoever_starts_it(self):
        a = self.conv(self.d1, self.d2)
        b = self.conv(self.d2, self.d1)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_talk_to_yourself_an_inactive_or_a_chatless_account(self):
        self.accept(self.d1)
        self.c["dir1"].post(url("start"), {"user": str(self.d1.pk)})
        self.c["dir1"].post(url("start"), {"user": str(self.sys.pk)})
        self.c["dir1"].post(url("start"), {"user": "not-a-uuid"})
        self.third.is_active = False
        self.third.save()
        self.c["dir1"].post(url("start"), {"user": str(self.third.pk)})
        self.assertEqual(Conversation.objects.count(), 0)

    def test_messages_arrive_and_are_marked_read_when_opened(self):
        conv = self.conv(self.d1, self.d2)
        self.c["dir1"].post(url("thread", conv.pk), {"body": "Salom, <b>kollega</b>"})
        self.accept(self.d2)
        self.assertEqual(services.unread_count(self.d2), 1)
        self.assertEqual(services.unread_count(self.d1), 0)
        self.assertIn("1", self.c["dir2"].get(reverse("portal:dashboard")).content.decode())  # the menu badge sees it
        body = self.c["dir2"].get(url("thread", conv.pk)).content.decode()
        self.assertIn("Salom, &lt;b&gt;kollega&lt;/b&gt;", body)  # plain text, escaped
        self.assertNotIn("<b>kollega</b>", body)
        self.assertEqual(services.unread_count(self.d2), 0)
        self.assertIn("o‘qildi", self.c["dir1"].get(url("thread", conv.pk)).content.decode())

    def test_empty_long_and_too_frequent_messages_are_refused(self):
        conv = self.conv(self.d1, self.d2)
        for body in ("", "   ", "x" * 2001):
            self.c["dir1"].post(url("thread", conv.pk), {"body": body})
        self.assertEqual(Message.objects.count(), 0)
        for i in range(services.RATE_LIMIT + 3):
            self.c["dir1"].post(url("thread", conv.pk), {"body": f"m{i}"})
        self.assertEqual(Message.objects.count(), services.RATE_LIMIT)

    def test_nobody_else_can_open_or_write_to_a_conversation(self):
        conv = self.conv(self.d1, self.d2)
        self.accept(self.third)
        self.assertEqual(self.c["third"].get(url("thread", conv.pk)).status_code, 404)
        self.assertEqual(self.c["third"].post(url("thread", conv.pk), {"body": "hi"}).status_code, 404)
        self.assertEqual(Message.objects.count(), 0)

    def test_a_message_to_an_inactive_person_is_refused(self):
        conv = self.conv(self.d1, self.d2)
        self.d2.is_active = False
        self.d2.save()
        with self.assertRaises(services.ChatError):
            services.send(self.d1, conv, "salom")

    def test_inbox_lists_people_with_their_school_and_never_emails(self):
        self.accept(self.d1)
        body = self.c["dir1"].get(url("inbox")).content.decode()
        self.assertIn("2-maktab", body)
        for other in ("dir2@example.test", "third@example.test", "boss@example.test"):  # the list never shows other people's e-mail
            self.assertNotIn(other, body)

    # ---- the administrator's archive ---------------------------------------------------------------------------
    def test_the_archive_is_for_administrators_only(self):
        conv = self.conv(self.d1, self.d2)
        self.c["dir1"].post(url("thread", conv.pk), {"body": "Maxfiy"})
        for who in ("dir1", "dir2", "third", "sysadm"):
            self.assertEqual(self.c[who].get(url("archive")).status_code, 403, who)
            self.assertEqual(self.c[who].get(url("archive_thread", conv.pk)).status_code, 403, who)

    def test_the_administrator_reads_everything_and_every_reading_is_logged(self):
        conv = self.conv(self.d1, self.d2)
        self.c["dir1"].post(url("thread", conv.pk), {"body": "Salom, bu maxfiy matn"})
        listing = self.c["boss"].get(url("archive")).content.decode()
        self.assertIn("dir1", listing)
        self.assertIn("dir2", listing)
        self.assertFalse(AuditLog.objects.filter(action="chat_archive_viewed").exists())  # the list shows no content
        r = self.c["boss"].get(url("archive_thread", conv.pk))
        self.assertContains(r, "Salom, bu maxfiy matn")
        self.c["boss"].get(url("archive_thread", conv.pk))
        logs = AuditLog.objects.filter(action="chat_archive_viewed", user=self.admin)
        self.assertEqual(logs.count(), 2)  # one entry per reading, with who and which conversation, never the text
        self.assertNotIn("maxfiy", str(logs.first().meta))
        self.assertEqual(services.unread_count(self.d2), 1)  # reading the archive does not mark anything read

    def test_messages_cannot_be_edited_or_deleted_through_the_site(self):
        conv = self.conv(self.d1, self.d2)
        self.c["dir1"].post(url("thread", conv.pk), {"body": "x"})
        m = Message.objects.get()
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.c["dir1"], method)(url("thread", conv.pk)).status_code, 405)
        self.assertTrue(Message.objects.filter(pk=m.pk).exists())

    def test_the_pair_order_is_enforced_by_the_database(self):
        from django.db import IntegrityError, transaction

        high, low = sorted((self.d1, self.d2), key=lambda u: u.pk, reverse=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conversation.objects.create(user_low=high, user_high=low)


class ChatLanguageTests(ChatTests):
    def test_pages_have_no_uzbek_interface_text_in_ru_and_en(self):
        conv = self.conv(self.d1, self.d2)
        self.c["dir1"].post(url("thread", conv.pk), {"body": "Hello"})
        self.accept(self.d2)
        for lang in ("ru", "en"):
            for who, pages in (("dir2", [url("notice"), url("inbox"), url("thread", conv.pk)]), ("boss", [url("archive"), url("archive_thread", conv.pk)])):
                self.c[who].cookies["django_language"] = lang
                for page in pages:
                    html = re.sub(r'<form class="lang-switch".*?</form>', "", self.c[who].get(page).content.decode(), flags=re.S)
                    html = html.replace("1-maktab", "").replace("2-maktab", "")  # school names are data
                    self.assertNotIn("‘", html, (lang, page))
                    self.assertNotIn("’", html, (lang, page))
