"""Role definitions (see docs/ROLES_PERMISSIONS.md).

A role is a Django Group. Group permissions are the *global* part of access control; the scope
(own / department / all) is stored in RoleAssignment and checked in services. The mapping below starts small
and grows module by module — `employee` has no extra permissions yet because no employee-facing modules exist.
Guests are anonymous users and have no role.
"""
from django.db import models


class RoleCode(models.TextChoices):
    EMPLOYEE = "employee", "Xodim"
    DEPARTMENT_HEAD = "department_head", "Bo‘lim boshlig‘i"
    CONTENT_MANAGER = "content_manager", "Kontent-menejer"
    HR = "hr", "Kadrlar bo‘limi"
    ADMIN = "admin", "Administrator"
    SYSADMIN = "sysadmin", "Tizim administratori"


_CONTENT = [
    "content.view_newscategory", "content.add_newscategory", "content.change_newscategory",
    "content.view_news", "content.add_news", "content.change_news", "content.publish_news",
]
_ORG_VIEW = ["organization.view_department", "organization.view_position"]
_DIRECTORY = ["organization.view_employee_directory"]
_CONTACTS = ["organization.view_employee_contacts"]
_PRIVATE = ["organization.view_employee_private"]
_ORG_WRITE = [
    "organization.add_department", "organization.change_department",
    "organization.add_position", "organization.change_position",
    "organization.add_employee", "organization.change_employee",
    "organization.view_institution", "organization.add_institution", "organization.change_institution",
]
_TASKS_BASIC = ["tasks.view_task", "tasks.add_taskcomment", "tasks.add_taskattachment", "tasks.remove_taskattachment"]
_TASKS_MANAGE = ["tasks.add_task", "tasks.change_task", "tasks.view_department_tasks"]
_DOCS_VIEW = ["documents.view_document", "documents.view_documentcategory"]
_DOCS_WRITE = ["documents.add_document", "documents.change_document"]
_DOCS_ALL = ["documents.view_all_documents", "documents.view_confidential_document"]
_USER_ADMIN = ["accounts.view_user", "accounts.manage_users", "accounts.assign_roles", "accounts.unlock_accounts"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Contacts/private data are further limited by SCOPE (own / department / all) in apps.organization.access.
    RoleCode.EMPLOYEE: _DIRECTORY + _ORG_VIEW + _TASKS_BASIC + _DOCS_VIEW,
    RoleCode.DEPARTMENT_HEAD: _DIRECTORY + _CONTACTS + _ORG_VIEW + _TASKS_BASIC + _TASKS_MANAGE + _DOCS_VIEW + _DOCS_WRITE,
    RoleCode.CONTENT_MANAGER: _CONTENT + ["organization.view_institution"] + _TASKS_BASIC + _DOCS_VIEW,
    RoleCode.HR: _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + ["accounts.view_user"] + _TASKS_BASIC + ["tasks.add_task"] + _DOCS_VIEW + _DOCS_WRITE + _DOCS_ALL,
    RoleCode.ADMIN: _CONTENT + _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + _USER_ADMIN + ["audit.view_auditlog"] + _TASKS_BASIC + _TASKS_MANAGE + _DOCS_VIEW + _DOCS_WRITE + _DOCS_ALL,
    RoleCode.SYSADMIN: ["audit.view_auditlog"],
}


# The scope is fixed per role (not chosen per assignment): one less thing to get wrong.
ROLE_SCOPE = {
    RoleCode.EMPLOYEE: "own",
    RoleCode.DEPARTMENT_HEAD: "department",  # needs a department
    RoleCode.CONTENT_MANAGER: "all",
    RoleCode.HR: "all",
    RoleCode.ADMIN: "all",
    RoleCode.SYSADMIN: "all",
}
PRIVILEGED_ROLES = {RoleCode.ADMIN, RoleCode.SYSADMIN}  # only an administrator may hand these out
