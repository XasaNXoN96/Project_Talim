from django.urls import path

from . import views as v

app_name = "tasks"

urlpatterns = [
    path("", v.TaskListView.as_view(), name="list"),
    path("new/", v.TaskCreateView.as_view(), name="create"),
    path("<uuid:pk>/", v.TaskDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.TaskEditView.as_view(), name="edit"),
    path("<uuid:pk>/comment/", v.TaskCommentView.as_view(), name="comment"),
    path("<uuid:pk>/attachments/add/", v.TaskAttachmentAddView.as_view(), name="attachment_add"),
    path("<uuid:pk>/attachments/<uuid:attachment_id>/download/", v.TaskAttachmentDownloadView.as_view(), name="attachment_download"),
    path("<uuid:pk>/attachments/<uuid:attachment_id>/remove/", v.TaskAttachmentRemoveView.as_view(), name="attachment_remove"),
    path("<uuid:pk>/status/<slug:status>/", v.TaskTransitionView.as_view(), name="transition"),
]
