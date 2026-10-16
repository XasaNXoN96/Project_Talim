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
_ORG_READ = ["organization.view_department", "organization.view_position", "organization.view_employee"]
_ORG_WRITE = [
    "organization.add_department", "organization.change_department",
    "organization.add_position", "organization.change_position",
    "organization.add_employee", "organization.change_employee",
    "organization.view_institution", "organization.add_institution", "organization.change_institution",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    RoleCode.EMPLOYEE: [],
    RoleCode.DEPARTMENT_HEAD: _ORG_READ,
    RoleCode.CONTENT_MANAGER: _CONTENT + ["organization.view_institution"],
    RoleCode.HR: _ORG_READ + _ORG_WRITE,
    RoleCode.ADMIN: _CONTENT + _ORG_READ + _ORG_WRITE + ["audit.view_auditlog", "accounts.view_user"],
    RoleCode.SYSADMIN: ["audit.view_auditlog"],
}
