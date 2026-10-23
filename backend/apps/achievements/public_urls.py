from django.urls import path

from . import views as v

app_name = "achievements_public"

urlpatterns = [
    path("yutuqlar/", v.PublicListView.as_view(), name="list"),
    path("yutuqlar/rasm/<uuid:pk>/", v.PublicImageView.as_view(), name="image"),
    path("yutuqlar/<slug:slug>/", v.PublicDetailView.as_view(), name="detail"),
]
