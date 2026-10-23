from django.urls import path

from . import import_views as iv
from . import views as v

app_name = "employees"

urlpatterns = [
    path("", v.EmployeeListView.as_view(), name="list"),
    path("structure/", v.StructureView.as_view(), name="structure"),
    path("structure/departments/new/", v.DepartmentFormView.as_view(), name="department_create"),
    path("structure/departments/<uuid:pk>/", v.DepartmentFormView.as_view(), name="department_edit"),
    path("structure/positions/new/", v.PositionFormView.as_view(), name="position_create"),
    path("structure/positions/<uuid:pk>/", v.PositionFormView.as_view(), name="position_edit"),
    path("structure/institutions/new/", v.InstitutionFormView.as_view(), name="institution_create"),
    path("structure/institutions/<uuid:pk>/", v.InstitutionFormView.as_view(), name="institution_edit"),
    path("me/", v.EmployeeMeView.as_view(), name="me"),
    path("me/edit/", v.EmployeeSelfEditView.as_view(), name="me_edit"),
    path("me/changes/<uuid:pk>/cancel/", v.EmployeeChangeCancelView.as_view(), name="change_cancel"),
    path("changes/", v.EmployeeChangeListView.as_view(), name="change_list"),
    path("changes/<uuid:pk>/", v.EmployeeChangeDetailView.as_view(), name="change_detail"),
    path("changes/<uuid:pk>/<slug:decision>/", v.EmployeeChangeDecideView.as_view(), name="change_decide"),
    path("new/", v.EmployeeCreateView.as_view(), name="create"),
    path("import/", iv.ImportUploadView.as_view(), name="import"),
    path("import/template/", iv.ImportTemplateView.as_view(), name="import_template"),
    path("import/<uuid:pk>/", iv.ImportDetailView.as_view(), name="import_detail"),
    path("import/<uuid:pk>/confirm/", iv.ImportConfirmView.as_view(), name="import_confirm"),
    path("import/<uuid:pk>/cancel/", iv.ImportCancelView.as_view(), name="import_cancel"),
    path("<uuid:pk>/", v.EmployeeDetailView.as_view(), name="detail"),
    path("<uuid:pk>/photo/", v.EmployeePhotoView.as_view(), name="photo"),
    path("<uuid:pk>/edit/", v.EmployeeEditView.as_view(), name="edit"),
    path("<uuid:pk>/archive/", v.EmployeeArchiveView.as_view(restore=False), name="archive"),
    path("<uuid:pk>/restore/", v.EmployeeArchiveView.as_view(restore=True), name="restore"),
]
