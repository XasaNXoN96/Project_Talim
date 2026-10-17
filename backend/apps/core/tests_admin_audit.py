"""Day 21: what a superuser can do in the Django admin, what is refused, what is journalled; and the safe `seed_roles`.

Threat model of this audit trail: it records actions taken through the application's admin and portal by signed-in users. It does NOT protect against
someone who can write to the database directly (the database owner, a system administrator with shell access): they can change data and, with the
database owner's rights, even the journal. The runtime database role cannot (see deploy/postgres), and backups are encrypted, but that is a boundary,
not a guarantee."""
import json
from io import StringIO

from django.contrib import admin as dj_admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.access.models import RoleAssignment
from apps.access.roles import ROLE_PERMISSIONS, RoleCode
from apps.accounts.testing import login_with_two_factor, make_user
from apps.audit.models import AuditLog
from apps.content import workflow
from apps.content.models import News, NewsReview
from apps.core.acceptance import World
from apps.organization.models import Department, Employee

User = get_user_model()


def perm(name):
    app, code = name.split(".")
    return Permission.objects.get(content_type__app_label=app, codename=code)


def form_data(response, **over):
    """What the browser would post back for an admin change form: the form's own initial values, the inlines' management forms, plus overrides."""
    adminform = response.context["adminform"]
    data = {}
    for name, field in adminform.form.fields.items():
        if name in adminform.readonly_fields:
            continue
        value = adminform.form.initial.get(name, field.initial)
        if value is None:
            continue
        if hasattr(value, "all"):
            value = [o.pk for o in value.all()]
        if isinstance(value, bool):
            if value:
                data[name] = "on"
            continue
        if hasattr(value, "pk"):
            value = value.pk
        if hasattr(value, "isoformat") and not hasattr(value, "hour"):
            value = value.isoformat()
        if hasattr(value, "hour"):
            data[f"{name}_0"], data[f"{name}_1"] = value.date().isoformat(), value.time().replace(microsecond=0).isoformat()
            continue
        data[name] = value
    for inline in response.context.get("inline_admin_formsets", []):
        mf = inline.formset.management_form
        for k in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
            data[f"{mf.prefix}-{k}"] = mf.initial.get(k, 0)
    data.update(over)
    return data


class AdminBase(TestCase):
    def setUp(self):
        self.w = World()
        self.su = self.w.client("superuser")
        self.cat = self.w.news_category
        self.author = make_user("adm_au", role="news_author")
        self.editor = make_user("adm_ed", role="news_editor")

    def news(self, status="draft", **kw):
        return News.objects.create(title=kw.pop("title", "Admin yangiligi"), slug=kw.pop("slug", f"adm-{News.objects.count()}"), body=kw.pop("body", "Dastlabki matn"),
                                   status=status, author=kw.pop("author", self.author), category=self.cat, **kw)

    def change(self, obj, model, **over):
        url = reverse(f"admin:{model}_change", args=[obj.pk])
        r = self.su.get(url)
        self.assertEqual(r.status_code, 200)
        return self.su.post(url, form_data(r, **over))

    def entries(self, action=None):
        qs = AuditLog.objects.all()
        return list(qs.filter(action=action) if action else qs)


