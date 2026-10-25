from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import AttendanceEvent, WorkZone


class ZoneForm(forms.ModelForm):
    class Meta:
        model = WorkZone
        fields = ["name", "institution", "latitude", "longitude", "radius_m", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "maxlength": 200}),
            "institution": forms.Select(attrs={"class": "select"}),
            "latitude": forms.NumberInput(attrs={"class": "input", "step": "0.000001", "min": "-90", "max": "90", "inputmode": "decimal"}),
            "longitude": forms.NumberInput(attrs={"class": "input", "step": "0.000001", "min": "-180", "max": "180", "inputmode": "decimal"}),
            "radius_m": forms.NumberInput(attrs={"class": "input", "min": "30", "max": "5000"}),
        }
        help_texts = {
            "institution": _("Bo‘sh qoldirsangiz, hudud hamma uchun amal qiladi."),
            "radius_m": _("30 dan 5000 metrgacha. Maktab hovlisi uchun odatda 100–200 m."),
        }


class ManualEventForm(forms.Form):
    kind = forms.ChoiceField(label=_("Amal"), choices=AttendanceEvent.Kind.choices, widget=forms.Select(attrs={"class": "select"}))
    at = forms.DateTimeField(label=_("Vaqt"), input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"], widget=forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    note = forms.CharField(label=_("Tuzatish sababi"), max_length=300, widget=forms.TextInput(attrs={"class": "input", "maxlength": 300}))

    def clean_at(self):
        at = self.cleaned_data["at"]
        if timezone.is_naive(at):
            at = timezone.make_aware(at)
        return at
