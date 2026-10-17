from django.urls import path

from . import manage_views as v

app_name = "users"

urlpatterns = [
    path("", v.UserListView.as_view(), name="list"),
    path("new/", v.UserCreateView.as_view(), name="create"),
    path("<uuid:pk>/", v.UserDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.UserEditView.as_view(), name="edit"),
    path("<uuid:pk>/roles/add/", v.RoleAssignView.as_view(), name="role_add"),
    path("<uuid:pk>/roles/<uuid:assignment_id>/remove/", v.RoleRevokeView.as_view(), name="role_remove"),
    path("<uuid:pk>/do/<slug:action>/", v.UserActionView.as_view(), name="action"),
]
