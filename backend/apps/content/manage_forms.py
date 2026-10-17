import secrets

from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .models import News, NewsCategory

INPUT = {"class": "input"}
BODY_MAX = 20000
EXCERPT_MAX = 500


def unique_slug(model, text, fallback, *, max_length):
    """URL-safe slug from `text` (Latin only: Cyrillic or empty titles fall back), unique within `model`."""
    base = slugify(text)[: max_length - 8].strip("-") or fallback
    slug = base
    while model.objects.filter(slug=slug).exists():
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


class NewsForm(forms.ModelForm):
    publish_at = forms.DateTimeField(
        label=_("Nashr sanasi (ixtiyoriy)"), required=False,
        widget=forms.DateTimeInput(attrs={**INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        help_text=_("Kelajakdagi sana bersangiz, yangilik shu vaqtdan boshlab ko‘rinadi. Bo‘sh qoldirsangiz, nashr qilingan zahoti ko‘rinadi."),
    )

    class Meta:
        model = News
        fields = ["title", "excerpt", "body", "category", "publish_at"]
        widgets = {
            "title": forms.TextInput(attrs={**INPUT, "maxlength": 300}),
            "excerpt": forms.Textarea(attrs={**INPUT, "rows": 3, "maxlength": EXCERPT_MAX}),
            "body": forms.Textarea(attrs={**INPUT, "rows": 14, "maxlength": BODY_MAX}),
            "category": forms.Select(attrs=INPUT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].label = _("Sarlavha")
        self.fields["excerpt"].label = _("Qisqa tavsif")
        self.fields["body"].label = _("Matn")
        self.fields["body"].help_text = _("Oddiy matn. Bo‘sh qator — yangi abzats. HTML va havolalar matn sifatida ko‘rinadi.")
        self.fields["category"].label = _("Kategoriya")
        self.fields["category"].required = False
        self.fields["category"].empty_label = _("— kategoriyasiz —")
        if self.instance.pk and self.instance.publish_at:
            from django.utils import timezone

            self.initial["publish_at"] = timezone.localtime(self.instance.publish_at)

    def clean_publish_at(self):
        value = self.cleaned_data["publish_at"]
        if value is None and self.instance.pk and self.instance.status == News.Status.PUBLISHED:
            return self.instance.publish_at  # a live item always keeps a date (and an empty field must not unpublish it)
        return value

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if not title:
            raise forms.ValidationError(_("Sarlavha bo‘sh bo‘lmasligi kerak."))
        return title

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError(_("Matn bo‘sh bo‘lmasligi kerak."))
        if len(body) > BODY_MAX:
            raise forms.ValidationError(_("Matn juda uzun (ko‘pi bilan %(n)d belgi).") % {"n": BODY_MAX})
        return body

    def clean_excerpt(self):
        excerpt = self.cleaned_data["excerpt"].strip()
        if len(excerpt) > EXCERPT_MAX:
            raise forms.ValidationError(_("Qisqa tavsif juda uzun (ko‘pi bilan %(n)d belgi).") % {"n": EXCERPT_MAX})
        return excerpt

    def save(self, commit=True):
        news = super().save(commit=False)
        if not news.slug:
            news.slug = unique_slug(News, news.title, "yangilik", max_length=320)
        if commit:
            news.save()
        return news


class NewsCategoryForm(forms.ModelForm):
    class Meta:
        model = NewsCategory
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={**INPUT, "maxlength": 100})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = _("Nomi")

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError(_("Nomi bo‘sh bo‘lmasligi kerak."))
        if NewsCategory.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Bunday kategoriya allaqachon bor."))
        return name

    def save(self, commit=True):
        category = super().save(commit=False)
        if not category.slug:
            category.slug = unique_slug(NewsCategory, category.name, "kategoriya", max_length=120)
        if commit:
            category.save()
        return category
