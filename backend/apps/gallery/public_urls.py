from django.urls import path

from . import views as v

app_name = "gallery_public"

urlpatterns = [
    path("media/", v.PublicListView.as_view(), name="list"),
    path("media/file/<uuid:pk>/<slug:variant>/", v.PublicFileView.as_view(), name="file"),
]
