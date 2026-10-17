from django.conf import settings
from django.utils.cache import add_never_cache_headers

# Pages that show or change account data must never be stored by browsers or shared caches.
NO_STORE_PREFIXES = ("/accounts/", "/portal/", "/" + getattr(settings, "ADMIN_URL", "admin/"))


class SecurityHeadersMiddleware:
    """CSP (report-only until enforced), Permissions-Policy and no-store for account pages.

    HSTS is handled by Django's SecurityMiddleware, which emits it only on HTTPS requests and only when
    SECURE_HSTS_SECONDS > 0 (production, after HTTPS is verified) — never for plain-HTTP environments.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        header = "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
        if settings.CSP_POLICY:
            response.headers.setdefault(header, settings.CSP_POLICY)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        if request.path.startswith(NO_STORE_PREFIXES):
            add_never_cache_headers(response)
        return response
