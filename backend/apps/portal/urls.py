from django.urls import path

from .views import AdminHubView, AuditLogListView, DashboardView, JobsView, PreviewView, SearchView

app_name = "portal"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("search/", SearchView.as_view(), name="search"),
    path("jobs/", JobsView.as_view(), name="jobs"),
    path("audit/", AuditLogListView.as_view(), name="audit"),
    path("admin-panel/", AdminHubView.as_view(), name="admin_hub"),
    path("maket/<slug:section>/", PreviewView.as_view(), name="preview"),
]
