"""Shared Django settings. Secrets and environment-specific values come ONLY from environment variables.

Local development reads backend/.env (never committed; see .env.example).
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend
REPO_ROOT = BASE_DIR.parent  # repository root (static demo lives here and is reused read-only)

try:  # development convenience; real environment variables always win
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Environment variable {name} is required (see backend/.env.example).")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return str(os.environ.get(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
ADMIN_URL = (env("DJANGO_ADMIN_URL", "admin/") or "admin/").lstrip("/")
if not ADMIN_URL.endswith("/"):
    ADMIN_URL += "/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.organization",
    "apps.access",
    "apps.content",
    "apps.audit",
    "apps.tasks",
    "apps.documents",
    "apps.notifications",
    "apps.reports",
    "apps.portal",
]

MIDDLEWARE = [
    "apps.core.network.TrustedProxyMiddleware",  # first: decides is_secure() from a TRUSTED proxy only
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.TwoFactorEnforcementMiddleware",  # needs auth + messages above
    "apps.accounts.middleware.MustChangePasswordMiddleware",  # after 2FA: first prove identity, then change the password
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- Reverse proxy. Forwarded headers (client IP, scheme) are believed ONLY from these addresses/networks.
# Empty = direct connections only (safe default). Set to the proxy's address(es) when deployed behind Nginx, e.g.
# DJANGO_TRUSTED_PROXIES=127.0.0.1,::1   (see docs/PRODUCTION_SECURITY_REQUIREMENTS.md, B-1)
from apps.core.network import parse_trusted_proxies  # noqa: E402

TRUSTED_PROXIES = env_list("DJANGO_TRUSTED_PROXIES")
TRUSTED_PROXY_NETWORKS = parse_trusted_proxies(TRUSTED_PROXIES)

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",  # LANGUAGE_CODE for <html lang>
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notifications.context.unread",
                "apps.core.context_processors.site",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", required=True),
        "USER": env("DB_USER", required=True),
        "PASSWORD": env("DB_PASSWORD", required=True),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication -------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrUsernameBackend"]
# Argon2 first; PBKDF2 stays only so older hashes can be verified and upgraded.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "portal:dashboard"
LOGOUT_REDIRECT_URL = "content:home"

# Password-reset links live 30 minutes; they are HMAC tokens (nothing stored) and die when the password changes.
PASSWORD_RESET_TIMEOUT = 60 * 30

# --- Rate limiting (apps.accounts.throttle). max = attempts allowed before the lock; seconds for window/lock.
# login:identifier and login:user are per account (all IPs); login:ip is higher because many staff may share one
# office address (NAT). Counting is atomic in PostgreSQL, so it is valid across processes and servers.
THROTTLE_POLICIES = {
    "login:identifier": {"max": 5, "window": 900, "lock": 900},
    "login:user": {"max": 5, "window": 900, "lock": 900},
    "login:ip": {"max": 20, "window": 900, "lock": 900},
    "pwchange:user": {"max": 5, "window": 900, "lock": 900},
    "otp:user": {"max": 5, "window": 900, "lock": 900},
    "otp:ip": {"max": 20, "window": 900, "lock": 900},
    "reset:ip": {"max": 5, "window": 3600, "lock": 3600},
    "reset:email": {"max": 3, "window": 3600, "lock": 3600},
    "csp:ip": {"max": 60, "window": 3600, "lock": 3600},
    "invite:user": {"max": 5, "window": 3600, "lock": 3600},  # invitation e-mails per account per hour
}

# --- Two-factor authentication (TOTP)
TWO_FACTOR_REQUIRED_ROLES = ["admin", "sysadmin"]  # superusers are always required as well
TWO_FACTOR_PENDING_SECONDS = 300  # time allowed between the password step and the code step
TWO_FACTOR_ISSUER = "Mirzacho‘l XTB"
# Comma-separated Fernet keys (newest first) used to encrypt TOTP secrets at rest. Never commit real keys.
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
OTP_ENCRYPTION_KEYS = env_list("OTP_ENCRYPTION_KEYS")

# --- E-mail. Default writes messages to files (never to the network); production must configure SMTP explicitly.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.filebased.EmailBackend")
EMAIL_FILE_PATH = BASE_DIR / ".dev_mail"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@localhost")

# --- Sessions / cookies / browser protections -----------------------------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # applies only when "Meni eslab qolish" is ticked
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# --- Content-Security-Policy (REPORT-ONLY at first: violations are reported to /csp-report/, nothing is blocked).
# No 'unsafe-eval' and no 'unsafe-inline' for scripts or stylesheets. style-src-attr allows inline style="..."
# attributes only, because the shared design system uses them; plan: remove them, then drop this exception.
CSP_REPORT_ONLY = env_bool("DJANGO_CSP_REPORT_ONLY", True)
CSP_DIRECTIVES = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    "style-src-attr": ["'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
    "report-uri": ["/csp-report/"],
}
CSP_POLICY = "; ".join(f"{name} {' '.join(values)}" for name, values in CSP_DIRECTIVES.items())
# geolocation stays disabled until the attendance/geolocation stage is approved by the legal checklist.
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

# --- Internationalisation (uz first; ru/en translations come later) -------
LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O‘zbekcha"), ("ru", "Русский"), ("en", "English")]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# --- Static files: Django's own + the existing static demo's assets (reused, not copied)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    ("assets", REPO_ROOT / "assets"),  # -> /static/assets/css/styles.css, /static/assets/js/app.js
]

# --- Logging --------------------------------------------------------------
LOG_LEVEL = (env("DJANGO_LOG_LEVEL", "INFO") or "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "apps.core.logging.RedactSecretsFilter"}},
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["redact"]}},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}


# --- Documents: private storage (no URL, outside static/media) and upload limits.
PRIVATE_MEDIA_ROOT = Path(env("DJANGO_PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")))
DOCUMENT_MAX_BYTES = int(env("DOCUMENT_MAX_BYTES", str(10 * 1024 * 1024)))
# Django reads the whole request body limit for non-file fields only; files above this go to a temp file on disk.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 1 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o600

# --- Notifications: e-mail copies are OFF unless explicitly enabled (and SMTP configured).
NOTIFICATION_EMAILS_ENABLED = env_bool("NOTIFICATION_EMAILS_ENABLED", False)

# --- Antivirus for uploads (ClamAV, local daemon only). Fail-closed: if the scan cannot finish, the upload is refused.
# "disabled" exists for local development and tests ONLY; production refuses to start with it.
DOCUMENT_SCAN_MODE = env("DOCUMENT_SCAN_MODE", "clamav")
CLAMAV_SOCKET = env("CLAMAV_SOCKET", "")  # e.g. /run/clamav/clamd.ctl ; empty = use host/port below
CLAMAV_HOST = env("CLAMAV_HOST", "127.0.0.1")
CLAMAV_PORT = int(env("CLAMAV_PORT", "3310"))
CLAMAV_TIMEOUT = float(env("CLAMAV_TIMEOUT", "20"))  # seconds for the whole scan
if DOCUMENT_SCAN_MODE not in ("clamav", "disabled"):
    raise ImproperlyConfigured("DOCUMENT_SCAN_MODE must be 'clamav' or 'disabled'.")

# --- Reports: hard limits so one request cannot ask for an unbounded amount of data.
REPORT_MAX_DAYS = 366          # longest date range
REPORT_MAX_ROWS = 500          # rows per table on screen and in Excel/PDF (the rest is summarised as "and N more")
REPORT_PDF_MAX_ROWS = 60       # rows per table in the PDF
