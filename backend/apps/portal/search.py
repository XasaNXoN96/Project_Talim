"""Global search of the portal: one box, five sources. NOT full-text search.

What it really does: case-insensitive substring matching ("contains") on a few named fields of each source, every word of
the query must match (in any of the fields), results are ordered by a fixed rule (no relevance ranking, no stemming, no
typo tolerance, no Latin/Cyrillic transliteration). Each source is limited by the SAME rules as its own section:

  employees    directory fields only (name, position), people the staff directory lists for this user      [view_employee_directory]
  departments  name                                                                                       [view_department]
  tasks        title, description of tasks this user may open                                             [tasks access rules]
  documents    title, number, description of ACTIVE documents this user may open (all access levels apply)[documents access rules]
  news         title, excerpt of PUBLISHED news (the public site)                                         [any signed-in user]

Never searched: phones, e-mails, birth dates and other contact/private fields, comments, attachment and document file
names and contents, audit log, users, notifications, drafts and archived items."""
import re

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.content.models import News
from apps.documents import access as doc_access
from apps.documents.models import Document
from apps.organization import access as org_access
from apps.organization.models import Department
from apps.tasks import access as task_access

MIN_LEN, MAX_LEN, MAX_WORDS = 2, 100, 5
PREVIEW, PAGE_SIZE = 5, 20
KINDS = ("employees", "departments", "tasks", "documents", "news")
LABELS = {"employees": _("Xodimlar"), "departments": _("Bo‘limlar"), "tasks": _("Topshiriqlar"), "documents": _("Hujjatlar"), "news": _("Yangiliklar")}


def clean_query(raw):
    """-> (query text, words). Whitespace collapsed, length and word count bounded; shorter than MIN_LEN gives no words."""
    text = "".join(ch for ch in (raw or "") if ch.isprintable() or ch in " \t\n")  # control characters (incl. NUL, which PostgreSQL refuses) are dropped
    text = re.sub(r"\s+", " ", text).strip()[:MAX_LEN]
    words = [w for w in text.split(" ") if w][:MAX_WORDS]
    if len(text) < MIN_LEN:
        return text, []
    return text, words


def _match(words, fields):
    q = Q()
    for w in words:
        part = Q()
        for f in fields:
            part |= Q(**{f"{f}__icontains": w})
        q &= part
    return q


def source(user, kind, words):
    """Queryset for one source, already limited to what `user` may see; None when the user has no access to the source at all."""
    if kind == "employees":
        if not user.has_perm("organization.view_employee_directory"):
            return None
        qs = org_access.directory_queryset(user)
        return qs.filter(_match(words, ["last_name", "first_name", "middle_name", "position__name"])).order_by("last_name", "first_name")
    if kind == "departments":
        if not user.has_perm("organization.view_department"):
            return None
        return Department.objects.filter(_match(words, ["name"])).select_related("parent").order_by("name")
    if kind == "tasks":
        if not user.has_perm("tasks.view_task"):
            return None
        return task_access.visible_tasks(user).filter(_match(words, ["title", "description"])).order_by("-created_at")
    if kind == "documents":
        if not user.has_perm("documents.view_document"):
            return None
        return doc_access.visible_documents(user).filter(status=Document.Status.ACTIVE).filter(_match(words, ["title", "number", "description"])).select_related("category").order_by("-doc_date", "-created_at")
    if kind == "news":
        return News.objects.published().filter(_match(words, ["title", "excerpt"])).select_related("category").order_by("-publish_at")
    raise ValueError(kind)


def describe(user, kind, obj):
    """{"title", "subtitle", "url"}: url is None when the user may not open the target page (the name is still theirs to see)."""
    from django.urls import reverse
    from django.utils.formats import date_format

    if kind == "employees":
        opens = "directory" in org_access.visible_tiers(user, obj)
        sub = " · ".join(x for x in (obj.department.name, obj.position.name if obj.position else "", obj.get_status_display()) if x)
        return {"title": f"{obj.last_name} {obj.first_name} {obj.middle_name}".strip(), "subtitle": sub, "url": reverse("employees:detail", args=[obj.pk]) if opens else None}
    if kind == "departments":
        if user.has_perm("organization.change_department"):
            url = reverse("employees:department_edit", args=[obj.pk])
        elif user.has_perm("organization.view_employee_directory"):
            url = reverse("employees:list") + f"?department={obj.pk}"
        else:
            url = reverse("employees:structure")
        return {"title": obj.name, "subtitle": obj.parent.name if obj.parent else "", "url": url}
    if kind == "tasks":
        return {"title": obj.title, "subtitle": obj.get_status_display(), "url": reverse("tasks:detail", args=[obj.pk])}
    if kind == "documents":
        return {"title": obj.title, "subtitle": " · ".join(x for x in (str(obj.category), obj.number) if x), "url": reverse("documents:detail", args=[obj.pk])}
    return {"title": obj.title, "subtitle": " · ".join(x for x in (obj.category.name if obj.category else "", date_format(obj.publish_at, "d.m.Y")) if x), "url": reverse("content:news_detail", args=[obj.slug])}
