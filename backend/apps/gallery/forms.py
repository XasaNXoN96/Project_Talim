from django import forms
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.achievements import videos
from apps.achievements.forms import MultipleFileField
from apps.documents.storage import new_storage_name
from apps.documents.validation import UploadRejected
from apps.organization.models import Institution

from . import images
from .models import MediaItem

INPUT = {"class": "input"}
MAX_PHOTOS_PER_UPLOAD = 12


def video_limit():
    from django.conf import settings

    return int(getattr(settings, "MEDIA_VIDEO_MAX_BYTES", settings.ACHIEVEMENT_VIDEO_MAX_BYTES))


class _Common(forms.Form):
    title = forms.CharField(label=_("Sarlavha"), max_length=200, required=False, widget=forms.TextInput(attrs=INPUT))
    institution = forms.ModelChoiceField(label=_("Ta’lim muassasasi"), queryset=Institution.objects.none(), required=False, widget=forms.Select(attrs=INPUT))
    taken_on = forms.DateField(label=_("Olingan sana"), required=False, widget=forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"))
    consent_confirmed = forms.BooleanField(
        label=_("Nashrga rozilik"), required=False,
        help_text=_("Rasmda yoki videoda ko‘ringan shaxslar (voyaga yetmaganlar uchun ota-onasi) ochiq saytda nashr etishga rozilik bergan. Rozilik bo‘lmasa, fayl nashr etilmaydi."),
    )

    def __init__(self, *args, request=None, **kwargs):
        self._request = request
        super().__init__(*args, **kwargs)
        self.fields["institution"].queryset = Institution.objects.all()

    def clean_taken_on(self):
        value = self.cleaned_data.get("taken_on")
        if value and value > timezone.localdate():
            raise forms.ValidationError(_("Sana kelajakda bo‘lishi mumkin emas."))
        return value

    def common(self):
        d = self.cleaned_data
        return {"institution": d.get("institution"), "taken_on": d.get("taken_on"), "consent_confirmed": bool(d.get("consent_confirmed"))}


class PhotoUploadForm(_Common):
    files = MultipleFileField(label=_("Fotorasmlar (JPG yoki PNG)"), required=True)
    field_order = ["files", "title", "institution", "taken_on", "consent_confirmed"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].help_text = _("Barcha rasmlarga bir xil sarlavha qo‘yiladi (ixtiyoriy).")
        self._prepared = []

    def clean_files(self):
        uploaded = self.cleaned_data.get("files") or []
        if not uploaded:
            raise forms.ValidationError(_("Kamida bitta rasm tanlang."))
        if len(uploaded) > MAX_PHOTOS_PER_UPLOAD:
            raise forms.ValidationError(_("Bir yuklashda ko‘pi bilan %(n)d ta rasm.") % {"n": MAX_PHOTOS_PER_UPLOAD})
        user = getattr(self._request, "user", None)
        for f in uploaded:  # every file is checked BEFORE anything is saved: one bad file refuses the whole batch
            try:
                self._prepared.append(images.prepare_photo(f, request=self._request, user=user))
            except UploadRejected as exc:
                raise forms.ValidationError(str(exc)) from exc
        return uploaded

    def save(self, user):
        import hashlib

        items = []
        for full, thumb in self._prepared:
            item = MediaItem(kind=MediaItem.Kind.PHOTO, title=self.cleaned_data.get("title", ""), uploaded_by=user, content_type="image/jpeg", size=len(full),
                             sha256=hashlib.sha256(full).hexdigest(), scan_status="clean", **self.common())
            item.file.save(new_storage_name("jpg"), ContentFile(full), save=False)
            item.thumb.save(new_storage_name("jpg"), ContentFile(thumb), save=False)
            item.save()
            items.append(item)
        return items


class VideoUploadForm(_Common):
    file = forms.FileField(
        label=_("Video fayl (MP4 yoki WebM)"), required=True, widget=forms.FileInput(attrs={"accept": "video/mp4,video/webm"}),
    )
    field_order = ["file", "title", "institution", "taken_on", "consent_confirmed"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = True
        self.fields["file"].help_text = _("Eng ko‘pi bilan %(mb)d MB. Brauzerda ochiladigan kodek tavsiya etiladi: MP4 uchun H.264/AAC.") % {"mb": videos.mb(video_limit())}
        self._video = None

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        try:
            self._video = videos.prepare_video(uploaded, request=self._request, user=getattr(self._request, "user", None), limit=video_limit())
        except UploadRejected as exc:
            raise forms.ValidationError(str(exc)) from exc
        return uploaded

    def save(self, user):
        v = self._video
        item = MediaItem(kind=MediaItem.Kind.VIDEO, title=self.cleaned_data["title"], uploaded_by=user, content_type=v.content_type, size=len(v.data), sha256=v.sha256,
                         scan_status=v.scan_status, **self.common())
        item.file.save(new_storage_name(v.ext), ContentFile(v.data), save=False)
        item.save()
        return [item]


class ItemForm(forms.ModelForm):
    class Meta:
        model = MediaItem
        fields = ["title", "institution", "taken_on", "consent_confirmed"]
        widgets = {"title": forms.TextInput(attrs=INPUT), "institution": forms.Select(attrs=INPUT), "taken_on": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d")}
        help_texts = {"consent_confirmed": _("Rasmda yoki videoda ko‘ringan shaxslar (voyaga yetmaganlar uchun ota-onasi) ochiq saytda nashr etishga rozilik bergan. Rozilik bo‘lmasa, fayl nashr etilmaydi.")}

    def clean(self):
        data = super().clean()
        if self.instance.status == MediaItem.Status.PUBLISHED and not data.get("consent_confirmed"):
            self.add_error("consent_confirmed", _("Nashr etilgan faylning roziligini olib tashlab bo‘lmaydi: avval nashrdan oling."))
        if self.instance.kind == MediaItem.Kind.VIDEO and not (data.get("title") or "").strip():
            self.add_error("title", _("Video uchun sarlavha shart."))
        return data
