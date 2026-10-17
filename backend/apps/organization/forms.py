from django import forms
from django.contrib.auth import get_user_model

from .models import Department, Employee, Position

INPUT = {"class": "input"}
User = get_user_model()


class EmployeeForm(forms.ModelForm):
    """Create/edit form. The user link is offered only to people who may manage accounts (see __init__)."""

    class Meta:
        model = Employee
        fields = [
            "last_name", "first_name", "middle_name", "department", "position", "status",
            "work_phone", "work_email", "hired_at", "personal_phone", "birth_date", "user",
        ]
        widgets = {
            "hired_at": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
            "birth_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, can_link_user=False, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("class", "input")
        self.fields["department"].queryset = Department.objects.filter(is_active=True) | Department.objects.filter(
            pk=getattr(self.instance, "department_id", None)
        )
        self.fields["position"].queryset = Position.objects.all()
        if can_link_user:
            self.fields["user"].queryset = User.objects.filter(is_active=True)
            self.fields["user"].required = False
            self.fields["user"].label = "Foydalanuvchi hisobi"
        else:
            del self.fields["user"]

    def clean_user(self):
        user = self.cleaned_data.get("user")
        if user and Employee.objects.filter(user=user).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu hisob boshqa xodimga biriktirilgan.")
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
            self.add_error("name", "Bu nomdagi bo‘lim shu joyda allaqachon bor.")
        if data.get("is_active") is False and self.instance.pk:
            if self.instance.employees.exclude(status=Employee.Status.ARCHIVED).exists() or self.instance.children.filter(is_active=True).exists():
                self.add_error("is_active", "Faol xodimlari yoki faol quyi bo‘limlari bor bo‘limni o‘chirib bo‘lmaydi.")
        return data


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "input"
