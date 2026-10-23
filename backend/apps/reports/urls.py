from django.urls import path

from . import views as v

app_name = "reports"

urlpatterns = [
    path("", v.ReportView.as_view(), name="index"),
    path("schools/", v.SchoolsReportView.as_view(), name="schools"),
    path("schools/export/", v.SchoolsExportView.as_view(), name="schools_export"),
    path("schools/export/pdf/", v.SchoolsExportView.as_view(fmt="pdf"), name="schools_export_pdf"),
    path("schools/<uuid:pk>/", v.SchoolDetailView.as_view(), name="school"),
    path("export/<slug:fmt>/", v.ReportExportView.as_view(), name="export"),
]
