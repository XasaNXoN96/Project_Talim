from django.urls import path

from . import views as v

app_name = "tasks"

urlpatterns = [
    path("", v.TaskListView.as_view(), name="list"),
    path("new/", v.TaskCreateView.as_view(), name="create"),
    path("<uuid:pk>/", v.TaskDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.TaskEditView.as_view(), name="edit"),
    path("<uuid:pk>/comment/", v.TaskCommentView.as_view(), name="comment"),
    path("<uuid:pk>/status/<slug:status>/", v.TaskTransitionView.as_view(), name="transition"),
]
