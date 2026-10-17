import io

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView as DjangoLoginView,
    PasswordChangeView as DjangoPasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, TemplateView
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import client_ip, record
from apps.core.network import throttle_ip_key

from . import otp, throttle
from .forms import (
    NEUTRAL_CODE_ERROR,
    NEUTRAL_PASSWORD_ERROR,
    LoginForm,
    OtpCodeForm,
    PasswordConfirmForm,
    ThrottledPasswordChangeForm,
    ThrottledPasswordResetForm,
    TotpSetupForm,
)
from .notifications import notify_security_event
from .sessions import invalidate_user_sessions
from .twofactor import (
    clear_pending,
    complete_login,
    get_pending,
    has_confirmed_device,
    must_verify_two_factor,
    requires_two_factor,
    start_pending,
)

User = get_user_model()


# ----------------------------------------------------------------- sign in
@method_decorator(never_cache, name="dispatch")
class LoginView(DjangoLoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        remember = bool(form.cleaned_data.get("remember_me"))
        next_url = self.get_success_url()
        if must_verify_two_factor(user):
            # Not signed in yet: the session only remembers that the password step passed.
            start_pending(self.request, user, user.backend, remember, next_url)
            return redirect("accounts:two_factor_verify" if has_confirmed_device(user) else "accounts:two_factor_setup")
        complete_login(self.request, user, user.backend, remember, verified=False)
        return HttpResponseRedirect(next_url)


# ------------------------------------------------------- two-factor helpers
def _otp_keys(request, user):
    return [throttle.Key("otp:user", str(user.pk), "clear"), throttle.Key("otp:ip", throttle_ip_key(client_ip(request)), "refund")]


def qr_svg(uri: str):
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode()
    return mark_safe(svg[svg.index("<svg"):])  # generated locally from the otpauth URI; contains no user input as markup


def grouped(secret: str) -> str:
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


class PendingOrSignedInMixin:
    """Acting user = the pending (password-verified) user, or the signed-in user."""

    pending = None

    def get_actor(self, request):
        if request.user.is_authenticated:
            return request.user
        found = get_pending(request)
        if found:
            self.pending = found[1]
            return found[0]
        return None


# ---------------------------------------------------------- verify (login)
@method_decorator(never_cache, name="dispatch")
class TwoFactorVerifyView(FormView):
    template_name = "accounts/two_factor_verify.html"
    form_class = OtpCodeForm

    def dispatch(self, request, *args, **kwargs):
        found = get_pending(request)
        if not found:
            messages.error(request, _("Kirish muddati tugadi. Qaytadan kiring."))
            return redirect("accounts:login")
        self.user, self.pending = found
        if not has_confirmed_device(self.user):
            return redirect("accounts:two_factor_setup")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        code = form.cleaned_data["code"]
        keys = _otp_keys(self.request, self.user)
        reservation = throttle.reserve(keys)  # counted before the code is checked
        if not reservation.allowed:
            if reservation.audit_blocked:
                record(AuditLog.Action.TWO_FACTOR_BLOCKED, request=self.request, user=self.user, meta={"kinds": reservation.blocked_kinds})
            form.add_error(None, NEUTRAL_CODE_ERROR)
            return self.form_invalid(form)

        used_backup = False
        if otp.normalise_totp_code(code):
            ok = otp.verify_totp(self.user.totp_device, code)
        else:
            ok = used_backup = otp.verify_backup_code(self.user, code)

        if not ok:
            record(AuditLog.Action.TWO_FACTOR_FAILED, request=self.request, user=self.user)
            if reservation.newly_locked:
                record(AuditLog.Action.TWO_FACTOR_LOCKED, request=self.request, user=self.user, meta={"kinds": reservation.newly_locked})
            form.add_error(None, NEUTRAL_CODE_ERROR)
            return self.form_invalid(form)

        throttle.succeed(keys, reservation)
        if used_backup:
            record(AuditLog.Action.TWO_FACTOR_BACKUP_USED, request=self.request, user=self.user,
                   meta={"remaining": otp.remaining_backup_codes(self.user)})
        next_url = self.pending["next"]
        complete_login(self.request, self.user, self.pending["backend"], self.pending["remember"], verified=True)
        if used_backup and otp.remaining_backup_codes(self.user) <= 2:
            messages.warning(self.request, _("Zaxira kodlaringiz kam qoldi. Yangilarini yarating."))
        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        return super().get_context_data(username=self.user.get_username(), **kwargs)


# ------------------------------------------------------------- enrolment
@method_decorator(never_cache, name="dispatch")
class TwoFactorSetupView(PendingOrSignedInMixin, FormView):
    """Enrol an authenticator app. Used for first sign-in of privileged users and for voluntary opt-in."""

    template_name = "accounts/two_factor_setup.html"
    form_class = TotpSetupForm

    def dispatch(self, request, *args, **kwargs):
        self.user = self.get_actor(request)
        if self.user is None:
            messages.error(request, _("Kirish muddati tugadi. Qaytadan kiring."))
            return redirect("accounts:login")
        if has_confirmed_device(self.user):
            return redirect("accounts:security" if request.user.is_authenticated else "accounts:two_factor_verify")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "restart" in request.POST:
            otp.regenerate_pending_secret(self.user)
            return redirect("accounts:two_factor_setup")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        device = otp.get_or_create_pending_device(self.user)
        secret = otp.decrypt_secret(device.secret_encrypted)
        return super().get_context_data(
            qr=qr_svg(otp.provisioning_uri(device)), secret=grouped(secret), username=self.user.get_username(),
            required=requires_two_factor(self.user), **kwargs,
        )

    def form_valid(self, form):
        device = otp.get_or_create_pending_device(self.user)
        keys = _otp_keys(self.request, self.user)
        reservation = throttle.reserve(keys)
        if not reservation.allowed and reservation.audit_blocked:
            record(AuditLog.Action.TWO_FACTOR_BLOCKED, request=self.request, user=self.user, meta={"stage": "setup", "kinds": reservation.blocked_kinds})
        if not reservation.allowed or not otp.verify_totp(device, form.cleaned_data["code"]):
            if reservation.allowed:
                record(AuditLog.Action.TWO_FACTOR_FAILED, request=self.request, user=self.user, meta={"stage": "setup"})
                if reservation.newly_locked:
                    record(AuditLog.Action.TWO_FACTOR_LOCKED, request=self.request, user=self.user, meta={"kinds": reservation.newly_locked})
            form.add_error(None, NEUTRAL_CODE_ERROR)
            return self.form_invalid(form)
        throttle.succeed(keys, reservation)
        otp.confirm_device(device)
        codes = otp.generate_backup_codes(self.user)
        record(AuditLog.Action.TWO_FACTOR_ENABLED, request=self.request, user=self.user)
        notify_security_event(self.user, "two_factor_enabled", self.request)
        next_url = reverse("portal:dashboard")
        if self.pending:
            next_url = self.pending["next"]
            complete_login(self.request, self.user, self.pending["backend"], self.pending["remember"], verified=True)
        else:
            self.request.session["two_factor_ok"] = True
        # Rendered directly (not redirected to): the codes exist in plaintext only in this one response.
        return self.response_class(self.request, "accounts/two_factor_backup_codes.html", {"codes": codes, "next": next_url}, status=200)


# --------------------------------------------------------- security page
@method_decorator(never_cache, name="dispatch")
class SecurityView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/security.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        return super().get_context_data(
            has_device=has_confirmed_device(user), required=requires_two_factor(user),
            remaining=otp.remaining_backup_codes(user), **kwargs,
        )


class _PasswordConfirmedAction(LoginRequiredMixin, FormView):
    """Base for sensitive actions that need the current password (rate limited like every password check)."""

    form_class = PasswordConfirmForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_confirmed_device(request.user):
            return redirect("accounts:security")
        return super().dispatch(request, *args, **kwargs)

    def password_ok(self, form):
        keys = [throttle.Key("pwchange:user", str(self.request.user.pk), "clear")]
        reservation = throttle.reserve(keys)
        if reservation.allowed and self.request.user.check_password(form.cleaned_data["password"]):
            throttle.succeed(keys, reservation)
            return True
        form.add_error(None, NEUTRAL_PASSWORD_ERROR)
        return False


@method_decorator(never_cache, name="dispatch")
class BackupCodesRegenerateView(_PasswordConfirmedAction):
    template_name = "accounts/two_factor_confirm.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=_("Zaxira kodlarni yangilash"), button=_("Yangi kodlar yaratish"),
                                        note=_("Eski zaxira kodlar bekor qilinadi."), **kwargs)

    def form_valid(self, form):
        if not self.password_ok(form):
            return self.form_invalid(form)
        codes = otp.generate_backup_codes(self.request.user)
        record(AuditLog.Action.TWO_FACTOR_BACKUP_REGENERATED, request=self.request, user=self.request.user)
        notify_security_event(self.request.user, "backup_codes_regenerated", self.request)
        return self.response_class(self.request, "accounts/two_factor_backup_codes.html", {"codes": codes, "next": reverse("accounts:security")}, status=200)


