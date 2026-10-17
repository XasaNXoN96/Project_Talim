from django.urls import path

from . import views as v

app_name = "notifications"

urlpatterns = [
    path("", v.NotificationListView.as_view(), name="list"),
    path("read-all/", v.NotificationReadAllView.as_view(), name="read_all"),
    path("<uuid:pk>/open/", v.NotificationOpenView.as_view(), name="open"),
    path("<uuid:pk>/read/", v.NotificationReadView.as_view(), name="read"),
]
