from django.urls import path

from .views import HomeView, NewsCoverView, NewsDetailView, NewsListView

app_name = "content"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("yangiliklar/", NewsListView.as_view(), name="news_list"),
    path("yangiliklar/rasm/<uuid:pk>/", NewsCoverView.as_view(), name="news_cover"),
    path("yangiliklar/<slug:slug>/", NewsDetailView.as_view(), name="news_detail"),
]
