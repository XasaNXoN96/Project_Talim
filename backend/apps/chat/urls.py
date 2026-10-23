from django.urls import path

from . import views as v

app_name = "chat"

urlpatterns = [
    path("", v.InboxView.as_view(), name="inbox"),
    path("notice/", v.NoticeView.as_view(), name="notice"),
    path("start/", v.StartView.as_view(), name="start"),
    path("archive/", v.ArchiveListView.as_view(), name="archive"),
    path("archive/<uuid:pk>/", v.ArchiveThreadView.as_view(), name="archive_thread"),
    path("<uuid:pk>/", v.ThreadView.as_view(), name="thread"),
]
