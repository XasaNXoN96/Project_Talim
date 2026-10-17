from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.organization.models import Department

from .models import RoleAssignment
from .roles import ROLE_PERMISSIONS, RoleCode
from .services import has_role, user_role_names

User = get_user_model()


def make_user(name="bob"):
    return User.objects.create_user(name, f"{name}@example.test", "Namuna-Parol-12345")


class SeedRolesTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)

    def test_creates_exactly_the_defined_roles(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(RoleCode.values))

    def test_is_idempotent(self):
        before = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        call_command("seed_roles", verbosity=0)
        after = {g.name: set(g.permissions.values_list("pk", flat=True)) for g in Group.objects.all()}
        self.assertEqual(before, after)
        self.assertEqual(Group.objects.count(), len(RoleCode.values))

    def test_permissions_match_the_mapping_exactly(self):
        for code, dotted in ROLE_PERMISSIONS.items():
            group = Group.objects.get(name=code)
            actual = {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.select_related("content_type")}
            self.assertEqual(actual, set(dotted), msg=code)

    def test_no_role_gets_dangerous_permissions(self):
        forbidden_apps = {"auth", "admin", "sessions", "contenttypes"}
        for group in Group.objects.all():
            for perm in group.permissions.select_related("content_type"):
                self.assertNotIn(perm.content_type.app_label, forbidden_apps, msg=f"{group.name}: {perm}")
                self.assertFalse(perm.codename.startswith("delete_"), msg=f"{group.name}: {perm}")
        admin_perms = {f"{p.content_type.app_label}.{p.codename}" for p in Group.objects.get(name="admin").permissions.select_related("content_type")}
        self.assertNotIn("accounts.change_user", admin_perms)
        self.assertNotIn("accounts.add_user", admin_perms)

    def test_employee_role_can_only_read_the_directory_and_structure(self):
        perms = {f"{p.content_type.app_label}.{p.codename}" for p in Group.objects.get(name="employee").permissions.select_related("content_type")}
        self.assertEqual(perms, {"organization.view_employee_directory", "organization.view_department", "organization.view_position"})
        for forbidden in ("view_employee_contacts", "view_employee_private", "add_employee", "change_employee"):
            self.assertNotIn("organization." + forbidden, perms)


class RoleAssignmentTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.user = make_user()
        self.dept = Department.objects.create(name="Metodik bo‘lim")
        self.hr = Group.objects.get(name="hr")

    def test_department_scope_requires_department(self):
        with self.assertRaises(ValidationError):
            RoleAssignment(user=self.user, role=self.hr, scope="department").save()

    def test_own_and_all_scope_reject_department(self):
        for scope in ("own", "all"):
            with self.assertRaises(ValidationError):
                RoleAssignment(user=self.user, role=self.hr, scope=scope, department=self.dept).save()

    def test_database_enforces_scope_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.bulk_create([RoleAssignment(user=self.user, role=self.hr, scope="department")])

    def test_duplicate_assignment_rejected(self):
        RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")

    def test_assignment_adds_user_to_group_and_grants_permission(self):
        self.assertFalse(self.user.has_perm("organization.add_employee"))
        RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        user = User.objects.get(pk=self.user.pk)  # fresh instance: permission cache
        self.assertIn("hr", user_role_names(user))
        self.assertTrue(user.has_perm("organization.add_employee"))

    def test_revoking_removes_group_membership(self):
        assignment = RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        assignment.delete()
        self.assertFalse(self.user.groups.filter(name="hr").exists())

    def test_group_kept_while_another_assignment_of_same_role_remains(self):
        first = RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        RoleAssignment.objects.create(user=self.user, role=self.hr, scope="department", department=self.dept)
        first.delete()
        self.assertTrue(self.user.groups.filter(name="hr").exists())

    def test_deleting_user_cascades_cleanly(self):
        RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        self.user.delete()
        self.assertFalse(RoleAssignment.objects.exists())

    def test_cannot_change_role_of_existing_assignment(self):
        assignment = RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        assignment.role = Group.objects.get(name="admin")
        with self.assertRaises(ValueError):
            assignment.save()

    def test_assignment_and_revocation_are_audited(self):
        assignment = RoleAssignment.objects.create(user=self.user, role=self.hr, scope="all")
        assignment.delete()
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertIn(AuditLog.Action.ROLE_ASSIGNED, actions)
        self.assertIn(AuditLog.Action.ROLE_REVOKED, actions)


class HasRoleServiceTests(TestCase):
    def setUp(self):
        call_command("seed_roles", verbosity=0)
        self.user = make_user()
        self.dept_a = Department.objects.create(name="A")
        self.dept_b = Department.objects.create(name="B")
        self.head = Group.objects.get(name="department_head")

    def test_all_scope_covers_any_department(self):
        RoleAssignment.objects.create(user=self.user, role=self.head, scope="all")
        self.assertTrue(has_role(self.user, "department_head", department=self.dept_a))
        self.assertTrue(has_role(self.user, "department_head", department=self.dept_b))

    def test_department_scope_covers_only_that_department(self):
        RoleAssignment.objects.create(user=self.user, role=self.head, scope="department", department=self.dept_a)
        self.assertTrue(has_role(self.user, "department_head", department=self.dept_a))
        self.assertFalse(has_role(self.user, "department_head", department=self.dept_b))

    def test_own_scope_covers_no_department(self):
        RoleAssignment.objects.create(user=self.user, role=self.head, scope="own")
        self.assertTrue(has_role(self.user, "department_head"))
        self.assertFalse(has_role(self.user, "department_head", department=self.dept_a))

    def test_inactive_and_anonymous_have_no_role(self):
        from django.contrib.auth.models import AnonymousUser

        RoleAssignment.objects.create(user=self.user, role=self.head, scope="all")
        self.user.is_active = False
        self.user.save()
        self.assertFalse(has_role(self.user, "department_head"))
        self.assertFalse(has_role(AnonymousUser(), "department_head"))
        self.assertEqual(user_role_names(AnonymousUser()), set())
