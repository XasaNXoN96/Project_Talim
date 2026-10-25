from django.urls import path

from . import manage_views as v

app_name = "news_admin"

urlpatterns = [
    path("", v.NewsListView.as_view(), name="list"),
    path("new/", v.NewsCreateView.as_view(), name="create"),
    path("categories/", v.CategoryListView.as_view(), name="categories"),
    path("categories/new/", v.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<uuid:pk>/", v.CategoryEditView.as_view(), name="category_edit"),
    path("<uuid:pk>/", v.NewsPreviewView.as_view(), name="preview"),
    path("<uuid:pk>/cover/", v.NewsCoverView.as_view(), name="cover"),
    path("<uuid:pk>/edit/", v.NewsEditView.as_view(), name="edit"),
    path("<uuid:pk>/<slug:action>/", v.NewsStatusView.as_view(), name="status"),
]
