"""Role definitions (see docs/ROLES_PERMISSIONS.md).

A role is a Django Group. Group permissions are the *global* part of access control; the scope
(own / department / all) is stored in RoleAssignment and checked in services. The mapping below starts small
and grows module by module — `employee` has no extra permissions yet because no employee-facing modules exist.
Guests are anonymous users and have no role.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class RoleCode(models.TextChoices):
    EMPLOYEE = "employee", _("Xodim")
    DEPARTMENT_HEAD = "department_head", _("Bo‘lim boshlig‘i")
    CONTENT_MANAGER = "content_manager", _("Kontent-menejer")
    HR = "hr", _("Kadrlar bo‘limi")
    ADMIN = "admin", _("Administrator")
    NEWS_AUTHOR = "news_author", _("Yangilik muallifi")
    NEWS_EDITOR = "news_editor", _("Yangilik muharriri")
    NEWS_PUBLISHER = "news_publisher", _("Yangilik nashr etuvchisi")
    SYSADMIN = "sysadmin", _("Tizim administratori")
    SCHOOL_DIRECTOR = "school_director", _("Muassasa direktori")


_CONTENT = [
    "content.view_newscategory", "content.add_newscategory", "content.change_newscategory",
    "content.view_news", "content.add_news", "content.change_news", "content.publish_news", "content.review_news",
    # "content.approve_own_news" is deliberately in NO role: nobody approves their own item (docs/NEWS_WORKFLOW.md)
]
# Notifications have their own (Django default) permission: it no longer rides on tasks.view_task. Every role that could open the
# notifications page before (those with tasks.view_task) keeps it; the news roles get it because their notices are about news.
_NOTIFY = ["notifications.view_notification"]
# Editorial roles (day 19). They only REUSE the news permissions; an item is also limited to what the role may see (apps.content.workflow.visible_news).
_NEWS_AUTHOR = ["content.view_news", "content.add_news", "content.change_news"]
_NEWS_EDITOR = ["content.view_news", "content.review_news"]
_NEWS_PUBLISHER = ["content.view_news", "content.publish_news"]
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
_REPORTS = ["reports.view_reports", "reports.export_reports"]
_REPORTS_PEOPLE = ["reports.view_report_people"]
_USER_ADMIN = ["accounts.view_user", "accounts.manage_users", "accounts.assign_roles", "accounts.unlock_accounts"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Contacts/private data are further limited by SCOPE (own / department / all) in apps.organization.access.
    RoleCode.EMPLOYEE: _DIRECTORY + _ORG_VIEW + _TASKS_BASIC + _DOCS_VIEW + _NOTIFY,
    RoleCode.DEPARTMENT_HEAD: _DIRECTORY + _CONTACTS + _ORG_VIEW + _TASKS_BASIC + _TASKS_MANAGE + _DOCS_VIEW + _DOCS_WRITE + _REPORTS + _REPORTS_PEOPLE + _NOTIFY,
    RoleCode.CONTENT_MANAGER: _CONTENT + ["organization.view_institution"] + _TASKS_BASIC + _DOCS_VIEW + _NOTIFY,
    RoleCode.HR: _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + ["accounts.view_user"] + _TASKS_BASIC + ["tasks.add_task"] + _DOCS_VIEW + _DOCS_WRITE + _DOCS_ALL + _REPORTS + _NOTIFY,
    RoleCode.ADMIN: _CONTENT + _DIRECTORY + _CONTACTS + _PRIVATE + _ORG_VIEW + _ORG_WRITE + _USER_ADMIN + ["audit.view_auditlog"] + _TASKS_BASIC + _TASKS_MANAGE + _DOCS_VIEW + _DOCS_WRITE + _DOCS_ALL + _REPORTS + _REPORTS_PEOPLE + _NOTIFY,
    RoleCode.NEWS_AUTHOR: _NEWS_AUTHOR + _NOTIFY,
    RoleCode.NEWS_EDITOR: _NEWS_EDITOR + _NOTIFY,
    RoleCode.NEWS_PUBLISHER: _NEWS_PUBLISHER + _NOTIFY,
    RoleCode.SYSADMIN: ["audit.view_auditlog"],
    # A school director sees and maintains the staff of THEIR OWN institution only: the limit is the "institution" scope,
    # enforced in apps.organization.access (listing, cards, create/edit/archive, photo). add/change_employee are global Django
    # permissions; the views narrow them to the own institution's cards without an account, hide department/user/private fields,
    # and keep the director out of the import tool and the admin hub. No department structure, no other institutions.
    RoleCode.SCHOOL_DIRECTOR: _DIRECTORY + _CONTACTS + ["organization.add_employee", "organization.change_employee"] + _TASKS_BASIC + _DOCS_VIEW + _NOTIFY,
}


# The scope is fixed per role (not chosen per assignment): one less thing to get wrong.
ROLE_SCOPE = {
    RoleCode.EMPLOYEE: "own",
    RoleCode.DEPARTMENT_HEAD: "department",  # needs a department
    RoleCode.CONTENT_MANAGER: "all",
    RoleCode.HR: "all",
    RoleCode.ADMIN: "all",
    RoleCode.NEWS_AUTHOR: "all",
    RoleCode.NEWS_EDITOR: "all",
    RoleCode.NEWS_PUBLISHER: "all",
    RoleCode.SYSADMIN: "all",
    RoleCode.SCHOOL_DIRECTOR: "institution",  # needs an employee card linked to an institution
}
PRIVILEGED_ROLES = {RoleCode.ADMIN, RoleCode.SYSADMIN}  # only an administrator may hand these out


# One line per role for the role-assignment screen (what the role allows, in the interface language).
ROLE_HINTS = {
    RoleCode.NEWS_AUTHOR: _("Yangilik yozadi va o‘z qoralamalarini tahrirlaydi, tekshiruvga yuboradi, o‘z yangiliklari bo‘yicha qarorlar va izohlarni ko‘radi. Ma’qullay yoki nashr eta olmaydi."),
    RoleCode.NEWS_EDITOR: _("Tekshiruvdagi yangiliklarni ko‘radi, ma’qullaydi yoki majburiy izoh bilan qaytaradi. Yozmaydi va nashr etmaydi; o‘z yangiligini ma’qullay olmaydi."),
    RoleCode.NEWS_PUBLISHER: _("Faqat ma’qullangan yangilikni nashr etadi va nashrdan oladi. Qoralamani to‘g‘ridan-to‘g‘ri nashr eta olmaydi."),
    RoleCode.SCHOOL_DIRECTOR: _("Faqat o‘z muassasasi xodimlarini va ularning aloqa ma’lumotlarini ko‘radi; o‘ziga biriktirilgan topshiriqlar bilan ishlaydi. Boshqa muassasalarni ko‘rmaydi."),
    RoleCode.CONTENT_MANAGER: _("Yangilikni yozadi, tekshiradi va nashr etadi (o‘zinikini ma’qullay olmaydi)."),
}
