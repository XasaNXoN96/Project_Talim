from django.urls import path

from . import views as v

app_name = "gallery"

urlpatterns = [
    path("", v.MediaListView.as_view(), name="list"),
    path("new/photos/", v.PhotoUploadView.as_view(), name="upload_photos"),
    path("new/video/", v.VideoUploadView.as_view(), name="upload_video"),
    path("bulk/", v.BulkView.as_view(), name="bulk"),
    path("file/<uuid:pk>/<slug:variant>/", v.FileView.as_view(), name="file"),
    path("<uuid:pk>/edit/", v.ItemEditView.as_view(), name="edit"),
    path("<uuid:pk>/delete/", v.ItemDeleteView.as_view(), name="delete"),
]
