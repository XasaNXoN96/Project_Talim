from django.urls import path

from .views import AuditLogListView, DashboardView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("audit/", AuditLogListView.as_view(), name="audit"),
]
