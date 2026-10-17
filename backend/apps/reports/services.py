"""Report data. ONE function (build_report) feeds the page and both exports, so they can never disagree about
filters or permissions.

Scope: which departments a user may report on comes from the scope of the role that carries reports.view_reports
(all = everything, department = that branch). Aggregates only, except the per-executor table, which needs
reports.view_report_people and is limited to the same scope. Documents are counted only among the documents the user
may open (apps.documents.access.visible_documents), so a count can never reveal a confidential document.
"""
import datetime
from collections import OrderedDict
from dataclasses import dataclass, field

from django import forms
from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.documents.access import visible_documents
from apps.documents.models import Document, DocumentCategory
from apps.organization.access import covered_departments_for, descendant_ids
from apps.organization.models import Department, Employee
from apps.tasks.models import Task

INPUT = {"class": "input"}


class FilterForm(forms.Form):
    date_from = forms.DateField(label=_("Boshlanish sanasi"), required=False, widget=forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"))
    date_to = forms.DateField(label=_("Tugash sanasi"), required=False, widget=forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"))
    department = forms.ModelChoiceField(label=_("Bo‘lim"), queryset=Department.objects.none(), required=False, widget=forms.Select(attrs=INPUT))
    status = forms.ChoiceField(label=_("Topshiriq holati"), required=False, choices=[("", _("Barchasi")), *Task.Status.choices], widget=forms.Select(attrs=INPUT))
    category = forms.ModelChoiceField(label=_("Hujjat turkumi"), queryset=DocumentCategory.objects.none(), required=False, widget=forms.Select(attrs=INPUT))
    period = forms.ChoiceField(label=_("Guruhlash"), required=False, choices=[("", _("Avtomatik")), ("day", _("Kunlar")), ("week", _("Haftalar")), ("month", _("Oylar"))], widget=forms.Select(attrs=INPUT))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        covered = covered_departments_for(user, "reports.view_reports")
        depts = Department.objects.filter(is_active=True)
        if covered is not None:
            depts = depts.filter(pk__in=covered)
        self.fields["department"].queryset = depts  # a department outside the user's scope is simply not a valid choice
        self.fields["category"].queryset = DocumentCategory.objects.filter(is_active=True)
        self.fields["department"].empty_label = _("Barcha bo‘limlar")
        self.fields["category"].empty_label = _("Barcha turkumlar")

    def clean(self):
        data = super().clean()
        today = timezone.localdate()
        end = data.get("date_to") or today
        start = data.get("date_from") or (end - datetime.timedelta(days=29))
        if start > end:
            raise forms.ValidationError(_("Boshlanish sanasi tugash sanasidan keyin bo‘lishi mumkin emas."))
        if (end - start).days + 1 > settings.REPORT_MAX_DAYS:
            raise forms.ValidationError(gettext("Davr %(n)d kundan oshmasligi kerak.") % {"n": settings.REPORT_MAX_DAYS})
        data["date_from"], data["date_to"] = start, end
        return data


@dataclass
class Table:
    key: str
    title: str
    columns: list
    rows: list
    total_rows: int  # before truncation
    note: str = ""

    @property
    def truncated(self):
        return self.total_rows > len(self.rows)


@dataclass
class ReportData:
    filters: dict
    period: str
    kpis: OrderedDict = field(default_factory=OrderedDict)
    tables: list = field(default_factory=list)
    timeline: list = field(default_factory=list)  # [(label, created, completed)]
    sections: set = field(default_factory=set)  # which sections the user may see: employees, tasks, documents, people
    scope_note: str = ""

    def table(self, key):
        return next((t for t in self.tables if t.key == key), None)


def _local_start(day):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def _bounds(d):
    return _local_start(d["date_from"]), _local_start(d["date_to"] + datetime.timedelta(days=1))


def _cap(rows):
    limit = settings.REPORT_MAX_ROWS
    return rows[:limit], len(rows)


def choose_period(requested, start, end):
    if requested:
        return requested
    days = (end - start).days + 1
    return "day" if days <= 62 else ("week" if days <= 200 else "month")


def _bucket_label(value, period):
    d = timezone.localtime(value).date() if isinstance(value, datetime.datetime) else value
    if period == "month":
        return d.strftime("%Y-%m")
    if period == "week":
        return d.strftime("%d.%m.%Y")
    return d.strftime("%d.%m")


def _buckets(start, end, period):
    out, cur = [], start
    if period == "week":
        cur = start - datetime.timedelta(days=start.weekday())
    if period == "month":
        cur = start.replace(day=1)
    while cur <= end:
        out.append(cur)
        if period == "day":
            cur += datetime.timedelta(days=1)
        elif period == "week":
            cur += datetime.timedelta(days=7)
        else:
            cur = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return out


def can_use_reports(user):
    return user.is_authenticated and user.is_active and user.has_perm("reports.view_reports")


def build_report(user, filters: dict) -> ReportData:
    """`filters` must be the cleaned data of FilterForm for this same user. Raises PermissionError otherwise."""
    if not can_use_reports(user):
        raise PermissionError("reports.view_reports required")
    covered = covered_departments_for(user, "reports.view_reports")  # None = everything
    dept = filters.get("department")
    if dept is not None and covered is not None and dept.pk not in covered:
        raise PermissionError("department outside scope")
    scope = None if covered is None else set(covered)  # department ids allowed
    if dept is not None:
        branch = descendant_ids(dept.pk)
        scope = branch if scope is None else (scope & branch)
    start, end = filters["date_from"], filters["date_to"]
    lo, hi = _bounds(filters)
    period = choose_period(filters.get("period"), start, end)
    status = filters.get("status") or ""
    today = timezone.localdate()
    data = ReportData(filters=filters, period=period)
    data.sections = {"employees", "tasks"}
    data.scope_note = _("Butun tashkilot") if scope is None else (gettext("Bo‘lim: %(name)s") % {"name": dept.name if dept else gettext("sizning doirangiz")})
    if user.has_perm("documents.view_document"):
        data.sections.add("documents")
    if user.has_perm("reports.view_report_people"):
        data.sections.add("people")

    # ---- employees (not archived), by department and position
    emp = Employee.objects.exclude(status=Employee.Status.ARCHIVED)
    if scope is not None:
        emp = emp.filter(department_id__in=scope)
    data.kpis["employees_active"] = emp.filter(status=Employee.Status.ACTIVE).count()
    data.kpis["employees_total"] = emp.count()
    by_dept, n = _cap([(r["department__name"], r["n"]) for r in emp.values("department__name").annotate(n=Count("pk")).order_by("-n", "department__name")])
    data.tables.append(Table("emp_dept", _("Xodimlar: bo‘limlar bo‘yicha"), [_("Bo‘lim"), _("Xodimlar")], by_dept, n))
    by_pos, n = _cap([(r["position__name"] or gettext("— (lavozim ko‘rsatilmagan)"), r["n"]) for r in emp.values("position__name").annotate(n=Count("pk")).order_by("-n", "position__name")])
    data.tables.append(Table("emp_pos", _("Xodimlar: lavozimlar bo‘yicha"), [_("Lavozim"), _("Xodimlar")], by_pos, n))

    # ---- tasks. The task set: created in the period, assignees in scope. A task with several assignees counts once in totals.
    tasks = Task.objects.filter(created_at__gte=lo, created_at__lt=hi)
    if scope is not None:
        tasks = tasks.filter(assignees__employee__department_id__in=scope).distinct()
    if status:
        tasks = tasks.filter(status=status)
    task_ids = list(tasks.values_list("pk", flat=True))
    base = Task.objects.filter(pk__in=task_ids)
    data.kpis["tasks_total"] = len(task_ids)
    data.kpis["tasks_done"] = base.filter(status=Task.Status.DONE).count()
    data.kpis["tasks_overdue_open"] = base.exclude(status__in=Task.FINAL).filter(due_date__lt=today).count()
    done_qs = base.filter(status=Task.Status.DONE, due_date__isnull=False, closed_at__isnull=False)
    late = sum(1 for due, closed in done_qs.values_list("due_date", "closed_at") if timezone.localtime(closed).date() > due)
    data.kpis["tasks_done_late"] = late
    data.kpis["tasks_done_rate"] = round(100 * data.kpis["tasks_done"] / len(task_ids)) if task_ids else 0
    counts = dict(base.values_list("status").annotate(n=Count("pk")).order_by())
    rows = [(str(label), counts.get(code, 0)) for code, label in Task.Status.choices]
    data.tables.append(Table("task_status", _("Topshiriqlar: holatlar bo‘yicha"), [_("Holat"), _("Soni")], rows, len(rows)))

    # performance by department and executor: through assignees; multi-assignee tasks count for each (stated in the note)
    link = Task.assignees.through.objects.filter(task_id__in=task_ids)
    if scope is not None:
        link = link.filter(user__employee__department_id__in=scope)
    open_overdue = Q(task__status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVIEW], task__due_date__lt=today)
    perf_dept = (
        link.values("user__employee__department__name")
        .annotate(total=Count("task_id", distinct=True), done=Count("task_id", filter=Q(task__status=Task.Status.DONE), distinct=True), overdue=Count("task_id", filter=open_overdue, distinct=True))
        .order_by("-total", "user__employee__department__name")
    )
    rows, n = _cap([(r["user__employee__department__name"] or gettext("— (bo‘limsiz)"), r["total"], r["done"], r["overdue"], f'{round(100 * r["done"] / r["total"])}%' if r["total"] else "0%") for r in perf_dept])
    data.tables.append(Table("perf_dept", _("Bajarilish: bo‘limlar bo‘yicha"), [_("Bo‘lim"), _("Jami"), _("Bajarilgan"), _("Muddati o‘tgan (ochiq)"), _("Bajarilish")], rows, n,
                             note=_("Bir nechta ijrochili topshiriq har bir ijrochining bo‘limida hisoblanadi.")))
    if "people" in data.sections:
        perf_user = (
            link.values("user__id", "user__first_name", "user__last_name", "user__username")
            .annotate(total=Count("task_id", distinct=True), done=Count("task_id", filter=Q(task__status=Task.Status.DONE), distinct=True), overdue=Count("task_id", filter=open_overdue, distinct=True))
            .order_by("-total", "user__last_name", "user__username")
        )
        rows, n = _cap([(f'{(r["user__last_name"] + " " + r["user__first_name"]).strip() or r["user__username"]}', r["total"], r["done"], r["overdue"], f'{round(100 * r["done"] / r["total"])}%' if r["total"] else "0%") for r in perf_user])
        data.tables.append(Table("perf_user", _("Bajarilish: ijrochilar bo‘yicha"), [_("Ijrochi"), _("Jami"), _("Bajarilgan"), _("Muddati o‘tgan (ochiq)"), _("Bajarilish")], rows, n,
                                 note=_("Shaxsiy natijalar: faqat ruxsati bor foydalanuvchilarga ko‘rinadi.")))

    # ---- dynamics: created (in period) and completed (closed_at in period, status done) per bucket
    trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}[period]
    created = {}
    for r in tasks.annotate(b=trunc("created_at", tzinfo=timezone.get_current_timezone())).values("b").annotate(n=Count("pk", distinct=True)).order_by():
        created[_bucket_date(r["b"], period)] = r["n"]
    done_set = Task.objects.filter(status=Task.Status.DONE, closed_at__gte=lo, closed_at__lt=hi)
    if scope is not None:
        done_set = done_set.filter(assignees__employee__department_id__in=scope).distinct()
    completed = {}
    for r in done_set.annotate(b=trunc("closed_at", tzinfo=timezone.get_current_timezone())).values("b").annotate(n=Count("pk", distinct=True)).order_by():
        completed[_bucket_date(r["b"], period)] = r["n"]
    data.kpis["tasks_completed_in_period"] = sum(completed.values())
    data.timeline = [(_bucket_label(b, period), created.get(b, 0), completed.get(b, 0)) for b in _buckets(start, end, period)]

    # ---- documents the user may open, by category and by period
    if "documents" in data.sections:
        docs = visible_documents(user).filter(created_at__gte=lo, created_at__lt=hi)
        if filters.get("category"):
            docs = docs.filter(category=filters["category"])
        docs = docs.filter(status=Document.Status.ACTIVE)
        data.kpis["documents_total"] = docs.count()
        rows, n = _cap([(gettext(r["category__name"]), r["n"]) for r in docs.values("category__name").annotate(n=Count("pk", distinct=True)).order_by("-n", "category__name")])
        data.tables.append(Table("doc_cat", _("Hujjatlar: turkumlar bo‘yicha"), [_("Turkum"), _("Hujjatlar")], rows, n,
                                 note=_("Faqat siz ko‘rishga ruxsat etilgan, faol hujjatlar hisoblanadi.")))
        per = {}
        for r in docs.annotate(b=trunc("created_at", tzinfo=timezone.get_current_timezone())).values("b").annotate(n=Count("pk", distinct=True)).order_by():
            per[_bucket_date(r["b"], period)] = r["n"]
        rows = [(_bucket_label(b, period), per[b]) for b in _buckets(start, end, period) if per.get(b)]  # only periods that have documents
        rows, n = _cap(rows)
        data.tables.append(Table("doc_period", _("Hujjatlar: davrlar bo‘yicha"), [_("Davr"), _("Hujjatlar")], rows, n, note=_("Faqat hujjat yuklangan davrlar ko‘rsatiladi.")))
    return data


def _bucket_date(value, period):
    d = timezone.localtime(value).date() if isinstance(value, datetime.datetime) else value
    if period == "week":
        d -= datetime.timedelta(days=d.weekday())
    elif period == "month":
        d = d.replace(day=1)
    return d

