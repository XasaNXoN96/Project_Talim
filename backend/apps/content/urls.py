from django.urls import path

from .views import HomeView, NewsDetailView, NewsListView

app_name = "content"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("yangiliklar/", NewsListView.as_view(), name="news_list"),
    path("yangiliklar/<slug:slug>/", NewsDetailView.as_view(), name="news_detail"),
]
