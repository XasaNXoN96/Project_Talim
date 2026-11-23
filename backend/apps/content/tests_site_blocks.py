"""Home page blocks: announcement strip, calendar, leadership, FAQ, district map; the portal pages that edit them and who may use them."""
import datetime

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.access.models import RoleAssignment
from apps.accounts.testing import login_with_two_factor, make_user
from apps.documents.storage import new_storage_name
from apps.organization.models import Institution

from .models import Announcement, Faq, Leader, SiteEvent

JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300") + b"\x00" * 60 + b"\xff\xd9"


class PublicBlocksTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        Announcement.objects.create(text="Qabul boshlandi", link="/murojaat/")
        Announcement.objects.create(text="Yashirin e’lon", is_published=False)
        Announcement.objects.create(text="Zararli havola", link="javascript:alert(1)")
        SiteEvent.objects.create(title="Kelgusi tadbir", date=today + datetime.timedelta(days=3))
        SiteEvent.objects.create(title="O‘tgan tadbir", date=today - datetime.timedelta(days=3))
        SiteEvent.objects.create(title="Yashirin tadbir", date=today + datetime.timedelta(days=4), is_published=False)
        self.leader = Leader.objects.create(full_name="Rahbar Birinchi", position="Boshliq")
        self.leader.photo.save(new_storage_name("jpg"), ContentFile(JPEG), save=True)
        self.hidden_leader = Leader.objects.create(full_name="Rahbar Yashirin", position="X", is_published=False)
        self.hidden_leader.photo.save(new_storage_name("jpg"), ContentFile(JPEG), save=True)
        Faq.objects.create(question="Savol bir?", answer="Javob bir.")
        Faq.objects.create(question="Yashirin savol?", answer="Yo‘q", is_published=False)
        Institution.objects.create(name="Xaritadagi maktab", kind="school", is_published=True, map_x=40, map_y=30)
        Institution.objects.create(name="Xaritasiz maktab", kind="school", is_published=True)
        self.page = Client().get(reverse("content:home")).content.decode()

    def test_only_published_items_are_shown(self):
        for shown in ("Qabul boshlandi", "Kelgusi tadbir", "Rahbar Birinchi", "Savol bir?", "Xaritadagi maktab"):
            self.assertIn(shown, self.page)
        for hidden in ("Yashirin e’lon", "O‘tgan tadbir", "Yashirin tadbir", "Rahbar Yashirin", "Yashirin savol?", "Xaritasiz maktab"):
            self.assertNotIn(hidden, self.page)

    def test_unsafe_announcement_link_is_dropped(self):
        self.assertNotIn("javascript:", self.page)
        self.assertIn("Zararli havola", self.page)

    def test_leader_photo_only_while_published(self):
        c = Client()
        self.assertEqual(c.get(reverse("content:leader_photo", args=[self.leader.pk])).status_code, 200)
        self.assertEqual(c.get(reverse("content:leader_photo", args=[self.hidden_leader.pk])).status_code, 404)

    def test_event_list_page(self):
        r = Client().get(reverse("content:events"))
        self.assertContains(r, "Kelgusi tadbir")
        self.assertNotContains(r, "O‘tgan tadbir")


class PortalSiteTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def client_for(self, role):
        user = make_user(f"s_{role}", role="employee")
        if role != "employee":
            RoleAssignment.objects.create(user=user, role=Group.objects.get(name=role), scope="all")
        c = Client()
        login_with_two_factor(c, user)
        return c

    def test_admin_creates_edits_and_deletes(self):
        c = self.client_for("admin")
        self.assertEqual(c.get(reverse("site_admin:index")).status_code, 200)
        r = c.post(reverse("site_admin:new", args=["faq"]), {"question": "Yangi savol?", "answer": "Yangi javob", "position": 1, "is_published": "on"})
        self.assertEqual(r.status_code, 302)
        faq = Faq.objects.get()
        c.post(reverse("site_admin:edit", args=["faq", faq.pk]), {"question": "O‘zgargan savol?", "answer": "A", "position": 1, "is_published": "on"})
        faq.refresh_from_db()
        self.assertEqual(faq.question, "O‘zgargan savol?")
        c.post(reverse("site_admin:delete", args=["faq", faq.pk]))
        self.assertEqual(Faq.objects.count(), 0)

    def test_announcement_link_rules(self):
        c = self.client_for("admin")
        bad = c.post(reverse("site_admin:new", args=["announcements"]), {"text": "x", "link": "javascript:alert(1)", "position": 0, "is_published": "on"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(Announcement.objects.count(), 0)
        c.post(reverse("site_admin:new", args=["announcements"]), {"text": "x", "link": "/murojaat/", "position": 0, "is_published": "on"})
        self.assertEqual(Announcement.objects.count(), 1)

    def test_unknown_kind_is_404(self):
        self.assertEqual(self.client_for("admin").get(reverse("site_admin:list", args=["nothing"])).status_code, 404)

    def test_roles_without_permission_get_403_and_delete_needs_post(self):
        faq = Faq.objects.create(question="Q?", answer="A")
        for role in ("employee", "hr", "news_author"):
            c = self.client_for(role)
            self.assertEqual(c.get(reverse("site_admin:index")).status_code, 403, role)
            self.assertEqual(c.post(reverse("site_admin:delete", args=["faq", faq.pk])).status_code, 403, role)
        self.assertEqual(self.client_for("admin").get(reverse("site_admin:delete", args=["faq", faq.pk])).status_code, 405)
        self.assertEqual(Faq.objects.count(), 1)

    def test_content_manager_may_edit(self):
        self.assertEqual(self.client_for("content_manager").get(reverse("site_admin:index")).status_code, 200)
