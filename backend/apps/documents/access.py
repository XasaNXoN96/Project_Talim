"""Document visibility. Evaluated on the server for every list, view and download.

  general       every signed-in user holding documents.view_document
  department    people whose employee record sits in the document's department or below it, plus the author
  confidential  the author and holders of documents.view_confidential_document
documents.view_all_documents adds every non-confidential document. Archived documents are visible to the author and
to holders of view_all_documents only.
"""
from django.db.models import Q

from apps.organization.models import Department

from .models import Document


def _ancestor_ids(department_id):
    ids = set()
    while department_id and department_id not in ids:
        ids.add(department_id)
        department_id = Department.objects.filter(pk=department_id).values_list("parent_id", flat=True).first()
    return ids


def _user_department_id(user):
    employee = getattr(user, "employee", None) if user.is_authenticated else None
    return employee.department_id if employee else None


def visible_documents(user):
    if not user.is_authenticated or not user.is_active or not user.has_perm("documents.view_document"):
        return Document.objects.none()
    if user.is_superuser:
        return Document.objects.all()
    see_all = user.has_perm("documents.view_all_documents")
    see_conf = user.has_perm("documents.view_confidential_document")
    own = Q(created_by=user)
    levels = Q(access_level=Document.Access.GENERAL)
    dept_id = _user_department_id(user)
    if dept_id:
        levels |= Q(access_level=Document.Access.DEPARTMENT, department_id__in=_ancestor_ids(dept_id))
    if see_all:
        levels |= Q(access_level__in=[Document.Access.GENERAL, Document.Access.DEPARTMENT])
    if see_conf:
        levels |= Q(access_level=Document.Access.CONFIDENTIAL)
    active = Q(status=Document.Status.ACTIVE)
    archived_ok = Q(status=Document.Status.ARCHIVED) if see_all else Q(pk__in=[])  # the author is covered by `own`
    return Document.objects.filter(own | (levels & (active | archived_ok))).distinct()


def can_view(user, document):
    return visible_documents(user).filter(pk=document.pk).exists()


def can_edit(user, document):
    return (
        user.has_perm("documents.change_document")
        and (document.created_by_id == user.pk or user.has_perm("documents.view_all_documents") or user.is_superuser)
        and can_view(user, document)
    )


def can_add(user):
    return user.has_perm("documents.add_document")
