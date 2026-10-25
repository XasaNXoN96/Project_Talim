from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import locale as core_locale
from apps.core import views as core_views

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("healthz/", core_views.healthz, name="healthz"),
    path("i18n/setlang/", core_locale.set_language, name="set_language"),  # the only language URL: no per-language duplicates
    path("csp-report/", core_views.csp_report, name="csp_report"),
    path("accounts/", include("apps.accounts.urls")),
    path("portal/users/", include("apps.accounts.manage_urls")),
    path("portal/news/", include("apps.content.manage_urls")),
    path("portal/achievements/", include("apps.achievements.urls")),
    path("portal/chat/", include("apps.chat.urls")),
    path("portal/attendance/", include("apps.attendance.urls")),
    path("portal/media/", include("apps.gallery.urls")),
    path("portal/employees/", include("apps.organization.urls")),
    path("portal/tasks/", include("apps.tasks.urls")),
    path("portal/documents/", include("apps.documents.urls")),
    path("portal/reports/", include("apps.reports.urls")),
    path("portal/notifications/", include("apps.notifications.urls")),
    path("portal/", include("apps.portal.urls")),
    path("", include("apps.achievements.public_urls")),
    path("", include("apps.gallery.public_urls")),
    path("", include("apps.content.urls")),
]

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
