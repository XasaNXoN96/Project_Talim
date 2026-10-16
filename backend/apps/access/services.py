from .models import RoleAssignment


def user_role_names(user) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


def has_role(user, role_code, *, department=None) -> bool:
    """True if the user holds `role_code` with a scope that covers `department`.

    scope=all covers everything; scope=department covers exactly that department; scope=own covers no department
    (callers check ownership of the object themselves).
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    assignments = RoleAssignment.objects.filter(user=user, role__name=str(role_code))
    if department is None:
        return assignments.exists()
    return assignments.filter(scope=RoleAssignment.Scope.ALL).exists() or assignments.filter(
        scope=RoleAssignment.Scope.DEPARTMENT, department=department
    ).exists()
