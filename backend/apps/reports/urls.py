from django.urls import path

from . import views as v

app_name = "reports"

urlpatterns = [
    path("", v.ReportView.as_view(), name="index"),
    path("export/<slug:fmt>/", v.ReportExportView.as_view(), name="export"),
]
