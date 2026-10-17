"""Who may see which part of an employee record.

Three tiers of fields, each guarded by its own permission AND a scope:
  directory  name, department, position, status        permission view_employee_directory
  contacts   work phone / e-mail                        permission view_employee_contacts
  private    hire date, personal phone, birth date      permission view_employee_private
A person always sees their own record in full. Scope comes from the user's RoleAssignment rows: "all" covers every
department, "department" covers that department and the ones below it. Superusers see everything.
"""
from apps.access.models import RoleAssignment

from .models import Department, Employee

DIRECTORY_FIELDS = ("last_name", "first_name", "middle_name", "department", "position", "status")
CONTACT_FIELDS = ("work_phone", "work_email")
PRIVATE_FIELDS = ("hired_at", "personal_phone", "birth_date")
TIER_FIELDS = {"directory": DIRECTORY_FIELDS, "contacts": CONTACT_FIELDS, "private": PRIVATE_FIELDS}
PERMISSION = {
    "directory": "organization.view_employee_directory",
    "contacts": "organization.view_employee_contacts",
    "private": "organization.view_employee_private",
}


def descendant_ids(department_id):
    ids, frontier = {department_id}, [department_id]
    while frontier:
        children = list(Department.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        frontier = [c for c in children if c not in ids]
        ids.update(frontier)
    return ids


def covered_departments(user, tier):
    """None = every department; otherwise the set of department ids the user's roles cover for this tier."""
    return covered_departments_for(user, PERMISSION[tier])


def covered_departments_for(user, permission):
    """Same, for any permission ("app.codename"): the scope of the role assignments whose role carries it."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return set()
    if user.is_superuser:
        return None
    app, codename = permission.split(".")
    covered = set()
    assignments = RoleAssignment.objects.filter(
        user=user, role__permissions__content_type__app_label=app, role__permissions__codename=codename
    ).distinct()
    for a in assignments:
        if a.scope == RoleAssignment.Scope.ALL:
            return None
        if a.scope == RoleAssignment.Scope.DEPARTMENT and a.department_id:
            covered |= descendant_ids(a.department_id)
    return covered


def visible_tiers(user, employee) -> set:
    """Tiers of `employee` that `user` may read."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return set()
    tiers = set()
    if employee.user_id and employee.user_id == user.pk:
        tiers = {"directory", "contacts", "private"}
    for tier in ("directory", "contacts", "private"):
        if tier in tiers:
            continue
        if not user.has_perm(PERMISSION[tier]):
            continue
        covered = covered_departments(user, tier)
        if covered is None or employee.department_id in covered:
            tiers.add(tier)
    return tiers


def directory_queryset(user):
    """Employees the user may list. Archived records are for people who can edit employees."""
    if not user.has_perm(PERMISSION["directory"]):
        return Employee.objects.none()
    qs = Employee.objects.select_related("department", "position")
    if not user.has_perm("organization.change_employee"):
        qs = qs.exclude(status=Employee.Status.ARCHIVED)
    return qs
