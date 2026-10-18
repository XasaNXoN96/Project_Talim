import json
import logging
import os
import re
import subprocess
import sys

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.logging import RedactSecretsFilter, redact

REPORT = reverse("csp_report")


def directives(header):
    return {part.split()[0]: part.split()[1:] for part in header.split(";") if part.strip()}


class SecurityHeaderTests(TestCase):
    def test_csp_is_report_only_by_default_and_never_enforcing(self):
        response = self.client.get(reverse("content:home"))
        self.assertIn("Content-Security-Policy-Report-Only", response.headers)
        self.assertNotIn("Content-Security-Policy", response.headers)

    def test_policy_has_no_unsafe_eval_and_no_inline_script_or_stylesheets(self):
        policy = directives(self.client.get("/").headers["Content-Security-Policy-Report-Only"])
        flat = " ".join(" ".join(v) for v in policy.values())
        self.assertNotIn("unsafe-eval", flat)
        self.assertEqual(policy["script-src"], ["'self'"])
        self.assertEqual(policy["style-src"], ["'self'"])
        self.assertNotIn("'unsafe-inline'", policy["default-src"] + policy["script-src"] + policy["style-src"])
        # the single, documented exception: inline style="..." attributes of the design system
        self.assertEqual(policy["style-src-attr"], ["'unsafe-inline'"])
        self.assertNotIn("unsafe-inline", " ".join(v for k, vals in policy.items() if k not in ("style-src-attr",) for v in vals))

    def test_policy_locks_down_plugins_framing_forms_and_base(self):
        policy = directives(self.client.get("/").headers["Content-Security-Policy-Report-Only"])
        self.assertEqual(policy["object-src"], ["'none'"])
        self.assertEqual(policy["frame-ancestors"], ["'none'"])
        self.assertEqual(policy["base-uri"], ["'self'"])
        self.assertEqual(policy["form-action"], ["'self'"])
        self.assertEqual(policy["report-uri"], ["/csp-report/"])

    def test_no_external_hosts_are_allowed(self):
        policy = self.client.get("/").headers["Content-Security-Policy-Report-Only"]
        self.assertIsNone(re.search(r"https?://", policy))
        self.assertIsNone(re.search(r"\*", policy))

    @override_settings(CSP_REPORT_ONLY=False)
    def test_enforcing_mode_switches_the_header(self):
        response = self.client.get("/")
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertNotIn("Content-Security-Policy-Report-Only", response.headers)

    def test_other_browser_protections(self):
        headers = self.client.get("/").headers
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "same-origin")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("geolocation=()", headers["Permissions-Policy"])

    def test_account_pages_are_never_cached(self):
        for url in (reverse("accounts:login"), reverse("accounts:password_reset"), reverse("portal:dashboard"), "/" + settings.ADMIN_URL):
            self.assertIn("no-store", self.client.get(url).headers.get("Cache-Control", ""), msg=url)
        self.assertNotIn("no-store", self.client.get("/").headers.get("Cache-Control", ""))

    def test_hsts_is_never_sent_over_plain_http(self):
        with override_settings(SECURE_HSTS_SECONDS=3600):
            self.assertNotIn("Strict-Transport-Security", Client().get("/").headers)

    def test_hsts_is_sent_over_https_only_when_enabled(self):
        with override_settings(SECURE_HSTS_SECONDS=3600):
            self.assertEqual(Client().get("/", secure=True).headers["Strict-Transport-Security"][:11], "max-age=360")
        with override_settings(SECURE_HSTS_SECONDS=0):
            self.assertNotIn("Strict-Transport-Security", Client().get("/", secure=True).headers)

    def test_default_configuration_has_hsts_off(self):
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_cookie_and_csrf_settings(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_state_changing_forms_enforce_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        for url in (reverse("accounts:login"), reverse("accounts:password_reset"), reverse("accounts:logout"), reverse("accounts:two_factor_verify")):
            self.assertEqual(strict.post(url, {}).status_code, 403, msg=url)


class CspReportEndpointTests(TestCase):
    def post(self, body, content_type="application/csp-report", **extra):
        return Client().post(REPORT, data=body if isinstance(body, (bytes, str)) else json.dumps(body), content_type=content_type, **extra)

    def sample(self, **overrides):
        report = {"document-uri": "http://testserver/accounts/login/?next=/portal/&token=SECRET", "effective-directive": "script-src-elem", "blocked-uri": "https://evil.example/x.js?k=SECRET#frag"}
        report.update(overrides)
        return {"csp-report": report}

    def test_accepts_a_report_and_logs_it_without_query_strings(self):
        with self.assertLogs("apps.core.views", level="WARNING") as logs:
            response = self.post(self.sample())
        self.assertEqual(response.status_code, 204)
        text = "\n".join(logs.output)
        self.assertIn("script-src-elem", text)
        self.assertIn("evil.example/x.js", text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("next=", text)

    def test_only_post_is_allowed(self):
        self.assertEqual(Client().get(REPORT).status_code, 405)

    def test_oversized_report_is_refused(self):
        self.assertEqual(self.post("x" * 9000).status_code, 413)

    def test_malformed_or_hostile_bodies_never_cause_errors(self):
        for body in ("not json", "[]", '{"csp-report": "str"}', '{"csp-report": {"blocked-uri": ' + '"a"' * 3 + "}}", "\x00\x01"):
            self.assertEqual(self.post(body).status_code, 204, msg=body)

    def test_no_cookie_or_csrf_token_is_needed(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(REPORT, data=json.dumps(self.sample()), content_type="application/csp-report").status_code, 204)

    @override_settings(THROTTLE_POLICIES={**settings.THROTTLE_POLICIES, "csp:ip": {"max": 3, "window": 3600, "lock": 3600}})
    def test_flooding_is_rate_limited_but_answers_stay_identical(self):
        with self.assertLogs("apps.core.views", level="WARNING") as logs:
            codes = [self.post(self.sample()).status_code for _ in range(8)]
        self.assertEqual(set(codes), {204})
        self.assertEqual(len(logs.output), 3)  # the rest were dropped silently

    def test_report_endpoint_changes_no_application_data(self):
        from apps.audit.models import AuditLog

        self.post(self.sample())
        self.assertEqual(AuditLog.objects.count(), 0)


class LogRedactionTests(SimpleTestCase):
    def test_reset_tokens_are_removed_from_paths(self):
        line = '"GET /accounts/reset/MQ/c1x2y3-abcdef0123456789/ HTTP/1.1" 200 1234'
        cleaned = redact(line)
        self.assertNotIn("c1x2y3-abcdef0123456789", cleaned)
        self.assertIn("/accounts/reset/MQ/[redacted]/", cleaned)

    def test_credential_like_pairs_are_removed(self):
        for text in ("login failed password=hunter2 for x", "token=abc123def", "secret=abc code=123456"):
            cleaned = redact(text)
            self.assertNotRegex(cleaned, r"hunter2|abc123def|=abc |123456")
            self.assertIn("[redacted]", cleaned)

    def test_ordinary_messages_are_untouched(self):
        for text in ("Not Found: /nope/", "GET / 200", "CSP report: directive=script-src blocked=x"):
            self.assertEqual(redact(text), text)

    def test_filter_rewrites_records_in_place(self):
        record = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"GET %s HTTP/1.1" %s', ("/accounts/reset/MQ/tok-ABCDEF/", 200), None)
        self.assertTrue(RedactSecretsFilter().filter(record))
        self.assertNotIn("tok-ABCDEF", record.getMessage())

    def test_filter_survives_malformed_log_calls(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "%s %s", ("only-one",), None)
        self.assertTrue(RedactSecretsFilter().filter(record))

    def test_console_handler_has_the_filter_configured(self):
        self.assertIn("redact", settings.LOGGING["handlers"]["console"]["filters"])


class ProductionSettingsTests(SimpleTestCase):
    """Starts real Django processes with production settings (nothing is deployed or served)."""

    GOOD = {
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "k3Jx9-Qw2Zr7_Lm5Vb8Nc1Td4Hy6Pf0Sg2Ua9Eo3Ri7Wt5Xq1Yz8Bv4Dn6Mc0Kj2",  # test-only, high variety
        "DJANGO_ALLOWED_HOSTS": "portal.example.test",
        "DJANGO_ADMIN_URL": "gate-0123456789abcdef/",  # production refuses the default admin path
        "OTP_ENCRYPTION_KEYS": ",".join(settings.OTP_ENCRYPTION_KEYS),  # the test-only key
        "EMAIL_HOST": "smtp.example.test",
        "DEFAULT_FROM_EMAIL": "no-reply@example.test",
    }

    def run_manage(self, *args, **env):
        merged = {**os.environ, **self.GOOD, **env}
        merged = {k: v for k, v in merged.items() if v is not None}
        return subprocess.run([sys.executable, "manage.py", *args], cwd=settings.BASE_DIR, env=merged, capture_output=True, text=True, timeout=60)

    def test_csp_is_enforced_by_default_in_production_and_report_only_only_when_asked(self):
        probe = "from django.conf import settings; print(settings.CSP_REPORT_ONLY)"
        default = self.run_manage("shell", "-c", probe)
        self.assertEqual((default.returncode, default.stdout.strip().splitlines()[-1]), (0, "False"), default.stderr[-300:])
        explicit = self.run_manage("shell", "-c", probe, DJANGO_CSP_REPORT_ONLY="1")
        self.assertEqual(explicit.stdout.strip().splitlines()[-1], "True")

    def test_refuses_a_short_secret_key(self):
        result = self.run_manage("check", DJANGO_SECRET_KEY="short")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_refuses_empty_allowed_hosts(self):
        result = self.run_manage("check", DJANGO_ALLOWED_HOSTS="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_refuses_to_start_without_an_otp_encryption_key(self):
        result = self.run_manage("check", OTP_ENCRYPTION_KEYS="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OTP_ENCRYPTION_KEYS", result.stderr)

    def test_refuses_to_start_without_explicit_smtp_settings(self):
        result = self.run_manage("check", EMAIL_HOST=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EMAIL_HOST", result.stderr)

    def test_deploy_check_reports_only_the_deliberately_deferred_hsts(self):
        result = self.run_manage("check", "--deploy")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        codes = set(re.findall(r"security\.W\d+", result.stdout + result.stderr))
        self.assertEqual(codes, {"security.W004"})  # HSTS is switched on only after HTTPS is verified

    def test_secure_defaults(self):
        result = self.run_manage(
            "shell", "-c",
            "from django.conf import settings as s; print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, "
            "s.SESSION_COOKIE_NAME, s.CSRF_COOKIE_NAME, s.SECURE_HSTS_SECONDS, s.CSP_REPORT_ONLY, s.EMAIL_BACKEND.rsplit('.', 2)[-2])",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("False True True True __Host-sessionid __Host-csrftoken 0 False smtp", result.stdout)


class ProductionAdminPathGuard(SimpleTestCase):
    """Day 25: the Django admin must not sit at the well-known /admin/ in production. A long, unguessable path is not a lock (the admin needs a superuser
    with a second factor anyway) but it removes the cheapest scanning target and the noise that goes with it."""

    BASE = {"DJANGO_SETTINGS_MODULE": "config.settings.production", "DJANGO_SECRET_KEY": "x" * 80, "DJANGO_ALLOWED_HOSTS": "a.test",
            "OTP_ENCRYPTION_KEYS": "Vd89ffgaIBKyfs3cTdxx0oY3ExI6vPux7GHTCBdWaTE=", "EMAIL_HOST": "smtp.test", "DEFAULT_FROM_EMAIL": "a@a.test",
            "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "DOCUMENT_SCAN_MODE": "clamav"}

    def start(self, **extra):
        import subprocess
        import sys
        from pathlib import Path
        env = {**os.environ, **self.BASE, **extra}
        env.pop("DJANGO_ADMIN_URL", None) if "DJANGO_ADMIN_URL" not in extra else None
        return subprocess.run([sys.executable, "-c", "import django; django.setup()"], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])

    def test_the_default_admin_path_is_refused_in_production(self):
        proc = self.start()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("DJANGO_ADMIN_URL", proc.stderr)

    def test_well_known_and_short_paths_are_refused(self):
        for bad in ("admin/", "/admin", "admin", "administrator/", "django-admin/", "secret/", "abc123/"):
            self.assertNotEqual(self.start(DJANGO_ADMIN_URL=bad).returncode, 0, bad)

    def test_a_long_unguessable_path_is_accepted(self):
        proc = self.start(DJANGO_ADMIN_URL="gate-7f3a9c1e5b2d4a60/")
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
