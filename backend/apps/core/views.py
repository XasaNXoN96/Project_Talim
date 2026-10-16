import logging

from django.db import connection
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def healthz(request):
    """Liveness + database check. Does not reveal error details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
    except Exception:  # noqa: BLE001
        logger.exception("Health check: database unavailable")
        database = "error"
    ok = database == "ok"
    return JsonResponse({"status": "ok" if ok else "degraded", "database": database}, status=200 if ok else 503)


def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def csrf_failure(request, reason=""):
    logger.warning("CSRF failure: %s", reason)
    return render(request, "errors/403.html", {"csrf": True}, status=403)


def error_500(request):
    # Rendered WITHOUT a request: no context processors, no session, no database access.
    return HttpResponseServerError(render_to_string("errors/500.html"))
