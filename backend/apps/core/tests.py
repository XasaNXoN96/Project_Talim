from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse


class CoreRoutesTests(TestCase):
    def test_healthz_reports_database_ok(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_unknown_url_uses_custom_404_page(self):
        response = self.client.get("/bunday-sahifa-yoq/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Sahifa topilmadi", status_code=404)

    def test_500_template_renders_without_request_or_database(self):
        html = render_to_string("errors/500.html")
        self.assertIn("Serverda xatolik", html)

    def test_security_headers(self):
        response = self.client.get(reverse("content:home"))
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_session_cookie_is_httponly_and_samesite(self):
        from django.conf import settings

        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_admin_requires_login(self):
        from django.conf import settings

        response = self.client.get("/" + settings.ADMIN_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
