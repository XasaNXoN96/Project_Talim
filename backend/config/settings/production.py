"""Production SKELETON — not deployed, not used on Day 1.

Refuses to start without explicit secrets and hosts. Real values are provided only through the
server's environment (never committed). TLS-related switches default to the secure choice.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a long random value.")

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Enable only after HTTPS is verified end-to-end; then raise towards one year.
SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0") or 0)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False
# NOTE: SECURE_PROXY_SSL_HEADER is deliberately NOT used: it believes the header from any client. HTTPS detection
# behind a proxy is done by apps.core.network.TrustedProxyMiddleware, only for peers listed in DJANGO_TRUSTED_PROXIES.
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405
# __Host- cookies are only accepted over HTTPS, without a Domain, for path "/": prevents subdomain cookie injection.
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_NAME = "__Host-csrftoken"

# TOTP secrets cannot be stored without an encryption key.
if not OTP_ENCRYPTION_KEYS:  # noqa: F405
    raise ImproperlyConfigured("OTP_ENCRYPTION_KEYS must be set in production.")

# Real mail is sent only through an explicitly configured SMTP server.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", required=True)  # noqa: F405
EMAIL_PORT = int(env("EMAIL_PORT", "587") or 587)  # noqa: F405
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")  # noqa: F405
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")  # noqa: F405
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)  # noqa: F405
if not env("DEFAULT_FROM_EMAIL"):  # noqa: F405
    raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must be set in production.")
