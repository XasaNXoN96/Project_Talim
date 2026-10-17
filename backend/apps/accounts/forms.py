import hashlib
import logging

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template import loader

from apps.audit.models import AuditLog
from apps.audit.services import client_ip, record
from apps.core.network import throttle_ip_key

from . import throttle
from .backends import find_login_user

logger = logging.getLogger(__name__)

# One message for "wrong credentials" AND "temporarily blocked": the response never reveals which, nor whether
# the login/e-mail exists.
NEUTRAL_LOGIN_ERROR = "Login yoki parol noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring."
NEUTRAL_CODE_ERROR = "Kod noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring."
NEUTRAL_PASSWORD_ERROR = "Joriy parol noto‘g‘ri yoki urinishlar soni chegaradan oshgan. 15 daqiqadan so‘ng qayta urinib ko‘ring."


def short_hash(value: str) -> str:
    """Audit-safe fingerprint: never the raw identifier (it may be a mistyped password)."""
    return hashlib.sha256(str(value).strip().lower().encode("utf-8")).hexdigest()[:16]


def login_keys(request, identifier, user):
    keys = [
        throttle.Key("login:identifier", str(identifier).strip().lower()[:254], "clear"),
        throttle.Key("login:ip", throttle_ip_key(client_ip(request)), "refund"),
    ]
    if user is not None:
        keys.append(throttle.Key("login:user", str(user.pk), "clear"))
    return keys


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

    error_messages = {"invalid_login": NEUTRAL_LOGIN_ERROR, "inactive": NEUTRAL_LOGIN_ERROR}

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username is None or password is None:
            return self.cleaned_data

        user = find_login_user(username)
        keys = login_keys(self.request, username, user)
        reservation = throttle.reserve(keys)  # counted BEFORE the password is checked (parallel-safe)
        fingerprint = short_hash(username)

        if not reservation.allowed:
            get_user_model()().set_password(password)  # same cost as a real check: lock state is not observable by timing
            if reservation.audit_blocked:
                record(AuditLog.Action.LOGIN_BLOCKED, request=self.request, user=user,
                       meta={"kinds": reservation.blocked_kinds, "identifier_sha256_16": fingerprint})
            raise self.get_invalid_login_error()

        self.user_cache = authenticate(self.request, username=username, password=password)
        if self.user_cache is None:
            if reservation.newly_locked:
                record(AuditLog.Action.LOGIN_LOCKED, request=self.request, user=user,
                       meta={"kinds": reservation.newly_locked, "identifier_sha256_16": fingerprint})
            raise self.get_invalid_login_error()

        self.confirm_login_allowed(self.user_cache)
        throttle.succeed(keys, reservation)
        return self.cleaned_data


class ThrottledPasswordChangeForm(PasswordChangeForm):
    """Current-password check is rate limited too: a hijacked session must not be able to guess it."""

    request = None
    error_messages = {**PasswordChangeForm.error_messages, "password_incorrect": NEUTRAL_PASSWORD_ERROR}

    def clean_old_password(self):
        old_password = self.cleaned_data["old_password"]
        keys = [throttle.Key("pwchange:user", str(self.user.pk), "clear")]
        reservation = throttle.reserve(keys)
        if not reservation.allowed or not self.user.check_password(old_password):
            if reservation.allowed and reservation.newly_locked:
                record(AuditLog.Action.LOGIN_LOCKED, request=self.request, user=self.user, meta={"kinds": reservation.newly_locked})
            raise ValidationError(self.error_messages["password_incorrect"], code="password_incorrect")
        throttle.succeed(keys, reservation)
        return old_password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password1")
        if password and "new_password1" not in self.errors and self.user.check_password(password):
            self.add_error("new_password1", ValidationError("Yangi parol joriy paroldan farq qilishi kerak.", code="password_unchanged"))
        return cleaned


class ThrottledPasswordResetForm(PasswordResetForm):
    """Same visible result whether or not the e-mail exists, and whether or not the request was rate limited."""

    def save(self, request=None, **kwargs):
        email = self.cleaned_data["email"].strip().lower()
        keys = [throttle.Key("reset:ip", throttle_ip_key(client_ip(request)), "keep"), throttle.Key("reset:email", email, "keep")]
        reservation = throttle.reserve(keys)
        fingerprint = short_hash(email)
        if not reservation.allowed:
            if reservation.audit_blocked:
                record(AuditLog.Action.PASSWORD_RESET_THROTTLED, request=request,
                       meta={"kinds": reservation.blocked_kinds, "email_sha256_16": fingerprint})
            return
        record(AuditLog.Action.PASSWORD_RESET_REQUESTED, request=request, meta={"email_sha256_16": fingerprint})
        super().save(request=request, **kwargs)

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        """Same as Django's, but a delivery failure is logged as a bare error TYPE.

        Django's own version logs a full traceback, and SMTP exceptions can contain the recipient's address.
        The visible answer is the same either way, so a failure never reveals that the account exists.
        """
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            message.attach_alternative(loader.render_to_string(html_email_template_name, context), "text/html")
        try:
            message.send()
        except Exception as exc:  # noqa: BLE001
            logger.error("Password-reset e-mail could not be sent (%s)", type(exc).__name__)


class OtpCodeForm(forms.Form):
    code = forms.CharField(
        label="Tasdiqlash kodi yoki zaxira kod",
        max_length=32,
        strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "text", "autofocus": True, "class": "input"}),
    )


class TotpSetupForm(forms.Form):
    code = forms.CharField(
        label="Ilovadagi 6 xonali kod",
        max_length=12,
        strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True, "class": "input"}),
    )


class PasswordConfirmForm(forms.Form):
    password = forms.CharField(
        label="Joriy parol",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "input"}),
    )
