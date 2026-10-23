from urllib.parse import urlparse

from django import forms
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.documents.storage import new_storage_name
from apps.documents.validation import UploadRejected
from apps.organization.models import Institution

from . import images, videos
from .models import Achievement, AchievementImage, AchievementVideo

INPUT = {"class": "input"}


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


class AchievementForm(forms.ModelForm):
    new_images = MultipleFileField(label=_("Rasmlar (JPG yoki PNG)"), required=False)
    remove_images = forms.ModelMultipleChoiceField(
        queryset=AchievementImage.objects.none(), required=False, label=_("Olib tashlanadigan rasmlar"), widget=forms.CheckboxSelectMultiple
    )

    new_video = forms.FileField(
        label=_("Video fayl (MP4 yoki WebM)"), required=False, widget=forms.FileInput(attrs={"accept": "video/mp4,video/webm"}),
    )
    remove_video = forms.BooleanField(label=_("Videoni olib tashlash"), required=False)

    class Meta:
        model = Achievement
        fields = [
            "institution", "kind", "title", "person_kind", "person_name", "person_position", "level", "awarded_on",
            "description", "video_url", "consent_confirmed",
        ]
        widgets = {
            "institution": forms.Select(attrs=INPUT), "kind": forms.Select(attrs=INPUT), "title": forms.TextInput(attrs=INPUT),
            "person_kind": forms.Select(attrs=INPUT), "person_name": forms.TextInput(attrs=INPUT), "person_position": forms.TextInput(attrs=INPUT),
            "level": forms.Select(attrs=INPUT), "awarded_on": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={**INPUT, "rows": 6}), "video_url": forms.URLInput(attrs={**INPUT, "placeholder": "https://"}),
        }
        help_texts = {
            "video_url": _("Yoki videoni boshqa saytga (masalan, YouTube) joylab, https havolasini kiriting."),
            "consent_confirmed": _("Ishtirokchi (voyaga yetmagan bo‘lsa, ota-onasi) ma’lumot va rasmni ochiq saytda nashr etishga rozilik bergan."),
        }

    def __init__(self, *args, request=None, staff=False, school=None, **kwargs):
        self._request = request
        self._school = school  # the Institution of a school user: fixed, not chosen
        self._image_bytes = []
        self._video = None
        super().__init__(*args, **kwargs)
        if staff:
            self.fields["institution"].queryset = Institution.objects.all()
        else:
            del self.fields["institution"]
        self.fields["new_video"].help_text = _("Eng ko‘pi bilan %(mb)d MB. Brauzerda ochiladigan kodek tavsiya etiladi: MP4 uchun H.264/AAC.") % {"mb": videos.mb(videos.max_bytes())}
        if not (self.instance.pk and hasattr(self.instance, "video")):
            del self.fields["remove_video"]
        if self.instance.pk:
            self.fields["remove_images"].queryset = self.instance.images.all()
            self.fields["remove_images"].label_from_instance = lambda im: _("Rasm") + f" {im.position + 1}"
        else:
            del self.fields["remove_images"]

    def clean_awarded_on(self):
        value = self.cleaned_data.get("awarded_on")
        if value and value > timezone.localdate():
            raise forms.ValidationError(_("Sana kelajakda bo‘lishi mumkin emas."))
        return value

    def clean_video_url(self):
        value = (self.cleaned_data.get("video_url") or "").strip()
        if value and urlparse(value).scheme != "https":
            raise forms.ValidationError(_("Faqat https havolasi qabul qilinadi."))
        return value

    def clean_new_images(self):
        uploaded = self.cleaned_data.get("new_images") or []
        existing = self.instance.images.count() if self.instance.pk else 0
        removing = len(self.data.getlist("remove_images")) if hasattr(self.data, "getlist") else 0
        if existing - removing + len(uploaded) > AchievementImage.MAX_PER_ACHIEVEMENT:
            raise forms.ValidationError(_("Bitta yutuqqa ko‘pi bilan %(n)d ta rasm biriktiriladi.") % {"n": AchievementImage.MAX_PER_ACHIEVEMENT})
        out = []
        for f in uploaded:
            try:
                out.append(images.prepare_image(f, request=self._request, user=getattr(self._request, "user", None)))
            except UploadRejected as exc:
                raise forms.ValidationError(str(exc)) from exc
        self._image_bytes = out
        return uploaded

    def clean_new_video(self):
        uploaded = self.cleaned_data.get("new_video")
        if uploaded:
            try:
                self._video = videos.prepare_video(uploaded, request=self._request, user=getattr(self._request, "user", None))
            except UploadRejected as exc:
                raise forms.ValidationError(str(exc)) from exc
        return uploaded

    def save(self, commit=True):
        a = super().save(commit=False)
        if self._school is not None:
            a.institution = self._school
        if commit:
            a.save()
            removed = list(self.cleaned_data.get("remove_images") or [])
            for im in removed:
                name = im.file.name
                im.delete()
                im.file.storage.delete(name)  # a removed picture must not linger on disk
            start = a.images.count()
            for i, data in enumerate(self._image_bytes):
                im = AchievementImage(achievement=a, position=start + i)
                im.file.save(new_storage_name("jpg"), ContentFile(data), save=False)
                im.save()
            video_changed = False
            current = AchievementVideo.objects.filter(achievement=a).first()
            if current is not None and (self._video is not None or self.cleaned_data.get("remove_video")):
                name = current.file.name
                current.delete()
                current.file.storage.delete(name)  # a replaced or removed video must not linger on disk
                video_changed = True
            if self._video is not None:
                v = AchievementVideo(achievement=a, content_type=self._video.content_type, size=len(self._video.data), sha256=self._video.sha256, scan_status=self._video.scan_status)
                v.file.save(new_storage_name(self._video.ext), ContentFile(self._video.data), save=False)
                v.save()
                video_changed = True
            if removed or self._image_bytes or video_changed:
                a.save(update_fields=["updated_at"])  # the pictures and the video belong to the version a preview refers to
        return a


class CommentForm(forms.Form):
    comment = forms.CharField(label=_("Muallif uchun izoh"), max_length=2000, widget=forms.Textarea(attrs={**INPUT, "rows": 3}))
