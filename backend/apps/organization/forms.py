from django import forms
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.documents.storage import new_storage_name
from apps.documents.validation import UploadRejected

from . import photos
from .models import SELF_EDITABLE_FIELDS, Department, Employee, Institution, Position

INPUT = {"class": "input"}
User = get_user_model()


class EmployeeForm(forms.ModelForm):
    """Create/edit form. The user link is offered only to people who may manage accounts (see __init__)."""

    class Meta:
        model = Employee
        fields = [
            "last_name", "first_name", "middle_name", "department", "position", "institution", "status",
            "work_phone", "work_email", "hired_at", "personal_phone", "birth_date", "user",
        ]
        widgets = {
            "hired_at": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
            "birth_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
        }

    photo_upload = forms.FileField(
        label=_("Surat (JPG yoki PNG)"), required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png"})
    )
    photo_clear = forms.BooleanField(label=_("Suratni olib tashlash"), required=False)

    # fields a school director never sees or sets: the office structure, account link and the private tier
    SCHOOL_HIDDEN = ("department", "institution", "user", "hired_at", "personal_phone", "birth_date")

    def __init__(self, *args, can_link_user=False, request=None, school=None, **kwargs):
        self._request = request
        self._photo_bytes = None
        self._school = school  # an Institution when a school director edits their own staff
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("class", "input")
        self.fields["department"].queryset = Department.objects.filter(is_active=True) | Department.objects.filter(
            pk=getattr(self.instance, "department_id", None)
        )
        self.fields["position"].queryset = Position.objects.all()
        self.fields["institution"].queryset = Institution.objects.all()
        self.fields["institution"].required = False
        if school is not None:
            for name in self.SCHOOL_HIDDEN:
                self.fields.pop(name, None)
            return
        if can_link_user:
            self.fields["user"].queryset = User.objects.filter(is_active=True)
            self.fields["user"].required = False
            self.fields["user"].label = _("Foydalanuvchi hisobi")
        else:
            del self.fields["user"]

    def clean_photo_upload(self):
        uploaded = self.cleaned_data.get("photo_upload")
        if uploaded:
            try:
                self._photo_bytes = photos.prepare_photo(uploaded, request=self._request, user=getattr(self._request, "user", None))
            except UploadRejected as exc:
                raise forms.ValidationError(str(exc)) from exc
        return uploaded

    def save(self, commit=True):
        employee = super().save(commit=False)
        if self._school is not None:
            from .access import school_staff_department

            employee.institution = self._school
            employee.department = school_staff_department()
        old_name = employee.photo.name if employee.photo else ""
        if self._photo_bytes:
            employee.photo.save(new_storage_name("jpg"), ContentFile(self._photo_bytes), save=False)
        elif self.cleaned_data.get("photo_clear") and old_name:
            employee.photo = ""
        if commit:
            employee.save()
            self.save_m2m()
            if old_name and employee.photo.name != old_name:  # a replaced or removed photo must not linger on disk
                employee.photo.storage.delete(old_name)
        return employee

    def clean_user(self):
        user = self.cleaned_data.get("user")
        if user and Employee.objects.filter(user=user).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Bu hisob boshqa xodimga biriktirilgan."))
        return user


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "parent", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "input"
        self.fields["parent"].widget.attrs["class"] = "input"
        self.fields["parent"].required = False
        qs = Department.objects.all()
        if self.instance.pk:
            from .access import descendant_ids

            qs = qs.exclude(pk__in=descendant_ids(self.instance.pk))  # a department cannot move under itself or its children
        self.fields["parent"].queryset = qs

    def clean(self):
        data = super().clean()
        name, parent = data.get("name"), data.get("parent")
        if name and Department.objects.filter(name__iexact=name.strip(), parent=parent).exclude(pk=self.instance.pk).exists():
            self.add_error("name", _("Bu nomdagi bo‘lim shu joyda allaqachon bor."))
        if data.get("is_active") is False and self.instance.pk:
            if self.instance.employees.exclude(status=Employee.Status.ARCHIVED).exists() or self.instance.children.filter(is_active=True).exists():
                self.add_error("is_active", _("Faol xodimlari yoki faol quyi bo‘limlari bor bo‘limni o‘chirib bo‘lmaydi."))
        return data


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "input"


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "kind", "head_name", "is_published"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("name", "kind", "head_name"):
            self.fields[name].widget.attrs["class"] = "input"

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Institution.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Bu nomdagi muassasa allaqachon bor."))
        return name


class SelfChangeForm(forms.ModelForm):
    """What a person may ask to change about themselves. Bound to a COPY of their card: nothing is saved from here."""

    class Meta:
        model = Employee
        fields = list(SELF_EDITABLE_FIELDS)
        widgets = {"birth_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d")}
        labels = {"work_phone": _("Ish telefoni"), "work_email": _("Ish e-pochtasi"), "personal_phone": _("Shaxsiy telefon"), "birth_date": _("Tug‘ilgan sana")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("class", "input")

    def changes(self):
        """{field: cleaned value} for the fields that differ from the card. Call after is_valid()."""
        return {f: self.cleaned_data[f] for f in self.changed_data if f in SELF_EDITABLE_FIELDS}


class RejectForm(forms.Form):
    comment = forms.CharField(label=_("Xodim uchun izoh"), max_length=1000, widget=forms.Textarea(attrs={**INPUT, "rows": 3}))
