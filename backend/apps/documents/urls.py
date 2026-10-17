from django.urls import path

from . import views as v

app_name = "documents"

urlpatterns = [
    path("", v.DocumentListView.as_view(), name="list"),
    path("new/", v.DocumentCreateView.as_view(), name="create"),
    path("<uuid:pk>/", v.DocumentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.DocumentEditView.as_view(), name="edit"),
    path("<uuid:pk>/versions/add/", v.VersionAddView.as_view(), name="version_add"),
    path("<uuid:pk>/download/", v.DocumentDownloadView.as_view(), name="download"),
    path("<uuid:pk>/download/<int:number>/", v.DocumentDownloadView.as_view(), name="download_version"),
    path("<uuid:pk>/view/", v.DocumentPreviewView.as_view(), name="preview"),
    path("<uuid:pk>/view/<int:number>/", v.DocumentPreviewView.as_view(), name="preview_version"),
    path("<uuid:pk>/inline/", v.DocumentInlineView.as_view(), name="inline"),
    path("<uuid:pk>/inline/<int:number>/", v.DocumentInlineView.as_view(), name="inline_version"),
    path("<uuid:pk>/archive/", v.DocumentArchiveView.as_view(restore=False), name="archive"),
    path("<uuid:pk>/restore/", v.DocumentArchiveView.as_view(restore=True), name="restore"),
]
