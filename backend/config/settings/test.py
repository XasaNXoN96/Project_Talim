"""Automated tests. Uses PostgreSQL like development (test_<DB_NAME> is created and dropped)."""
import os

# Test-only key: it protects nothing. Real keys never live in the repository.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-protects-nothing-0123456789-0123456789-0123456789")

from .base import *  # noqa: E402,F401,F403

DEBUG = False
# Fast hasher so the suite runs quickly. NEVER used outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ALLOWED_HOSTS = ["testserver", "localhost"]
# Test-only Fernet key: protects nothing.
OTP_ENCRYPTION_KEYS = ["Vd89ffgaIBKyfs3cTdxx0oY3ExI6vPux7GHTCBdWaTE="]
LOGGING["loggers"]["django"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["django.request"] = {"handlers": [], "level": "CRITICAL", "propagate": False}  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "CRITICAL"  # noqa: F405
