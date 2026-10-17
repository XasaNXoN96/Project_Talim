import json
import re
import threading
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog

from . import throttle
from .backends import EmailOrUsernameBackend
from .models import ThrottleState
from .testing import PASSWORD, frozen_throttle_clock, make_user

LOGIN = reverse("accounts:login")
WRONG = "Noto-g-ri-parol-0000"


def attempt(client, identifier="alice", password=PASSWORD, ip="10.0.0.1", **extra):
    return client.post(LOGIN, {"username": identifier, "password": password}, REMOTE_ADDR=ip, **extra)


def signed_in(client):
    return "_auth_user_id" in client.session


def error_text(response):
    match = re.search(r'class="alert err"[^>]*>.*?<span>(.*?)</span>', response.content.decode(), re.S)
    return match.group(1).strip() if match else None


class LoginLockoutTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")

    def test_locks_after_five_failures_even_for_the_correct_password(self):
        for _ in range(5):
            attempt(self.client, password=WRONG)
        response = attempt(self.client, password=PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(signed_in(self.client))

    def test_four_failures_do_not_lock_and_success_resets_the_counter(self):
        for _ in range(4):
            attempt(self.client, password=WRONG)
        self.assertEqual(attempt(self.client).status_code, 302)  # still allowed
        self.client.post(reverse("accounts:logout"))
        for _ in range(4):  # budget is fresh again: four more failures are fine
            attempt(self.client, password=WRONG)
        self.assertEqual(attempt(self.client).status_code, 302)

    def test_lock_lasts_15_minutes_then_expires(self):
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                attempt(self.client, password=WRONG)
            clock.advance(minutes=14, seconds=59)
            self.assertEqual(attempt(self.client).status_code, 200)  # still locked
            clock.advance(seconds=2)  # 15:01 after the last failure
            self.assertEqual(attempt(self.client).status_code, 302)
            self.assertTrue(signed_in(self.client))

    def test_blocked_attempts_do_not_extend_the_lock(self):
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                attempt(self.client, password=WRONG)
            clock.advance(minutes=10)
            for _ in range(3):
                attempt(self.client, password=WRONG)  # attacker keeps hammering during the lock
            clock.advance(minutes=5, seconds=1)  # 15:01 since the lock started
            self.assertEqual(attempt(self.client).status_code, 302)

    def test_fresh_budget_after_expiry(self):
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                attempt(self.client, password=WRONG)
            clock.advance(minutes=16)
            for _ in range(4):
                attempt(self.client, password=WRONG)
            self.assertEqual(attempt(self.client).status_code, 302)  # 4 failures: not locked yet

    def test_lock_is_never_permanent(self):
        with frozen_throttle_clock() as clock:
            for _ in range(3):  # three full lock cycles
                for _ in range(5):
                    attempt(self.client, password=WRONG)
                clock.advance(minutes=15, seconds=1)
                self.assertEqual(attempt(self.client).status_code, 302)
                self.client.post(reverse("accounts:logout"))

    def test_account_lock_cannot_be_bypassed_by_changing_ip(self):
        for i in range(5):
            attempt(self.client, password=WRONG, ip=f"10.0.1.{i}")
        self.assertEqual(attempt(self.client, ip="10.0.9.9").status_code, 200)
        self.assertFalse(signed_in(self.client))

    def test_other_accounts_are_not_affected(self):
        make_user("bob")
        for _ in range(5):
            attempt(self.client, password=WRONG)  # alice locked
        self.client.logout()
        self.assertEqual(attempt(self.client, "bob", ip="10.0.7.7").status_code, 302)

    def test_aliases_of_one_account_share_a_single_counter(self):
        for identifier in ["alice", "alice@example.test", "ALICE", "alice@example.test", "Alice@Example.Test"]:
            attempt(self.client, identifier, password=WRONG, ip="10.0.2.2")
        self.assertEqual(attempt(self.client, "alice", ip="10.0.2.3").status_code, 200)  # locked
        self.assertEqual(attempt(self.client, "alice@example.test", ip="10.0.2.4").status_code, 200)

    @override_settings(THROTTLE_POLICIES={**settings.THROTTLE_POLICIES, "login:ip": {"max": 6, "window": 900, "lock": 900}})
    def test_ip_limit_applies_across_different_accounts(self):
        make_user("bob")
        for i in range(6):
            attempt(self.client, f"nobody{i}", password=WRONG, ip="10.0.3.3")
        self.assertEqual(attempt(self.client, "bob", ip="10.0.3.3").status_code, 200)  # IP locked, bob is innocent
        self.client.logout()
        self.assertEqual(attempt(self.client, "bob", ip="10.0.3.4").status_code, 302)  # another address: fine

    @override_settings(THROTTLE_POLICIES={**settings.THROTTLE_POLICIES, "login:ip": {"max": 6, "window": 900, "lock": 900}})
    def test_forwarded_for_header_cannot_dodge_the_ip_limit(self):
        for i in range(6):
            attempt(self.client, f"nobody{i}", password=WRONG, ip="10.0.4.4", HTTP_X_FORWARDED_FOR=f"203.0.113.{i}")
        self.assertEqual(attempt(self.client, "alice", ip="10.0.4.4", HTTP_X_FORWARDED_FOR="198.51.100.77").status_code, 200)

    @override_settings(THROTTLE_POLICIES={**settings.THROTTLE_POLICIES, "login:ip": {"max": 6, "window": 900, "lock": 900}})
    def test_logging_into_own_account_does_not_reset_the_ip_counter(self):
        make_user("attacker")
        for i in range(5):
            attempt(self.client, f"victim{i}", password=WRONG, ip="10.0.5.5")
            attempt(self.client, "attacker", ip="10.0.5.5")  # legitimate success in between
            self.client.post(reverse("accounts:logout"))
        attempt(self.client, "victim-last", password=WRONG, ip="10.0.5.5")  # 6th failure
        self.assertEqual(attempt(self.client, "attacker", ip="10.0.5.5").status_code, 200)  # IP is now locked

    def test_success_refunds_the_ip_and_clears_account_counters(self):
        for _ in range(2):
            attempt(self.client, password=WRONG, ip="10.0.6.6")
        attempt(self.client, password=PASSWORD, ip="10.0.6.6")
        ip = ThrottleState.objects.get(kind="login:ip", key_hash=throttle.digest("login:ip", "10.0.6.6"))
        self.assertEqual(ip.failures, 2)  # the successful attempt was refunded, earlier failures remain
        for kind, value in (("login:identifier", "alice"), ("login:user", str(self.user.pk))):
            row = ThrottleState.objects.get(kind=kind, key_hash=throttle.digest(kind, value))
            self.assertEqual((row.failures, row.locked_until), (0, None))

    def test_a_legitimate_fifth_attempt_does_not_leave_a_lock_behind(self):
        for _ in range(4):
            attempt(self.client, password=WRONG, ip="10.0.8.8")
        self.assertEqual(attempt(self.client, password=PASSWORD, ip="10.0.8.8").status_code, 302)  # 5th attempt, correct
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(attempt(self.client, password=PASSWORD, ip="10.0.8.8").status_code, 302)

    def test_inactive_account_gets_the_same_neutral_answer(self):
        self.user.is_active = False
        self.user.save()
        response = attempt(self.client)
        self.assertEqual(response.status_code, 200)
        self.assertIn("noto‘g‘ri", error_text(response))


class NoEnumerationTests(TestCase):
    """Existing and non-existing logins must be indistinguishable at every stage."""

    def test_identical_responses_for_known_and_unknown_logins(self):
        make_user("alice")
        known, unknown = [], []
        for _ in range(8):  # crosses the lock threshold
            known.append(attempt(self.client, "alice", password=WRONG, ip="10.1.0.1"))
            unknown.append(attempt(self.client, "ghost", password=WRONG, ip="10.1.0.2"))
        self.assertEqual([r.status_code for r in known], [r.status_code for r in unknown])
        self.assertEqual({error_text(r) for r in known}, {error_text(r) for r in unknown})
        self.assertEqual(len({error_text(r) for r in known}), 1)  # one message for "wrong" and "blocked"

    def test_unknown_login_is_rate_limited_too(self):
        for _ in range(5):
            attempt(self.client, "ghost@example.test", password=WRONG)
        self.assertTrue(throttle.is_locked(throttle.Key("login:identifier", "ghost@example.test")))

    def test_message_mentions_both_possibilities(self):
        response = attempt(self.client, "ghost", password=WRONG)
        text = error_text(response)
        self.assertIn("noto‘g‘ri", text)
        self.assertIn("urinishlar", text)


class LockoutAuditTests(TestCase):
    def setUp(self):
        make_user("alice")

    def test_lock_and_blocked_attempts_are_audited_without_secrets(self):
        secret_password = "Super-Secret-Pass-9"
        for _ in range(5):
            attempt(self.client, "alice", password=secret_password)
        for _ in range(3):
            attempt(self.client, "alice", password=secret_password)  # while locked
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_LOCKED).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_BLOCKED).count(), 1)  # rate limited: once a minute
        dump = json.dumps(list(AuditLog.objects.values("action", "meta", "object_type", "object_id", "user_agent")), default=str)
        self.assertNotIn(secret_password, dump)

    def test_typed_identifier_is_stored_only_as_a_hash(self):
        typed = "could-be-a-password-123"
        for _ in range(5):
            attempt(self.client, typed, password=WRONG)
        dump = json.dumps(list(AuditLog.objects.values("meta")), default=str)
        self.assertNotIn(typed, dump)
        locked = AuditLog.objects.get(action=AuditLog.Action.LOGIN_LOCKED)
        self.assertEqual(len(locked.meta["identifier_sha256_16"]), 16)
        self.assertEqual(locked.ip, "10.0.0.1")

    def test_blocked_audit_entry_is_written_again_after_a_minute(self):
        with frozen_throttle_clock() as clock:
            for _ in range(5):
                attempt(self.client, password=WRONG)
            attempt(self.client)
            clock.advance(seconds=61)
            attempt(self.client)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_BLOCKED).count(), 2)


