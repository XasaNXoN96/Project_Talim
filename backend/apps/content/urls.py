from django.urls import path

from .views import (HomeView, InstitutionDetailView, InstitutionListView, NewsCoverView, NewsDetailView, NewsListView, SearchView, TeacherListView,
                    TeacherPhotoView, LeaderPhotoView, EventListView)

app_name = "content"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("yangiliklar/", NewsListView.as_view(), name="news_list"),
    path("yangiliklar/rasm/<uuid:pk>/", NewsCoverView.as_view(), name="news_cover"),
    path("muassasalar/", InstitutionListView.as_view(), name="institutions"),
    path("muassasalar/<uuid:pk>/", InstitutionDetailView.as_view(), name="institution"),
    path("ustozlar/", TeacherListView.as_view(), name="teachers"),
    path("ustozlar/rasm/<uuid:pk>/", TeacherPhotoView.as_view(), name="teacher_photo"),
    path("tadbirlar/", EventListView.as_view(), name="events"),
    path("rahbariyat/rasm/<uuid:pk>/", LeaderPhotoView.as_view(), name="leader_photo"),
    path("qidiruv/", SearchView.as_view(), name="search"),
    path("yangiliklar/<slug:slug>/", NewsDetailView.as_view(), name="news_detail"),
]
