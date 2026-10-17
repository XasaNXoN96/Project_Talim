from django.urls import path

from .views import AuditLogListView, DashboardView, SearchView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("search/", SearchView.as_view(), name="search"),
    path("audit/", AuditLogListView.as_view(), name="audit"),
]
