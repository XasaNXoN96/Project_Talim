from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("healthz/", core_views.healthz, name="healthz"),
    path("csp-report/", core_views.csp_report, name="csp_report"),
    path("accounts/", include("apps.accounts.urls")),
    path("portal/users/", include("apps.accounts.manage_urls")),
    path("portal/employees/", include("apps.organization.urls")),
    path("portal/tasks/", include("apps.tasks.urls")),
    path("portal/", include("apps.portal.urls")),
    path("", include("apps.content.urls")),
]

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
