"""ONLINE DEMO on Vercel (serverless). FICTITIOUS data only; never for real people or a real installation.

* The database is an external PostgreSQL (Neon) given by DATABASE_URL / POSTGRES_URL.
* Files live in /tmp: the demo pictures shipped with the deployment are copied there when an instance starts. Uploaded files are NOT kept
  for long (a serverless instance is temporary).
* The second factor is skipped (DEMO_PREVIEW), the antivirus is off, e-mail goes to the log. The deployment itself should stay behind Vercel's
  own sign-in (Deployment Protection) unless the owner decides otherwise.
"""
import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

_url = urlparse(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "")
os.environ.setdefault("DB_NAME", (_url.path or "/").lstrip("/") or "neondb")
os.environ.setdefault("DB_USER", unquote(_url.username or ""))
os.environ.setdefault("DB_PASSWORD", unquote(_url.password or ""))
os.environ.setdefault("DB_HOST", _url.hostname or "127.0.0.1")
os.environ.setdefault("DB_PORT", str(_url.port or 5432))
os.environ.setdefault("DOCUMENT_SCAN_MODE", "disabled")
os.environ.setdefault("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

from .base import *  # noqa: E402,F401,F403

DEBUG = False
DEMO_PREVIEW = True
DEV_SKIP_TWO_FACTOR = True
ALLOWED_HOSTS = [".vercel.app", "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Vercel's edge sets it
DATABASES["default"]["OPTIONS"] = {"sslmode": "require"}  # noqa: F405
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True  # noqa: F405  (a pooled connection)
DATABASES["default"]["CONN_MAX_AGE"] = 120  # noqa: F405  (a warm instance reuses its database connection instead of opening a new TLS one per request)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405  (a connection the database closed meanwhile is replaced, not an error)

# The pictures that ship with the deployment are read-only; copy them to /tmp once per instance.
_SHIPPED = Path(__file__).resolve().parents[2] / "private_media"
PRIVATE_MEDIA_ROOT = Path("/tmp/private_media")
if _SHIPPED.is_dir() and not PRIVATE_MEDIA_ROOT.exists():
    shutil.copytree(_SHIPPED, PRIVATE_MEDIA_ROOT)
EMAIL_FILE_PATH = Path("/tmp/dev_mail")
STATIC_URL = "/static/"  # served by Vercel's CDN from public/static
