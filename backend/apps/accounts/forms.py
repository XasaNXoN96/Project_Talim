from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Elektron pochta yoki login",
        max_length=254,
        widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True, "class": "input"}),
    )
    password = forms.CharField(
        label="Parol",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "input"}),
    )
    remember_me = forms.BooleanField(label="Meni eslab qolish", required=False)

    error_messages = {
        "invalid_login": "Login yoki parol noto‘g‘ri. Qaytadan urinib ko‘ring.",
        "inactive": "Bu hisob faol emas.",
    }
