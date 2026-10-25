from django.urls import path

from . import views as v

app_name = "attendance"

urlpatterns = [
    path("", v.ClockView.as_view(), name="clock"),
    path("notice/", v.NoticeView.as_view(), name="notice"),
    path("team/", v.TeamView.as_view(), name="team"),
    path("team/<uuid:pk>/", v.MemberView.as_view(), name="member"),
    path("team/<uuid:pk>/correct/", v.CorrectView.as_view(), name="correct"),
    path("zones/", v.ZonesView.as_view(), name="zones"),
    path("zones/new/", v.ZoneFormView.as_view(), name="zone_new"),
    path("zones/<uuid:pk>/", v.ZoneDetailView.as_view(), name="zone_detail"),
    path("zones/<uuid:pk>/edit/", v.ZoneFormView.as_view(), name="zone_edit"),
]
