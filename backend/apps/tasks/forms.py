from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.organization.models import Institution

from .models import Task, TaskComment

INPUT = {"class": "input"}
User = get_user_model()


class UserChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.get_username()


class TaskForm(forms.ModelForm):
    assignees = UserChoiceField(
        queryset=User.objects.none(), label=_("Ijrochilar"), required=False, widget=forms.SelectMultiple(attrs={**INPUT, "size": 8})
    )
    # Giving a task to a school means giving it to its director: the only person who signs in from a school.
    institutions = forms.ModelMultipleChoiceField(
        queryset=Institution.objects.none(), label=_("Ta’lim muassasalari"), required=False,
        widget=forms.SelectMultiple(attrs={**INPUT, "size": 8}),
        help_text=_("Topshiriq tanlangan muassasa direktoriga beriladi."),
    )

    class Meta:
        model = Task
        fields = ["title", "description", "priority", "due_date", "due_time", "assignees"]
        widgets = {
            "title": forms.TextInput(attrs=INPUT),
            "description": forms.Textarea(attrs={**INPUT, "rows": 6}),
            "priority": forms.Select(attrs=INPUT),
            "due_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
            "due_time": forms.TimeInput(attrs={**INPUT, "type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, assignable, can_assign_schools=False, **kwargs):
        super().__init__(*args, **kwargs)
        if can_assign_schools:
            self.fields["institutions"].queryset = Institution.objects.all()
        else:
            del self.fields["institutions"]
        self.fields["due_time"].help_text = _("Vaqt ko‘rsatilmasa, muddat o‘sha kun oxirigacha hisoblanadi.")
        keep = self.instance.assignees.all() if self.instance.pk else User.objects.none()
        self.fields["assignees"].queryset = User.objects.filter(Q(pk__in=assignable.values("pk")) | Q(pk__in=keep.values("pk"))).order_by("last_name", "first_name", "username")  # existing assignees stay valid even if outside scope
        self.fields["assignees"].help_text = _("Bir nechta ijrochini Ctrl (⌘) bosib tanlang.")

    def clean(self):
        data = super().clean()
        people = list(data.get("assignees") or [])
        missing = []
        for school in data.get("institutions") or []:
            directors = User.objects.filter(
                is_active=True, role_assignments__role__name="school_director", role_assignments__scope="institution", employee__institution=school
            ).distinct()
            if directors:
                people += [d for d in directors if d not in people]
            else:
                missing.append(school.name)
        if missing:
            self.add_error("institutions", _("Direktor hisobi yo‘q muassasalar: %(names)s.") % {"names": ", ".join(missing)})
        elif not people:
            if "institutions" in self.fields:
                self.add_error("assignees", _("Kamida bitta ijrochi yoki muassasa tanlang."))
            else:  # no school picker for this user: the field is simply required, as before
                self.add_error("assignees", self.fields["assignees"].error_messages["required"])
        data["assignees"] = people
        return data

    def clean_due_time(self):
        value = self.cleaned_data.get("due_time")
        if value and not self.data.get("due_date"):
            raise forms.ValidationError(_("Vaqt uchun avval sanani ko‘rsating."))
        return value


class CommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={**INPUT, "rows": 3})}
        labels = {"body": _("Izoh")}
