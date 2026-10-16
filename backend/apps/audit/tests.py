import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, ImmutableAuditError
from .services import record

User = get_user_model()
PASSWORD = "Namuna-Parol-12345"


class AuditSignalsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("carol", "carol@example.test", PASSWORD)

    def test_successful_login_is_recorded_with_ip(self):
        self.client.post(reverse("accounts:login"), {"username": "carol", "password": PASSWORD})
        entry = AuditLog.objects.get(action=AuditLog.Action.LOGIN)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.ip, "127.0.0.1")

    def test_failed_login_is_recorded_without_the_typed_identifier(self):
        typed = "hunter2-this-could-be-a-password"
        self.client.post(reverse("accounts:login"), {"username": typed, "password": "whatever-1234"})
        entry = AuditLog.objects.get(action=AuditLog.Action.LOGIN_FAILED)
        self.assertIsNone(entry.user)
        self.assertNotIn(typed, json.dumps(entry.meta))
        self.assertEqual(entry.meta["identifier_length"], len(typed))
        self.assertEqual(len(entry.meta["identifier_sha256_16"]), 16)

    def test_password_never_stored(self):
        self.client.post(reverse("accounts:login"), {"username": "carol", "password": "Wrong-pass-12345"})
        dump = json.dumps(list(AuditLog.objects.values("meta", "object_type", "object_id", "user_agent")), default=str)
        self.assertNotIn("Wrong-pass-12345", dump)


class AuditImmutabilityTests(TestCase):
    def setUp(self):
        self.entry = record(AuditLog.Action.LOGIN)

    def test_cannot_modify_saved_entry(self):
        self.entry.action = AuditLog.Action.LOGOUT
        with self.assertRaises(ImmutableAuditError):
            self.entry.save()

    def test_cannot_delete_entry(self):
        with self.assertRaises(ImmutableAuditError):
            self.entry.delete()

    def test_queryset_update_delete_blocked(self):
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.all().update(action="login")
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.all().delete()
        with self.assertRaises(ImmutableAuditError):
            AuditLog.objects.bulk_update([self.entry], ["action"])
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_deleting_a_user_keeps_entries_but_unlinks_them(self):
        user = User.objects.create_user("dave", "dave@example.test", PASSWORD)
        entry = record(AuditLog.Action.LOGIN, user=user)
        user.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.user)