class NewsInTheAdmin(AdminBase):
    def test_a_text_change_is_allowed_and_audited_by_field_name_without_the_text(self):
        n = self.news()
        self.assertEqual(self.change(n, "content_news", body="MAXFIY-yangi-matn-sir").status_code, 302)
        n.refresh_from_db()
        self.assertEqual(n.body, "MAXFIY-yangi-matn-sir")
        entry = AuditLog.objects.get(action="admin_changed", object_type="News")
        self.assertEqual((entry.user.username, str(entry.object_id)), ("root", str(n.pk)))
        self.assertEqual(entry.meta["fields"], ["body"])
        self.assertEqual(entry.meta["via"], "django_admin")
        self.assertNotIn("MAXFIY", json.dumps(entry.meta))
        self.assertIsNotNone(entry.at)

    def test_saving_without_a_change_writes_no_entry(self):
        n = self.news()
        self.change(n, "content_news")
        self.assertEqual(self.entries("admin_changed"), [])

    def test_status_author_and_publication_date_cannot_be_set_through_the_admin(self):
        n = self.news()
        other = make_user("adm_other", role="news_author")
        self.change(n, "content_news", status="published", author=other.pk, publish_at_0="2026-01-01", publish_at_1="10:00:00")
        n.refresh_from_db()
        self.assertEqual((n.status, n.author_id, n.publish_at), ("draft", self.author.pk, None))
        self.assertEqual(self.w.client("anon").get(reverse("content:news_detail", args=[n.slug])).status_code, 404)

    def test_changing_the_text_of_an_approved_item_sends_it_back_to_draft_with_history_and_audit(self):
        n = self.news(status="approved")
        self.change(n, "content_news", title="Boshqa sarlavha")
        n.refresh_from_db()
        self.assertEqual(n.status, "draft")
        row = n.reviews.get()
        self.assertEqual((row.action, row.actor.username, row.from_status, row.to_status), ("edit_reset", "root", "approved", "draft"))
        entry = AuditLog.objects.get(action="admin_changed", object_type="News")
        self.assertEqual(entry.meta["fields"], ["approval_reset", "title"])
        # the old approval cannot be used for the new text
        self.assertEqual(self.w.client("content").post(reverse("news_admin:status", args=[n.pk, "publish"])).status_code, 302)
        n.refresh_from_db()
        self.assertEqual(n.status, "draft")

    def test_an_approved_item_keeps_its_approval_when_the_text_did_not_change(self):
        n = self.news(status="approved")
        self.change(n, "content_news")
        n.refresh_from_db()
        self.assertEqual(n.status, "approved")
        self.assertEqual(n.reviews.count(), 0)

    def test_an_item_under_review_is_frozen_in_the_admin_too(self):
        n = self.news(status="review")
        self.change(n, "content_news", body="Tekshiruv paytida o‘zgartirildi")
        n.refresh_from_db()
        self.assertEqual(n.body, "Dastlabki matn")
        self.assertEqual(n.status, "review")

    def test_a_published_item_can_be_corrected_and_stays_published(self):
        from django.utils import timezone
        n = self.news(status="published", publish_at=timezone.now())
        self.change(n, "content_news", excerpt="Tuzatish")
        n.refresh_from_db()
        self.assertEqual((n.status, n.excerpt), ("published", "Tuzatish"))
        self.assertEqual(AuditLog.objects.get(action="admin_changed").meta["fields"], ["excerpt"])

    def test_news_cannot_be_added_or_deleted_in_the_admin_not_even_in_bulk(self):
        n = self.news()
        NewsReview.objects.create(news=n, action="submit", from_status="draft", to_status="review")
        self.assertEqual(self.su.get(reverse("admin:content_news_add")).status_code, 403)
        self.assertEqual(self.su.get(reverse("admin:content_news_delete", args=[n.pk])).status_code, 403)
        self.assertEqual(self.su.post(reverse("admin:content_news_delete", args=[n.pk]), {"post": "yes"}).status_code, 403)
        page = self.su.get(reverse("admin:content_news_changelist"))
        self.assertNotIn("delete_selected", page.content.decode())                    # the bulk action is not even offered
        r = self.su.post(reverse("admin:content_news_changelist"), {"action": "delete_selected", "_selected_action": [str(n.pk)], "post": "yes"})
        self.assertIn(r.status_code, (200, 302))
        self.assertTrue(News.objects.filter(pk=n.pk).exists())
        self.assertEqual(NewsReview.objects.count(), 1)
        self.assertEqual(self.entries("admin_deleted"), [])

    def test_the_approval_history_cannot_be_seen_changed_or_deleted_in_the_admin(self):
        n = self.news()
        row = NewsReview.objects.create(news=n, action="submit", from_status="draft", to_status="review", comment="c")
        self.assertNotIn(NewsReview, dj_admin.site._registry)
        for suffix in ("", f"{row.pk}/change/", f"{row.pk}/delete/", "add/"):
            for method in ("get", "post"):
                self.assertEqual(getattr(self.su, method)(f"{reverse('admin:index')}content/newsreview/{suffix}").status_code, 404, (method, suffix))
        self.assertEqual(NewsReview.objects.get(pk=row.pk).comment, "c")

    def test_internal_notes_never_reach_the_audit_log_whatever_happens_to_the_item(self):
        n = self.news(status="review")
        version = workflow.version_token(n)
        c = Client()
        login_with_two_factor(c, self.editor)
        c.post(reverse("news_admin:status", args=[n.pk, "request_changes"]), {"version": version, "comment": "Muallifga", "internal_note": "MAXFIY-ICHKI-QAYD"})
        n.refresh_from_db()
        self.change(n, "content_news", body="Tahrir")
        self.assertNotIn("MAXFIY-ICHKI-QAYD", json.dumps(list(AuditLog.objects.values_list("meta", flat=True))))


