import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Appeal

PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{7,20}$")
INPUT = {"class": "input"}


class AppealForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off", "aria-hidden": "true"}))  # honeypot

    class Meta:
        model = Appeal
        fields = ["full_name", "phone", "email", "subject", "message"]
        widgets = {
            "full_name": forms.TextInput(attrs={**INPUT, "autocomplete": "name", "maxlength": 120}),
            "phone": forms.TextInput(attrs={**INPUT, "type": "tel", "autocomplete": "tel", "placeholder": "+998 90 123 45 67"}),
            "email": forms.EmailInput(attrs={**INPUT, "autocomplete": "email"}),
            "subject": forms.Select(attrs=INPUT),
            "message": forms.Textarea(attrs={**INPUT, "rows": 7, "maxlength": 2000}),
        }

    def clean_full_name(self):
        value = " ".join(self.cleaned_data["full_name"].split())
        if len(value) < 3:
            raise forms.ValidationError(_("Ism-familiyangizni to‘liq kiriting."))
        return value

    def clean_phone(self):
        value = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(value):
            raise forms.ValidationError(_("Telefon raqamini to‘g‘ri kiriting, masalan: +998 90 123 45 67."))
        return value

    def clean_message(self):
        value = self.cleaned_data["message"].strip()
        if len(value) < 10:
            raise forms.ValidationError(_("Murojaat matni kamida 10 ta belgidan iborat bo‘lsin."))
        return value

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("spam")
        return ""


class StatusForm(forms.Form):
    code = forms.CharField(max_length=12, widget=forms.TextInput(attrs={**INPUT, "placeholder": "M-XXXXXXXX", "autocomplete": "off"}))
    phone_tail = forms.CharField(min_length=4, max_length=4, widget=forms.TextInput(attrs={**INPUT, "inputmode": "numeric", "placeholder": "1234", "autocomplete": "off"}))


class AnswerForm(forms.Form):
    status = forms.ChoiceField(choices=[(Appeal.Status.IN_PROGRESS, _("Ko‘rib chiqilmoqda")), (Appeal.Status.ANSWERED, _("Javob berildi")), (Appeal.Status.REJECTED, _("Rad etildi"))],
                               widget=forms.Select(attrs=INPUT))
    answer = forms.CharField(max_length=2000, required=False, widget=forms.Textarea(attrs={**INPUT, "rows": 6, "maxlength": 2000}))

    def clean(self):
        data = super().clean()
        if data.get("status") in (Appeal.Status.ANSWERED, Appeal.Status.REJECTED) and not (data.get("answer") or "").strip():
            self.add_error("answer", _("Javob matnini kiriting."))
        return data
