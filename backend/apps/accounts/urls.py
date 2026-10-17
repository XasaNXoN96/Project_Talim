from django.contrib.auth.views import LogoutView
from django.db import transaction
from django.urls import path

from . import views

app_name = "accounts"

# Views that update attempt counters are not wrapped in the per-request transaction (ATOMIC_REQUESTS): counters
# must persist even when the request later fails.
na = transaction.non_atomic_requests

urlpatterns = [
    path("login/", na(views.LoginView.as_view()), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),  # POST only (Django 5)
    # two-factor
    path("2fa/verify/", na(views.TwoFactorVerifyView.as_view()), name="two_factor_verify"),
    path("2fa/setup/", na(views.TwoFactorSetupView.as_view()), name="two_factor_setup"),
    path("security/", views.SecurityView.as_view(), name="security"),
    path("security/backup-codes/", na(views.BackupCodesRegenerateView.as_view()), name="backup_codes_regenerate"),
    path("security/2fa-disable/", na(views.TwoFactorDisableView.as_view()), name="two_factor_disable"),
    # password
    path("password-change/", na(views.PasswordChangeView.as_view()), name="password_change"),
    path("password-change/done/", views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("password-reset/", na(views.PasswordResetRequestView.as_view()), name="password_reset"),
    path("password-reset/done/", views.PasswordResetDone.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.PasswordResetConfirm.as_view(), name="password_reset_confirm"),
    path("reset/done/", views.PasswordResetComplete.as_view(), name="password_reset_complete"),
]