class UsersAndGroupsInTheAdmin(AdminBase):
    def test_users_cannot_be_added_or_deleted_and_passwords_cannot_be_set_in_the_admin(self):
        target = self.w.users["emp"]
        self.assertEqual(self.su.get(reverse("admin:accounts_user_add")).status_code, 403)
        self.assertEqual(self.su.post(reverse("admin:accounts_user_delete", args=[target.pk]), {"post": "yes"}).status_code, 403)
        before = target.password
        for method in ("get", "post"):
            r = getattr(self.su, method)(reverse("admin:auth_user_password_change", args=[target.pk]),
                                         {"password1": "Yangi-Parol-9876!", "password2": "Yangi-Parol-9876!"} if method == "post" else {})
            self.assertEqual(r.status_code, 403, method)
        target.refresh_from_db()
        self.assertEqual(target.password, before)
        self.assertEqual(AuditLog.objects.filter(action="admin_blocked", meta__what="set_password", user__username="root").count(), 2)   # both attempts, nothing else

    def test_the_audit_never_holds_a_password_or_hash(self):
        target = self.w.users["emp"]
        self.change(target, "accounts_user", first_name="Boshqa", password="not-editable")
        text = json.dumps(list(AuditLog.objects.values_list("meta", flat=True)))
        self.assertNotIn("pbkdf2", text)
        self.assertNotIn("argon2", text)
        self.assertNotIn("not-editable", text)

    def test_security_flags_are_journalled_with_old_and_new_value(self):
        target = self.w.users["emp"]
        self.change(target, "accounts_user", is_staff="on")
        entry = AuditLog.objects.get(action="admin_changed", object_type="User")
        self.assertEqual(entry.meta["flags"], {"is_staff": [False, True]})
        self.assertEqual(entry.meta["fields"], ["is_staff"])

    def test_groups_of_a_user_are_read_only_roles_are_assigned_in_the_portal(self):
        target = self.w.users["emp"]
        before = set(target.groups.values_list("name", flat=True))
        self.change(target, "accounts_user", groups=[Group.objects.get(name="admin").pk])
        self.assertEqual(set(User.objects.get(pk=target.pk).groups.values_list("name", flat=True)), before)
        assignments = RoleAssignment.objects.count()
        self.assertEqual(self.su.post(reverse("admin:access_roleassignment_add"), {"user": target.pk, "role": Group.objects.get(name="admin").pk, "scope": "all"}).status_code, 403)
        ra = RoleAssignment.objects.first()
        self.assertEqual(self.su.post(reverse("admin:access_roleassignment_change", args=[ra.pk]), {"scope": "own"}).status_code, 403)
        self.assertEqual(self.su.post(reverse("admin:access_roleassignment_delete", args=[ra.pk]), {"post": "yes"}).status_code, 403)
        self.assertEqual(self.su.get(reverse("admin:access_roleassignment_changelist")).status_code, 200)
        self.assertEqual(RoleAssignment.objects.count(), assignments)

    def test_a_personal_permission_can_be_granted_and_revoked_with_an_audit_entry_and_it_really_works(self):
        n = News.objects.create(title="Mening", slug="mening", body="b", status="review", author=self.editor, category=self.cat)
        c = Client()
        login_with_two_factor(c, self.editor)
        url = reverse("news_admin:status", args=[n.pk, "approve"])
        c.post(url, {"version": workflow.version_token(n)})
        n.refresh_from_db()
        self.assertEqual(n.status, "review")                                       # refused: own item
        keep = [p.pk for p in self.editor.user_permissions.all()]
        self.change(self.editor, "accounts_user", user_permissions=keep + [perm("content.approve_own_news").pk])
        entry = AuditLog.objects.get(action="admin_changed", object_type="User")
        self.assertEqual(entry.meta["user_permissions_added"], ["content.approve_own_news"])
        self.assertEqual(entry.meta["user_permissions_removed"], [])
        c.post(url, {"version": workflow.version_token(n)})
        n.refresh_from_db()
        self.assertEqual(n.status, "approved")                                     # the explicit exception works...
        self.assertEqual(n.reviews.get().actor, self.editor)                       # ...and the history names who used it
        self.change(User.objects.get(pk=self.editor.pk), "accounts_user", user_permissions=keep)
        self.assertEqual(AuditLog.objects.filter(action="admin_changed", object_type="User").latest("at").meta["user_permissions_removed"], ["content.approve_own_news"])

    def test_role_groups_are_read_only_and_cannot_be_deleted_in_the_admin(self):
        group = Group.objects.get(name="news_editor")
        before = set(group.permissions.values_list("pk", flat=True))
        self.change(group, "auth_group", name="boshqa-nom", permissions=list(before) + [perm("content.publish_news").pk])
        group.refresh_from_db()
        self.assertEqual((group.name, set(group.permissions.values_list("pk", flat=True))), ("news_editor", before))
        self.assertEqual(self.su.post(reverse("admin:auth_group_delete", args=[group.pk]), {"post": "yes"}).status_code, 403)
        r = self.su.post(reverse("admin:auth_group_changelist"), {"action": "delete_selected", "_selected_action": [str(group.pk)], "post": "yes"})
        self.assertTrue(Group.objects.filter(name="news_editor").exists(), r.status_code)

    def test_other_groups_are_editable_with_the_permission_names_in_the_audit(self):
        group = Group.objects.create(name="pilot-guruh")
        self.change(group, "auth_group", permissions=[perm("content.view_news").pk, perm("documents.view_document").pk])
        entry = AuditLog.objects.get(action="admin_changed", object_type="Group")
        self.assertEqual(entry.meta["permissions_added"], ["content.view_news", "documents.view_document"])
        self.assertEqual(self.su.post(reverse("admin:auth_group_delete", args=[group.pk]), {"post": "yes"}).status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action="admin_deleted", object_type="Group", object_id=str(group.pk)).exists())

    def test_only_superusers_reach_the_admin_at_all(self):
        for actor in ("anon", "emp", "content", "admin", "hr", "sysadmin"):
            c = self.w.client(actor)
            for name in ("admin:accounts_user_changelist", "admin:content_news_changelist", "admin:auth_group_changelist"):
                r = c.get(reverse(name))
                self.assertIn(r.status_code, (302, 403), (actor, name))


