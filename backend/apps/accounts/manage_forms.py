from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

from apps.access.roles import RoleCode
from apps.organization.models import Department

User = get_user_model()

USERNAME_VALIDATOR = RegexValidator(r"^[A-Za-z0-9._-]{3,150}$", "Login 3–150 belgi: lotin harflari, raqamlar, nuqta, tire, pastki chiziq.")
INPUT = {"class": "input"}


def _exists_ci(field, value, exclude=None):
    qs = User.objects.filter(**{f"{field}__iexact": value})
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.exists()


class UserCreateForm(forms.Form):
    username = forms.CharField(label="Login", max_length=150, validators=[USERNAME_VALIDATOR], widget=forms.TextInput(attrs=INPUT))
    email = forms.EmailField(label="E-pochta", widget=forms.EmailInput(attrs=INPUT))
    last_name = forms.CharField(label="Familiya", max_length=150, widget=forms.TextInput(attrs=INPUT))
    first_name = forms.CharField(label="Ism", max_length=150, widget=forms.TextInput(attrs=INPUT))
    role = forms.ChoiceField(label="Rol", choices=RoleCode.choices, widget=forms.Select(attrs=INPUT))
    department = forms.ModelChoiceField(
        label="Bo‘lim (faqat bo‘lim boshlig‘i uchun)", queryset=Department.objects.filter(is_active=True), required=False,
        widget=forms.Select(attrs=INPUT),
    )

    def __init__(self, *args, allowed_roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed_roles is not None:
            self.fields["role"].choices = [c for c in RoleCode.choices if c[0] in allowed_roles]

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if _exists_ci("username", value):
            raise forms.ValidationError("Bu login band.")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if _exists_ci("email", value):
            raise forms.ValidationError("Bu e-pochta band.")
        return value


class UserEditForm(forms.Form):
    email = forms.EmailField(label="E-pochta", widget=forms.EmailInput(attrs=INPUT))
    last_name = forms.CharField(label="Familiya", max_length=150, widget=forms.TextInput(attrs=INPUT))
    first_name = forms.CharField(label="Ism", max_length=150, widget=forms.TextInput(attrs=INPUT))
    locale = forms.ChoiceField(label="Til", choices=User.Locale.choices, widget=forms.Select(attrs=INPUT))

    def __init__(self, *args, user, **kwargs):
        self.target = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if _exists_ci("email", value, exclude=self.target):
            raise forms.ValidationError("Bu e-pochta band.")
        return value


class RoleAssignForm(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=RoleCode.choices, widget=forms.Select(attrs=INPUT))
    department = forms.ModelChoiceField(
        label="Bo‘lim", queryset=Department.objects.filter(is_active=True), required=False, widget=forms.Select(attrs=INPUT)
    )

    def __init__(self, *args, allowed_roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed_roles is not None:
            self.fields["role"].choices = [c for c in RoleCode.choices if c[0] in allowed_roles]
