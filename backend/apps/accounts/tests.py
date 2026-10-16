import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog

User = get_user_model()
PASSWORD = "Namuna-Parol-12345"  # fictional test password


def make_user(username="alice", email="alice@example.test", password=PASSWORD, **extra):
    return User.objects.create_user(username=username, email=email, password=password, **extra)


class UserModelTests(TestCase):
    def test_primary_key_is_uuid(self):
        self.assertIsInstance(make_user().pk, uuid.UUID)

    def test_email_is_normalised_to_lowercase(self):
        self.assertEqual(make_user(email="  Alice@Example.TEST ").email, "alice@example.test")

    def test_email_unique_case_insensitive(self):
        make_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user(username="other", email="ALICE@example.test")

    def test_username_unique_case_insensitive(self):
        make_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user(username="ALICE", email="other@example.test")

    def test_new_users_have_no_privileges(self):
        user = make_user()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.get_all_permissions(), set())
        self.assertFalse(user.groups.exists())

    def test_password_is_hashed_not_plain(self):
        user = make_user()
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.check_password(PASSWORD))

    def test_argon2_is_primary_hasher_in_real_settings(self):
        from config.settings import base

        self.assertTrue(base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher"))

    @override_settings(
        PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.Argon2PasswordHasher",
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        ]
    )
    def test_argon2_hasher_works(self):
        user = make_user()
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertTrue(user.check_password(PASSWORD))


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.url = reverse("accounts:login")

    def login(self, identifier="alice", password=PASSWORD, **extra):
        return self.client.post(self.url, {"username": identifier, "password": password, **extra})

    def test_login_page_renders_real_form_with_csrf(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, 'id="signin-form"')
        self.assertNotContains(response, 'id="loginForm"')  # static demo's fake-login hook must not apply here

    def test_login_with_username(self):
        response = self.login("alice")
        self.assertRedirects(response, reverse("portal:dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_login_with_email_case_insensitive(self):
        self.assertEqual(self.login("ALICE@Example.Test").status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_rejected(self):
        response = self.login(password="Noto-g-ri-parol-1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login yoki parol noto‘g‘ri")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_does_not_accept_any_password(self):
        for password in ["x", "password", "1", PASSWORD + "x", PASSWORD.lower(), " " + PASSWORD]:
            self.client.logout()
            self.login(password=password)
            self.assertNotIn("_auth_user_id", self.client.session, msg=password)

    def test_unknown_user_gets_same_error(self):
        response = self.login("nobody", PASSWORD)
        self.assertContains(response, "Login yoki parol noto‘g‘ri")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        self.login()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_empty_fields_show_errors(self):
        response = self.client.post(self.url, {"username": "", "password": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_requires_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(self.url, {"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", strict.session)

    def test_without_remember_me_session_ends_with_browser(self):
        self.login()
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_uses_configured_lifetime(self):
        from django.conf import settings

        self.login(remember_me="on")
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)

    def test_open_redirect_is_blocked(self):
        response = self.client.post(self.url + "?next=https://evil.test/", {"username": "alice", "password": PASSWORD, "next": "https://evil.test/"})
        self.assertRedirects(response, reverse("portal:dashboard"), fetch_redirect_response=False)

    def test_safe_next_is_followed(self):
        response = self.client.post(self.url, {"username": "alice", "password": PASSWORD, "next": reverse("portal:dashboard")})
        self.assertEqual(response["Location"], reverse("portal:dashboard"))

    def test_signed_in_user_is_redirected_away_from_login(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 302)


class LogoutTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_ends_session(self):
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("content:home"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("portal:dashboard")).status_code, 302)

    def test_logout_is_audited(self):
        self.client.post(reverse("accounts:logout"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGOUT, user=self.user).exists())