class OtherAdminModels(AdminBase):
    def test_employee_edits_are_audited_by_field_name_only_and_employees_cannot_be_deleted(self):
        card = self.w.card
        self.change(card, "organization_employee", personal_phone="+998 90 000 11 22")
        entry = AuditLog.objects.get(action="admin_changed", object_type="Employee")
        self.assertEqual(entry.meta["fields"], ["personal_phone"])
        self.assertNotIn("998", json.dumps(entry.meta))
        self.assertEqual(self.su.post(reverse("admin:organization_employee_delete", args=[card.pk]), {"post": "yes"}).status_code, 403)
        self.assertTrue(Employee.objects.filter(pk=card.pk).exists())

    def test_a_bulk_delete_where_deletion_is_allowed_is_audited_per_object(self):
        a, b = Department.objects.create(name="Vaqtinchalik A"), Department.objects.create(name="Vaqtinchalik B")
        r = self.su.post(reverse("admin:organization_department_changelist"), {"action": "delete_selected", "_selected_action": [str(a.pk), str(b.pk)], "post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Department.objects.filter(pk__in=[a.pk, b.pk]).exists())
        rows = AuditLog.objects.filter(action="admin_deleted", object_type="Department")
        self.assertEqual({r.object_id for r in rows}, {str(a.pk), str(b.pk)})
        self.assertTrue(all(r.meta.get("bulk") for r in rows))

    def test_documents_files_and_the_journal_have_no_editing_surface_in_the_admin(self):
        from apps.documents.models import Document, DocumentVersion
        for model in (Document, DocumentVersion):
            self.assertNotIn(model, dj_admin.site._registry)
        entry = AuditLog.objects.create(action="login")
        for method, suffix in (("post", f"{entry.pk}/change/"), ("post", f"{entry.pk}/delete/"), ("post", "add/")):
            self.assertEqual(getattr(self.su, method)(f"{reverse('admin:index')}audit/auditlog/{suffix}", {"post": "yes"}).status_code, 403)
        r = self.su.post(reverse("admin:audit_auditlog_changelist"), {"action": "delete_selected", "_selected_action": [str(entry.pk)], "post": "yes"})
        self.assertTrue(AuditLog.objects.filter(pk=entry.pk).exists(), r.status_code)

    def test_the_portal_audit_page_shows_admin_actions_by_label(self):
        self.change(self.w.users["emp"], "accounts_user", is_staff="on")
        page = self.w.client("admin").get(reverse("portal:audit")).content.decode()
        self.assertIn("Django admin: yozuv o‘zgartirildi", page)


class SeedRolesIsSafe(TestCase):
    def run_cmd(self, *args):
        out, err = StringIO(), StringIO()
        call_command("seed_roles", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def perms(self, code):
        return set(Group.objects.get(name=code).permissions.values_list("pk", flat=True))

    def test_dry_run_shows_the_plan_and_changes_nothing_on_an_empty_database(self):
        Group.objects.filter(name__in=RoleCode.values).delete()
        out, err = self.run_cmd("--dry-run")
        self.assertIn("would create group", out)
        self.assertIn("role news_editor: + content.review_news", out)
        self.assertIn("DRY RUN: nothing was changed", out)
        self.assertFalse(Group.objects.filter(name__in=RoleCode.values).exists())

    def test_a_normal_run_adds_what_is_missing_and_keeps_hand_made_extras_but_reports_them(self):
        self.run_cmd()
        group = Group.objects.get(name="content_manager")
        group.permissions.add(perm("content.approve_own_news"))
        group.permissions.remove(perm("content.review_news"))
        out, err = self.run_cmd()
        self.assertIn("role content_manager: + content.review_news", out)
        self.assertIn("content_manager: = content.approve_own_news kept", err)
        self.assertIn("--prune", err)
        self.assertIn(perm("content.approve_own_news").pk, self.perms("content_manager"))     # NOT silently destroyed
        self.assertIn(perm("content.review_news").pk, self.perms("content_manager"))          # standard permission restored

    def test_the_kept_extras_are_reported_even_when_the_command_is_quiet(self):
        self.run_cmd()
        Group.objects.get(name="news_author").permissions.add(perm("content.publish_news"))
        out, err = StringIO(), StringIO()
        call_command("seed_roles", verbosity=0, stdout=out, stderr=err)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("news_author: = content.publish_news kept", err.getvalue())

    def test_prune_removes_extras_only_when_asked_and_a_dry_run_of_prune_removes_nothing(self):
        self.run_cmd()
        group = Group.objects.get(name="news_author")
        group.permissions.add(perm("content.publish_news"))
        out, err = self.run_cmd("--prune", "--dry-run")
        self.assertIn("would be removed", err)
        self.assertIn(perm("content.publish_news").pk, self.perms("news_author"))
        out, err = self.run_cmd("--prune")
        self.assertIn("REMOVED by --prune", err)
        self.assertNotIn(perm("content.publish_news").pk, self.perms("news_author"))
        self.assertEqual(self.perms("news_author"), {perm(p).pk for p in ROLE_PERMISSIONS["news_author"]})

    def test_running_it_again_with_the_same_data_changes_nothing(self):
        self.run_cmd()
        before = {g.name: self.perms(g.name) for g in Group.objects.all()}
        out, err = self.run_cmd()
        self.assertNotIn(": +", out)
        self.assertEqual(err, "")
        self.assertEqual(before, {g.name: self.perms(g.name) for g in Group.objects.all()})
        out, err = self.run_cmd("--dry-run")
        self.assertIn("The roles are up to date", out)
        self.assertEqual(self.run_cmd("--prune")[1], "")

    def test_personal_permissions_assignments_memberships_and_other_groups_survive_every_mode(self):
        self.run_cmd()
        user = make_user("keeps", role="news_editor")
        user.user_permissions.add(perm("content.approve_own_news"), perm("documents.view_document"))
        custom = Group.objects.create(name="pilot-guruh")
        custom.permissions.add(perm("content.view_news"))
        for args in ((), ("--dry-run",), ("--prune",), ("--prune", "--dry-run")):
            self.run_cmd(*args)
            user = User.objects.get(pk=user.pk)
            self.assertEqual(set(user.user_permissions.values_list("codename", flat=True)), {"approve_own_news", "view_document"}, args)
            self.assertEqual(list(user.groups.values_list("name", flat=True)), ["news_editor"], args)
            self.assertEqual(RoleAssignment.objects.filter(user=user).count(), 1, args)
            self.assertEqual(set(Group.objects.get(name="pilot-guruh").permissions.values_list("codename", flat=True)), {"view_news"}, args)
            self.assertFalse(user.is_superuser)

    def test_an_unknown_permission_in_the_definition_stops_the_command_before_any_change(self):
        from unittest import mock

        from django.core.management.base import CommandError
        from apps.access import roles
        broken = {**roles.ROLE_PERMISSIONS, RoleCode.EMPLOYEE: roles.ROLE_PERMISSIONS[RoleCode.EMPLOYEE] + ["content.no_such_permission"]}
        with mock.patch("apps.access.management.commands.seed_roles.ROLE_PERMISSIONS", broken), self.assertRaises(CommandError):
            call_command("seed_roles", verbosity=0)
        self.assertFalse(Group.objects.filter(name__in=RoleCode.values).exists())
