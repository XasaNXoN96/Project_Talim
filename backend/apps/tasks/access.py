"""Who may see, edit and move a task. The scope comes from the roles' assignments (apps.organization.access)."""
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.organization.access import covered_departments_for

from .models import Task

User = get_user_model()


def _department_filter(prefix, covered):
    return Q(**{f"{prefix}__employee__department_id__in": covered})


def visible_tasks(user):
    """Own tasks (creator or assignee) plus, for managers, tasks of people in the departments their role covers."""
    if not user.is_authenticated or not user.is_active or not user.has_perm("tasks.view_task"):
        return Task.objects.none()
    qs = Task.objects.all()
    if user.has_perm("tasks.view_department_tasks"):
        covered = covered_departments_for(user, "tasks.view_department_tasks")
        if covered is None:
            return qs
        if covered:
            return qs.filter(Q(created_by=user) | Q(assignees=user) | _department_filter("assignees", covered)).distinct()
    return qs.filter(Q(created_by=user) | Q(assignees=user)).distinct()


def can_view(user, task):
    return visible_tasks(user).filter(pk=task.pk).exists()


def manages(user, task):
    """True for the creator, and for managers whose role covers the task through the assignees' departments."""
    if task.created_by_id == user.pk:
        return True
    if not user.has_perm("tasks.view_department_tasks"):
        return False
    covered = covered_departments_for(user, "tasks.view_department_tasks")
    if covered is None:
        return True
    return bool(covered) and task.assignees.filter(employee__department_id__in=covered).exists()


def can_edit(user, task):
    return user.has_perm("tasks.change_task") and task.status not in Task.FINAL and manages(user, task)


def assignable_users(user):
    """People this user may give a task to. Department heads: members of their department branch (and themselves)."""
    if not user.has_perm("tasks.add_task"):
        return User.objects.none()
    qs = User.objects.filter(is_active=True).order_by("last_name", "first_name", "username")
    covered = covered_departments_for(user, "tasks.add_task")
    if covered is None:
        return qs
    return qs.filter(Q(pk=user.pk) | Q(employee__department_id__in=covered)).distinct()


def allowed_transitions(user, task):
    """Statuses `user` may move the task to right now."""
    S = Task.Status
    if task.status in Task.FINAL:
        return set()
    allowed = set()
    is_assignee = task.assignees.filter(pk=user.pk).exists()
    if is_assignee:
        if task.status == S.NEW:
            allowed.add(S.IN_PROGRESS)
        if task.status in (S.NEW, S.IN_PROGRESS):
            allowed.add(S.REVIEW)
    if user.has_perm("tasks.change_task") and manages(user, task):
        allowed.add(S.CANCELLED)
        if task.status == S.REVIEW:
            allowed |= {S.DONE, S.IN_PROGRESS}
    return allowed
