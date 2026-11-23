from django.urls import path

from .site_views import SiteDeleteView, SiteFormView, SiteIndexView, SiteListView

app_name = "site_admin"

urlpatterns = [
    path("", SiteIndexView.as_view(), name="index"),
    path("<slug:kind>/", SiteListView.as_view(), name="list"),
    path("<slug:kind>/new/", SiteFormView.as_view(), name="new"),
    path("<slug:kind>/<uuid:pk>/edit/", SiteFormView.as_view(), name="edit"),
    path("<slug:kind>/<uuid:pk>/delete/", SiteDeleteView.as_view(), name="delete"),
]
