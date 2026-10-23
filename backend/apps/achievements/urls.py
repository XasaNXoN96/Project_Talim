from django.urls import path

from . import views as v

app_name = "achievements"

urlpatterns = [
    path("", v.AchievementListView.as_view(), name="list"),
    path("new/", v.AchievementCreateView.as_view(), name="create"),
    path("image/<uuid:pk>/", v.AchievementImageView.as_view(), name="image"),
    path("video/<uuid:pk>/", v.AchievementVideoView.as_view(), name="video"),
    path("<uuid:pk>/", v.AchievementDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.AchievementEditView.as_view(), name="edit"),
    path("<uuid:pk>/preview/", v.AchievementPreviewView.as_view(), name="preview"),
    path("<uuid:pk>/step/<slug:step>/", v.AchievementStepView.as_view(), name="step"),
]
