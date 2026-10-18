"""The 'Admin panel' hub: tiles that lead to the management pages that already exist. Nothing here grants access; every target page checks its own permission."""

from django.utils.translation import gettext_noop as _

MANAGE_PERMS = (
    "accounts.view_user", "audit.view_auditlog", "content.add_news", "organization.change_employee",
    "tasks.add_task", "documents.add_document", "reports.export_reports",
)

# (permission, url name, url args, icon, colour, title, subtitle)
TILES = (
    ("organization.view_employee_directory", "employees:list", (), "users", "c-blue", _("Xodimlar"), _("Qo‘shish, tahrirlash")),
    ("content.view_news", "news_admin:list", (), "news", "c-red", _("Yangiliklar"), _("Nashrlarni boshqarish")),
    ("tasks.view_task", "tasks:list", (), "clipboard", "c-orange", _("Topshiriqlar"), _("Nazorat")),
    ("documents.view_document", "documents:list", (), "file", "c-blue", _("Hujjatlar"), _("Hujjatlar bazasi")),
    ("reports.view_reports", "reports:index", (), "chart", "c-green", _("Hisobotlar"), _("Statistika")),
    ("organization.view_department", "employees:structure", (), "school", "c-teal", _("Tashkilot"), _("Tuzilma va lavozimlar")),
    ("accounts.view_user", "users:list", (), "users", "c-violet", _("Foydalanuvchilar"), _("Hisoblar va rollar")),
    ("audit.view_auditlog", "portal:audit", (), "shield", "c-violet", _("Audit jurnali"), _("Harakatlar tarixi")),
    ("audit.view_auditlog", "portal:jobs", (), "clock", "c-teal", _("Fon vazifalari"), _("Rejalashtirilgan ishlar")),
)


def can_open_hub(user):
    return user.is_authenticated and user.is_active and any(user.has_perm(p) for p in MANAGE_PERMS)


def tiles_for(user):
    return [t for t in TILES if user.has_perm(t[0])]
