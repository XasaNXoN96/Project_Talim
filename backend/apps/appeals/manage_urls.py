from django.urls import path

from .views import AppealDetailView, AppealListView

app_name = "appeals_admin"

urlpatterns = [
    path("", AppealListView.as_view(), name="list"),
    path("<uuid:pk>/", AppealDetailView.as_view(), name="detail"),
]
