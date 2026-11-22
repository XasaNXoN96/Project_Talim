"""One-off setup of the demo database (migrate, then load the demo data). Needs the secret SETUP_TOKEN in the X-Setup-Token header."""
import hmac
import io
import os
import sys
from urllib.parse import parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.vercel")

import django  # noqa: E402

django.setup()
from django.core.management import call_command  # noqa: E402


def app(environ, start_response):
    def reply(code, text):
        body = text.encode()
        start_response(code, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    secret = os.environ.get("SETUP_TOKEN", "")
    if not secret or not hmac.compare_digest(environ.get("HTTP_X_SETUP_TOKEN", ""), secret):
        return reply("403 Forbidden", "no")
    step = (parse_qs(environ.get("QUERY_STRING", "")).get("step") or [""])[0]
    out = io.StringIO()
    try:
        if step == "migrate":
            call_command("migrate", interactive=False, stdout=out, verbosity=1)
        elif step == "reset":
            call_command("flush", interactive=False, stdout=out, verbosity=1)  # empties every table, the demo file is then loaded again
        elif step == "load":
            from apps.documents.models import DocumentCategory

            DocumentCategory.objects.all().delete()  # the migrations seed their own; the demo file brings its own with the same names
            call_command("loaddata", os.path.join(os.path.dirname(__file__), "..", "backend", "demo", "demo.json"), verbosity=1, stdout=out)
        elif step == "status":
            from apps.accounts.models import User
            from apps.achievements.models import Achievement
            from apps.content.models import News

            out.write(f"users={User.objects.count()} news={News.objects.count()} achievements={Achievement.objects.count()}")
        else:
            return reply("400 Bad Request", "step=migrate|reset|load|status")
    except Exception as exc:  # noqa: BLE001 - the operator needs the class and message of any failure
        return reply("500 Internal Server Error", f"{type(exc).__name__}: {str(exc)[:600]}")
    return reply("200 OK", out.getvalue() or "ok")