class ThrottleServiceTests(TestCase):
    def test_hashes_do_not_contain_the_raw_value(self):
        throttle.reserve([throttle.Key("login:identifier", "visible-name")])
        row = ThrottleState.objects.get()
        self.assertNotIn("visible-name", row.key_hash)
        self.assertEqual(len(row.key_hash), 64)

    def test_same_value_in_different_kinds_does_not_collide(self):
        self.assertNotEqual(throttle.digest("login:ip", "x"), throttle.digest("otp:ip", "x"))

    def test_purge_removes_stale_rows_but_keeps_active_ones(self):
        now = throttle._now()
        make = lambda name, **kw: ThrottleState.objects.create(kind="login:identifier", key_hash=name * 64, **kw)
        make("a", failures=0, last_failure_at=None)  # cleared by a successful login
        make("b", failures=2, last_failure_at=now - timedelta(hours=2))  # old, no lock
        make("c", failures=5, last_failure_at=now - timedelta(minutes=1), locked_until=now + timedelta(minutes=14))  # locked
        make("d", failures=2, last_failure_at=now - timedelta(minutes=5))  # inside its window
        make("e", failures=5, last_failure_at=now - timedelta(hours=3), locked_until=now - timedelta(hours=2))  # lock long over
        self.assertEqual(throttle.purge_expired(), 3)
        self.assertEqual(set(ThrottleState.objects.values_list("key_hash", flat=True)), {"c" * 64, "d" * 64})

    def test_purge_command_runs(self):
        out = StringIO()
        call_command("purge_throttles", stdout=out)
        self.assertIn("deleted", out.getvalue())


