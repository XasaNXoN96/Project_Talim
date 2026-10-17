import logging

from django.db import connection
import json

from django.http import HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

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


MAX_CSP_REPORT_BYTES = 8192


@csrf_exempt  # browsers send CSP reports without cookies or CSRF tokens; the endpoint only logs, it changes no data
@require_POST
def csp_report(request):
    """Receives Content-Security-Policy violation reports. Size-limited, rate-limited per IP, logged without secrets."""
    from apps.accounts import throttle
    from apps.audit.services import client_ip

    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = MAX_CSP_REPORT_BYTES + 1
    if length > MAX_CSP_REPORT_BYTES:
        return HttpResponse(status=413)
    reservation = throttle.reserve([throttle.Key("csp:ip", client_ip(request) or "unknown", "keep")])
    if reservation.allowed:
        try:
            data = json.loads(request.body[:MAX_CSP_REPORT_BYTES] or b"{}")
        except ValueError:
            data = {}
        report = data.get("csp-report") if isinstance(data, dict) else None
        if not isinstance(report, dict):  # hostile or malformed bodies are accepted silently, never an error
            report = {}
        def clean(value):  # drop query strings/fragments (they can carry tokens) and cap the length
            return str(value or "").split("?")[0].split("#")[0][:200]
        logger.warning(
            "CSP report: directive=%s blocked=%s document=%s",
            clean(report.get("effective-directive") or report.get("violated-directive")),
            clean(report.get("blocked-uri")),
            clean(report.get("document-uri")),
        )
    return HttpResponse(status=204)  # identical answer whether or not the report was kept
