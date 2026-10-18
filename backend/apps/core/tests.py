from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse


class CoreRoutesTests(TestCase):
    def test_healthz_reports_database_ok(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok", "grants": "ok"})

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


class HealthzPrivileges(TestCase):
    """The health check also notices a database role that cannot read every table (apply_grants.sql forgotten after a migration)."""

    def fake_connection(self, unreadable):
        from unittest import mock
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (unreadable,)
        conn = mock.MagicMock()
        conn.cursor.return_value = cursor
        return mock.patch("apps.core.views.connection", conn)

    def test_a_role_that_reads_every_table_is_healthy_and_reports_grants_ok(self):
        r = self.client.get(reverse("healthz"))
        self.assertEqual((r.status_code, r.json()), (200, {"status": "ok", "database": "ok", "grants": "ok"}))

    def test_a_role_that_cannot_read_a_table_makes_the_release_degraded_with_no_table_names(self):
        with self.fake_connection(2), self.assertLogs("apps.core.views", level="ERROR") as logs:
            r = self.client.get(reverse("healthz"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"status": "degraded", "database": "ok", "grants": "error"})
        self.assertIn("apply_grants.sql", "\n".join(logs.output))