class ConcurrencyTests(TransactionTestCase):
    """Real threads against real PostgreSQL: parallel attempts must not slip extra guesses past the limit."""

    def test_reserve_is_race_free(self):
        results, errors = [], []
        barrier = threading.Barrier(20)

        def worker():
            try:
                barrier.wait()
                results.append(throttle.reserve([throttle.Key("login:identifier", "racer")]).allowed)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sum(results), 5)  # exactly the budget; the other 15 were refused
        row = ThrottleState.objects.get(kind="login:identifier", key_hash=throttle.digest("login:identifier", "racer"))
        self.assertEqual(row.failures, 5)
        self.assertIsNotNone(row.locked_until)

    def test_parallel_login_requests_cannot_exceed_the_password_check_budget(self):
        from django.test import Client

        make_user("alice")
        original = EmailOrUsernameBackend.authenticate
        checks, lock, errors = [], threading.Lock(), []

        def counting(backend, *args, **kwargs):
            with lock:
                checks.append(1)
            return original(backend, *args, **kwargs)

        barrier = threading.Barrier(15)

        def worker(i):
            try:
                client = Client()
                barrier.wait()
                attempt(client, "alice", password=WRONG, ip=f"10.9.0.{i}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connections.close_all()

        with mock.patch.object(EmailOrUsernameBackend, "authenticate", counting):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertLessEqual(len(checks), 5)  # at most 5 verifications reached the password check
        self.assertTrue(throttle.is_locked(throttle.Key("login:identifier", "alice")))
        self.assertFalse(signed_in(self.client) or attempt(self.client, "alice", ip="10.9.9.9").status_code == 302)