@method_decorator(never_cache, name="dispatch")
class TwoFactorDisableView(_PasswordConfirmedAction):
    template_name = "accounts/two_factor_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and requires_two_factor(request.user):
            messages.error(request, _("Sizning rolingiz uchun 2FA majburiy: uni o‘chirib bo‘lmaydi."))
            return redirect("accounts:security")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=_("2FA ni o‘chirish"), button=_("O‘chirish"), danger=True,
                                        note=_("Hisob faqat parol bilan himoyalanadi."), **kwargs)

    def form_valid(self, form):
        if not self.password_ok(form):
            return self.form_invalid(form)
        user = self.request.user
        user.backup_codes.all().delete()
        user.totp_device.delete()
        record(AuditLog.Action.TWO_FACTOR_DISABLED, request=self.request, user=user)
        notify_security_event(user, "two_factor_disabled", self.request)
        messages.success(self.request, _("2FA o‘chirildi."))
        return redirect("accounts:security")


# ------------------------------------------------------- password change
@method_decorator(never_cache, name="dispatch")
class PasswordChangeView(DjangoPasswordChangeView):
    form_class = ThrottledPasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.request = self.request
        return form

    def form_valid(self, form):
        response = super().form_valid(form)  # saves, keeps THIS session signed in (new auth hash, new session id)
        user = self.request.user
        removed = invalidate_user_sessions(user, keep_session_key=self.request.session.session_key)
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        record(AuditLog.Action.PASSWORD_CHANGED, request=self.request, user=user, meta={"other_sessions_closed": removed})
        notify_security_event(user, "password_changed", self.request)
        return response


class PasswordChangeDoneView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/password_change_done.html"


# -------------------------------------------------------- password reset
@method_decorator(never_cache, name="dispatch")
class PasswordResetRequestView(PasswordResetView):
    form_class = ThrottledPasswordResetForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDone(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


@method_decorator(never_cache, name="dispatch")
class PasswordResetConfirm(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    post_reset_login = False  # resetting a password must never sign anyone in (2FA could be bypassed)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        removed = invalidate_user_sessions(user)
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        # Proof of mailbox control lifts the lockouts of this account, whichever way it was typed (user id, login, e-mail).
        throttle.clear([
            throttle.Key("login:user", str(user.pk)),
            throttle.Key("login:identifier", user.get_username().strip().lower()[:254]),
            throttle.Key("login:identifier", user.email.strip().lower()[:254]),
            throttle.Key("otp:user", str(user.pk)),
            throttle.Key("pwchange:user", str(user.pk)),
        ])
        record(AuditLog.Action.PASSWORD_RESET_COMPLETED, request=self.request, user=user, meta={"sessions_closed": removed})
        notify_security_event(user, "password_reset", self.request)
        return response


class PasswordResetComplete(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
