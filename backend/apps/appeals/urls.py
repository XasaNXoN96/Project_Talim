from django.urls import path

from .views import AppealCreateView, AppealStatusView

app_name = "appeals"

urlpatterns = [
    path("murojaat/", AppealCreateView.as_view(), name="create"),
    path("murojaat/holat/", AppealStatusView.as_view(), name="status"),
]
