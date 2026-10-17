from django.urls import path

from .views import AuditLogListView, DashboardView, SearchView, JobsView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("search/", SearchView.as_view(), name="search"),
    path("jobs/", JobsView.as_view(), name="jobs"),
    path("audit/", AuditLogListView.as_view(), name="audit"),
]
