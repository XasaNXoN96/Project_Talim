"""Vercel entry: the Django site (demo settings)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.vercel")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
