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
_USER_ADMIN = ["accounts.view_user", "accounts.manage_users", "accounts.assign_roles", "accounts.unlock_accounts"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Contacts/private data are further limited by SCOPE (own / department / all) in apps.organization.access.
    RoleCode.EMPLOYEE: _DIRECTORY + _ORG_VIEW,
    RoleCode.DEPARTMENT_HEAD: _DIRECTORY + _CONTACTS + _ORG_VIEW,
    RoleCode.CONTENT_MANAGER: _CONTENT + ["organization.view_institution"],
    RoleCode.HR: _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + ["accounts.view_user"],
    RoleCode.ADMIN: _CONTENT + _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + _USER_ADMIN + ["audit.view_auditlog"],
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
