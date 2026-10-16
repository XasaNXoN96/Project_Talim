from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("healthz/", core_views.healthz, name="healthz"),
    path("accounts/", include("apps.accounts.urls")),
    path("portal/", include("apps.portal.urls")),
    path("", include("apps.content.urls")),
]

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
