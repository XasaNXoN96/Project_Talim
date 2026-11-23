from django import forms
from django.utils.translation import gettext_lazy as _

from apps.documents.validation import UploadRejected
from apps.organization.photos import prepare_photo

from .models import Announcement, Faq, Leader, SiteEvent

INPUT = {"class": "input"}


class _Base(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.DateInput, forms.TimeInput)):
                field.widget.attrs.setdefault("class", "input")


class AnnouncementForm(_Base):
    class Meta:
        model = Announcement
        fields = ["text", "link", "position", "is_published"]

    def clean_link(self):
        link = (self.cleaned_data.get("link") or "").strip()
        if link and (link.startswith("//") or not link.startswith(("/", "http://", "https://"))):
            raise forms.ValidationError(_("Havola / bilan yoki https:// bilan boshlansin."))
        return link


class EventForm(_Base):
    class Meta:
        model = SiteEvent
        fields = ["title", "date", "time", "place", "description", "is_published"]
        widgets = {"date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"), "time": forms.TimeInput(attrs={**INPUT, "type": "time"}, format="%H:%M")}


class FaqForm(_Base):
    class Meta:
        model = Faq
        fields = ["question", "answer", "position", "is_published"]
        widgets = {"answer": forms.Textarea(attrs={**INPUT, "rows": 6})}


class LeaderForm(_Base):
    photo_upload = forms.FileField(label=_("Surat (JPG yoki PNG)"), required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png"}))

    class Meta:
        model = Leader
        fields = ["full_name", "position", "reception", "phone", "email", "position_order", "is_published"]

    def __init__(self, *args, request=None, **kwargs):
        self._request = request
        self._photo = None
        super().__init__(*args, **kwargs)

    def clean_photo_upload(self):
        up = self.cleaned_data.get("photo_upload")
        if not up:
            return up
        try:
            self._photo = prepare_photo(up, request=self._request, user=getattr(self._request, "user", None))
        except UploadRejected as exc:
            raise forms.ValidationError(str(exc)) from exc
        return up

    def save(self, commit=True):
        from django.core.files.base import ContentFile

        from apps.documents.storage import new_storage_name

        obj = super().save(commit=commit)
        if self._photo:
            obj.photo.save(new_storage_name("jpg"), ContentFile(self._photo), save=True)
        return obj


KINDS = {
    "announcements": (Announcement, AnnouncementForm, _("Yugurma qator (e’lonlar)"), ("text", "is_published")),
    "events": (SiteEvent, EventForm, _("Tadbirlar kalendari"), ("title", "date", "is_published")),
    "leaders": (Leader, LeaderForm, _("Rahbariyat"), ("full_name", "position", "is_published")),
    "faq": (Faq, FaqForm, _("Ko‘p beriladigan savollar"), ("question", "is_published")),
}
