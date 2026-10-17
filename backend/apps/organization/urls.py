from django.urls import path

from . import views as v

app_name = "employees"

urlpatterns = [
    path("", v.EmployeeListView.as_view(), name="list"),
    path("structure/", v.StructureView.as_view(), name="structure"),
    path("structure/departments/new/", v.DepartmentFormView.as_view(), name="department_create"),
    path("structure/departments/<uuid:pk>/", v.DepartmentFormView.as_view(), name="department_edit"),
    path("structure/positions/new/", v.PositionFormView.as_view(), name="position_create"),
    path("structure/positions/<uuid:pk>/", v.PositionFormView.as_view(), name="position_edit"),
    path("me/", v.EmployeeMeView.as_view(), name="me"),
    path("new/", v.EmployeeCreateView.as_view(), name="create"),
    path("<uuid:pk>/", v.EmployeeDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", v.EmployeeEditView.as_view(), name="edit"),
    path("<uuid:pk>/archive/", v.EmployeeArchiveView.as_view(restore=False), name="archive"),
    path("<uuid:pk>/restore/", v.EmployeeArchiveView.as_view(restore=True), name="restore"),
]
