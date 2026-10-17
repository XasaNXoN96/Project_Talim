from django import forms
from django.utils.translation import gettext_lazy as _

from apps.organization.models import Department

from .models import Document, DocumentCategory

INPUT = {"class": "input"}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "number", "category", "doc_date", "description", "access_level", "department"]
        widgets = {
            "title": forms.TextInput(attrs=INPUT), "number": forms.TextInput(attrs=INPUT), "category": forms.Select(attrs=INPUT),
            "doc_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={**INPUT, "rows": 4}),
            "access_level": forms.Select(attrs=INPUT), "department": forms.Select(attrs=INPUT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = DocumentCategory.objects.filter(is_active=True)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].required = False
        self.fields["department"].help_text = _("Faqat «Faqat bo‘lim» darajasi uchun.")

    def clean(self):
        data = super().clean()
        level, dept = data.get("access_level"), data.get("department")
        if level == Document.Access.DEPARTMENT and not dept:
            self.add_error("department", _("Bo‘lim darajasi uchun bo‘lim tanlang."))
        if level != Document.Access.DEPARTMENT:
            data["department"] = None
        return data


class FileMixin(forms.Form):
    file = forms.FileField(label=_("Fayl"), widget=forms.ClearableFileInput(attrs={**INPUT, "accept": ".pdf,.png,.jpg,.jpeg,.txt,.docx,.xlsx,.pptx,.odt,.ods"}))


class DocumentCreateForm(DocumentForm, FileMixin):
    pass


class VersionForm(FileMixin):
    comment = forms.CharField(label=_("Izoh (nima o‘zgardi)"), max_length=200, required=False, widget=forms.TextInput(attrs=INPUT))
