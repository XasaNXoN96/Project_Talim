"""Statistics by school (education institution) for the people who see the whole organisation.

A school receives its tasks through its director (the only person who signs in from a school), so a task counts for a school when one of the
school's director accounts is an assignee; a task given to several schools counts for each (as in the other reports). Whole history, no period:
a task that is overdue stays visible until it is closed. Staff are counted, never named (personal data)."""
from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone

from apps.achievements.models import Achievement
from apps.organization.access import covered_departments_for
from apps.organization.models import Employee, Institution
from apps.tasks.models import Task

S = Task.Status


def can_see_schools(user):
    """Organisation-wide reporting right: the same scope rule as the other reports (a department head sees only their branch, so not this)."""
    return user.is_authenticated and user.is_active and user.has_perm("reports.view_reports") and covered_departments_for(user, "reports.view_reports") is None


@dataclass
class SchoolRow:
    institution: Institution
    directors: int = 0  # active director accounts
    staff: int = 0
    tasks: int = 0
    done: int = 0
    open: int = 0
    overdue: int = 0  # open and past the deadline
    late: int = 0  # done, but after the deadline
    ach: dict = field(default_factory=dict)  # status -> count

    @property
    def rate(self):
        counted = self.tasks - self._cancelled
        return round(100 * self.done / counted) if counted else None

    _cancelled: int = 0

    @property
    def ach_total(self):
        return sum(self.ach.values())

    @property
    def ach_pending(self):
        return self.ach.get(Achievement.Status.SUBMITTED, 0)

    @property
    def ach_published(self):
        return self.ach.get(Achievement.Status.PUBLISHED, 0)


def school_tasks(institution_ids=None):
    """[(institution_id, Task)] one row per (school, task): the task, as seen through the school's active director accounts."""
    User = get_user_model()
    dirs = User.objects.filter(role_assignments__role__name="school_director", employee__institution__isnull=False)
    if institution_ids is not None:
        dirs = dirs.filter(employee__institution_id__in=institution_ids)
    owner = {uid: inst for uid, inst in dirs.values_list("pk", "employee__institution_id")}
    if not owner:
        return []
    links = Task.assignees.through.objects.filter(user_id__in=owner).select_related("task").order_by("task__due_date", "task__created_at")
    seen, out = set(), []
    for link in links:
        key = (owner[link.user_id], link.task_id)
        if key not in seen:  # two director accounts of one school do not double the task
            seen.add(key)
            out.append((owner[link.user_id], link.task))
    return out


def build_rows():
    rows = {i.pk: SchoolRow(i) for i in Institution.objects.all()}
    User = get_user_model()
    for inst_id in User.objects.filter(is_active=True, role_assignments__role__name="school_director", employee__institution__isnull=False).values_list("employee__institution_id", flat=True).distinct():
        if inst_id in rows:
            rows[inst_id].directors = User.objects.filter(is_active=True, role_assignments__role__name="school_director", employee__institution_id=inst_id).distinct().count()
    for inst_id, n in Employee.objects.exclude(status=Employee.Status.ARCHIVED).filter(institution__isnull=False).values_list("institution_id").annotate(n=Count("pk")).order_by():
        rows[inst_id].staff = n
    for inst_id, task in school_tasks():
        r = rows.get(inst_id)
        if r is None:
            continue
        r.tasks += 1
        if task.status == S.CANCELLED:
            r._cancelled += 1
        elif task.status == S.DONE:
            r.done += 1
            if task.deadline and task.closed_at and task.closed_at > task.deadline:
                r.late += 1
        else:
            r.open += 1
            if task.is_overdue:
                r.overdue += 1
    for inst_id, status, n in Achievement.objects.values_list("institution_id", "status").annotate(n=Count("pk")).order_by():
        rows[inst_id].ach[status] = n
    return sorted(rows.values(), key=lambda r: (-r.overdue, r.institution.name.lower()))


def totals(rows):
    t = SchoolRow(institution=None)
    for r in rows:
        t.tasks += r.tasks; t.done += r.done; t.open += r.open; t.overdue += r.overdue; t.late += r.late; t.staff += r.staff; t.directors += r.directors
        t._cancelled += r._cancelled
        for k, v in r.ach.items():
            t.ach[k] = t.ach.get(k, 0) + v
    return t
