"""Generated acceptance matrix: EVERY application route x EVERY actor x several HTTP methods.

What it proves, from the live URLconf (so a route added tomorrow is covered automatically):
  * nothing ever answers 5xx, whoever asks and however (wrong method, empty body, tampered identifiers);
  * a route that declares a permission answers 403 to a signed-in user who lacks it, for every method;
  * anonymous visitors never get a 2xx from a protected route;
  * PUT/PATCH/DELETE never succeed anywhere;
  * every state-changing POST route rejects a request without a CSRF token, for every actor (the CSP report sink excepted);
  * reading (GET/HEAD/OPTIONS) never changes data.
"""
import uuid

from django.test import TestCase
from django.urls import reverse

from apps.content.models import News, NewsCategory
from apps.documents.models import Document
from apps.notifications.models import Notification
from apps.organization.models import Department, Employee, EmployeeImport, Position
from apps.tasks.models import Task, TaskAttachment

from .acceptance import ACTORS, World, app_routes, required_permissions

PUBLIC = {"healthz", "csp_report", "set_language", "content:home", "content:news_list", "content:news_detail", "content:news_cover", "achievements_public:list", "achievements_public:detail", "achievements_public:image", "achievements_public:video", "gallery_public:list", "gallery_public:file", "accounts:login", "accounts:logout",
          "accounts:two_factor_verify", "accounts:two_factor_setup", "accounts:password_reset", "accounts:password_reset_done",
          "accounts:password_reset_confirm", "accounts:password_reset_complete", "accounts:password_change"}
CSRF_EXEMPT = {"csp_report"}
WRITE_METHODS = ("put", "patch", "delete")


def snapshot():
    # UserSession is deliberately absent: it is bookkeeping that signing in and any authenticated request refresh (see apps.accounts.sessions)
    from django.contrib.auth import get_user_model

    U = get_user_model()
    return {
        "tasks": list(Task.objects.order_by("pk").values_list("pk", "status", "title")),
        "docs": list(Document.objects.order_by("pk").values_list("pk", "status", "title", "access_level")),
        "users": list(U.objects.order_by("pk").values_list("pk", "is_active", "must_change_password", "email")),
        "notes": list(Notification.objects.order_by("pk").values_list("pk", "read_at")),
        "emps": list(Employee.objects.order_by("pk").values_list("pk", "status", "last_name")),
        "imports": list(EmployeeImport.objects.order_by("pk").values_list("pk", "status")),
        "news": list(News.objects.order_by("pk").values_list("pk", "status", "title", "publish_at")),
        "newscat": list(NewsCategory.objects.order_by("pk").values_list("pk", "name")),
        "att": list(TaskAttachment.objects.order_by("pk").values_list("pk", "removed_at")),
        "depts": list(Department.objects.order_by("pk").values_list("pk", "name", "is_active")),
        "pos": list(Position.objects.order_by("pk").values_list("pk", "name")),
        "roles": [(a.user_id, a.role_id) for a in __import__("apps.access.models", fromlist=["RoleAssignment"]).RoleAssignment.objects.order_by("pk")],
    }


class RouteMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = World()
        cls.routes = app_routes()

    def url(self, name):
        return reverse(name, kwargs=self.w.kwargs_for(name))

    def test_the_inventory_is_not_empty_and_every_route_is_classified(self):
        names = {n for n, _ in self.routes}
        self.assertGreater(len(names), 60)
        # a route that is neither public, nor login-protected, nor permission-protected would be a forgotten door
        for name, cls in self.routes:
            if name in PUBLIC:
                continue
            mixins = {b.__name__ for b in cls.__mro__} if cls else set()
            self.assertTrue({"PortalPermissionMixin", "LoginRequiredMixin"} & mixins, f"{name} has no access control")

    def test_no_route_ever_answers_5xx_and_permissions_hold_for_every_actor_and_method(self):
        failures = []
        for actor in ACTORS:
            for name, cls in self.routes:
                url = self.url(name)
                needed = required_permissions(name, cls)
                user = self.w.users.get(actor)
                lacks = bool(user) and not all(user.has_perm(p) for p in needed) if needed else False
                c = self.w.client(actor)
                for method in ("get", "head", "options", "post", "put", "patch", "delete"):
                    if name == "accounts:logout" and method == "post":
                        continue  # a real sign-out would end the actor's session mid-matrix
                    if method == "post" and not lacks and actor != "anon":
                        continue  # authorised writes are exercised by the flow tests, not with empty bodies
                    if method == "post" and actor == "anon":
                        continue  # anonymous POSTs are covered by the CSRF test below
                    r = getattr(c, method)(url)
                    status = r.status_code
                    tag = f"{actor} {method.upper()} {name}"
                    if status >= 500:
                        failures.append(f"{tag} -> {status}")
                    if method in WRITE_METHODS:
                        if status != 405:  # rejected centrally, before authentication or permissions are even consulted
                            failures.append(f"{tag} -> {status} (expected 405)")
                        continue
                    if actor == "anon" and name not in PUBLIC and 200 <= status < 300:
                        failures.append(f"{tag} -> {status} (anonymous reached a protected route)")
                    if actor != "anon" and lacks and name not in PUBLIC and status != 403:
                        failures.append(f"{tag} -> {status} (lacks {needed}, expected 403)")
        if failures:
            import collections, re
            groups = collections.Counter(re.sub(r'^\S+ ', '', f) for f in failures)
            print('\nMATRIX FAILURES BY ROUTE/METHOD:')
            for k, v in sorted(groups.items()): print(f'  {v:3d}x {k}')
        self.assertEqual(failures, [])

    def test_only_get_head_options_and_post_are_ever_accepted(self):
        c = self.w.client("admin")
        for name, _cls in self.routes:
            for method in ("put", "patch", "delete", "trace"):
                r = getattr(c, method)(self.url(name))
                self.assertEqual(r.status_code, 405, (name, method))
                self.assertIn("POST", r["Allow"])

    def test_every_post_route_enforces_csrf_for_every_actor(self):
        failures = []
        for actor in ACTORS:
            c = self.w.client(actor, csrf=True)
            for name, cls in self.routes:
                if name in CSRF_EXEMPT or name == "accounts:logout" and actor == "anon":
                    continue
                r = c.post(self.url(name), {})
                if r.status_code != 403 and not (name in {"healthz"} and r.status_code == 405):
                    failures.append(f"{actor} POST {name} without a CSRF token -> {r.status_code}")
        self.assertEqual(failures, [])

    def test_reading_never_changes_data(self):
        before = snapshot()
        for actor in ACTORS:
            c = self.w.client(actor)
            for name, _cls in self.routes:
                if name == "accounts:logout":
                    continue
                for method in ("get", "head", "options"):
                    getattr(c, method)(self.url(name))
        self.assertEqual(snapshot(), before)

    def test_tampered_identifiers_never_crash_or_leak(self):
        ghost = uuid.uuid4()
        c = self.w.client("admin")
        for name, cls in self.routes:
            kwargs = self.w.kwargs_for(name)
            if not kwargs:
                continue
            tampered = {k: (ghost if k in {"pk", "attachment_id", "assignment_id"} else v) for k, v in kwargs.items()}
            if "number" in tampered:
                tampered["number"] = 999
            if "status" in tampered:
                tampered["status"] = "no-such-status"
            if "action" in tampered:
                tampered["action"] = "no-such-action"
            if "fmt" in tampered:
                tampered["fmt"] = "exe"
            if "slug" in tampered:
                tampered["slug"] = "no-such-slug"
            if "variant" in tampered:
                tampered["variant"] = "no-such-variant"
            if "decision" in tampered:
                tampered["decision"] = "no-such-decision"
            if "step" in tampered:
                tampered["step"] = "no-such-step"
            if "section" in tampered:
                tampered["section"] = "no-such-section"
            if "token" in tampered:
                tampered["token"] = "bad-token"
            for method in ("get", "post"):
                r = getattr(c, method)(reverse(name, kwargs=tampered))
                self.assertLess(r.status_code, 500, (name, method, tampered))
                if method == "post" and name != "accounts:password_reset_confirm":  # an invalid reset link shows its explanatory page
                    self.assertNotEqual(r.status_code, 200, (name, method))
                if r.status_code == 200 and method == "get" and name not in {"accounts:password_reset_confirm"}:
                    self.fail(f"GET {name} with a non-existent identifier returned 200")

    def test_identifier_swaps_between_objects_are_refused(self):
        """An object id used under another object's URL (attachment of task B under task A, version of doc B under doc A)."""
        other_task = Task.objects.create(title="Boshqa", created_by=self.w.users["admin"])
        other_task.assignees.set([self.w.users["emp"]])
        c = self.w.client("admin")
        r = c.get(reverse("tasks:attachment_download", kwargs={"pk": other_task.pk, "attachment_id": self.w.attachment.pk}))
        self.assertEqual(r.status_code, 404)
        r = c.post(reverse("tasks:attachment_remove", kwargs={"pk": other_task.pk, "attachment_id": self.w.attachment.pk}))
        self.assertEqual(r.status_code, 404)
        r = c.get(reverse("documents:download_version", kwargs={"pk": self.w.doc.pk, "number": 2}))
        self.assertEqual(r.status_code, 404)

    def test_the_django_admin_is_closed_to_everyone_except_superusers(self):
        for actor in ACTORS:
            c = self.w.client(actor)
            for path in ("/admin/", "/admin/accounts/user/", "/admin/audit/auditlog/", "/admin/organization/employee/add/", "/admin/auth/group/"):
                r = c.get(path, follow=True)
                if actor == "superuser":
                    self.assertEqual(r.status_code, 200, (actor, path))
                elif actor == "anon":
                    self.assertTrue(r.redirect_chain[-1][0].startswith("/accounts/login/"), (actor, path, r.redirect_chain))
                else:
                    self.assertEqual(r.status_code, 403, (actor, path))
                r = c.post(path, {}, follow=True)
                self.assertLess(r.status_code, 500)
        # the audit log stays read-only even for a superuser
        su = self.w.client("superuser")
        self.assertEqual(su.get("/admin/audit/auditlog/add/").status_code, 403)
        self.assertEqual(su.post("/admin/audit/auditlog/", {"action": "delete_selected", "_selected_action": []}).status_code, 200)
