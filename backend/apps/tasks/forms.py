from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import Task, TaskComment

INPUT = {"class": "input"}
User = get_user_model()


class UserChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.get_username()


class TaskForm(forms.ModelForm):
    assignees = UserChoiceField(queryset=User.objects.none(), label=_("Ijrochilar"), widget=forms.SelectMultiple(attrs={**INPUT, "size": 8}))

    class Meta:
        model = Task
        fields = ["title", "description", "priority", "due_date", "assignees"]
        widgets = {
            "title": forms.TextInput(attrs=INPUT),
            "description": forms.Textarea(attrs={**INPUT, "rows": 6}),
            "priority": forms.Select(attrs=INPUT),
            "due_date": forms.DateInput(attrs={**INPUT, "type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, assignable, **kwargs):
        super().__init__(*args, **kwargs)
        keep = self.instance.assignees.all() if self.instance.pk else User.objects.none()
        self.fields["assignees"].queryset = User.objects.filter(Q(pk__in=assignable.values("pk")) | Q(pk__in=keep.values("pk"))).order_by("last_name", "first_name", "username")  # existing assignees stay valid even if outside scope
        self.fields["assignees"].help_text = _("Bir nechta ijrochini Ctrl (⌘) bosib tanlang.")

    def clean_assignees(self):
        users = self.cleaned_data["assignees"]
        if not users:
            raise forms.ValidationError(_("Kamida bitta ijrochi tanlang."))
        return users


class CommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={**INPUT, "rows": 3})}
        labels = {"body": _("Izoh")}
