"""Rate limiting / temporary lockout backed by PostgreSQL (works across processes and servers).

Design
------
* Every limited action has a *kind* with a policy (max attempts, window, lock duration) in settings.THROTTLE_POLICIES.
* A key identifies who is limited (identifier, user id, IP, e-mail). Only an HMAC of it is stored.
* ``reserve()`` is called BEFORE the secret is verified. Under row locks it either reports "blocked" or counts the
  attempt and, when the threshold is reached, starts a temporary lock. Because counting happens before verification,
  parallel requests cannot slip extra guesses through: at most ``max_failures`` verifications happen per lock cycle.
* While a key is locked nothing is counted and the lock is NOT extended, so no account is ever locked permanently.
* On success ``succeed()`` clears account-level keys; IP keys only get this attempt refunded (so logging in to an
  attacker's own account cannot reset the IP counter).
* Callers must show the same neutral message for "wrong secret" and "blocked", so lock state never reveals whether a
  login or e-mail exists.
"""
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import ThrottleState

BLOCKED_LOG_INTERVAL = timedelta(seconds=60)  # at most one "blocked attempt" audit entry per key per minute


def _now():
    """Single time source (patched in tests)."""
    return timezone.now()


@dataclass(frozen=True)
class Policy:
    max_failures: int
    window: timedelta
    lock: timedelta


def get_policy(kind: str) -> Policy:
    cfg = settings.THROTTLE_POLICIES[kind]
    return Policy(int(cfg["max"]), timedelta(seconds=int(cfg["window"])), timedelta(seconds=int(cfg["lock"])))


@dataclass(frozen=True)
class Key:
    kind: str
    value: str
    on_success: str = "clear"  # "clear": reset counter; "refund": give back this attempt only; "keep": do nothing


def digest(kind: str, value: str) -> str:
    """HMAC-SHA256 keyed with SECRET_KEY; kind-separated so equal values in different kinds never collide."""
    return hmac.new(settings.SECRET_KEY.encode(), f"{kind}\x00{value}".encode(), hashlib.sha256).hexdigest()


@dataclass
class Reservation:
    allowed: bool
    blocked_kinds: list = field(default_factory=list)
    newly_locked: list = field(default_factory=list)
    audit_blocked: bool = False  # True when a "blocked attempt" audit entry should be written now


def reserve(keys: list) -> Reservation:
    """Atomically count one attempt against all keys, or report that one of them is locked."""
    unique = {(k.kind, digest(k.kind, k.value)): k for k in keys}
    now = _now()
    with transaction.atomic():
        rows = {}
        for kind, key_hash in sorted(unique):  # fixed order => no deadlocks between concurrent requests
            row, _ = ThrottleState.objects.select_for_update().get_or_create(kind=kind, key_hash=key_hash)
            rows[(kind, key_hash)] = row

        blocked = [kind for (kind, _), row in rows.items() if row.locked_until and row.locked_until > now]
        if blocked:
            audit = False
            for (kind, _), row in rows.items():
                if kind in blocked and (row.last_blocked_log_at is None or now - row.last_blocked_log_at >= BLOCKED_LOG_INTERVAL):
                    row.last_blocked_log_at = now
                    row.save(update_fields=["last_blocked_log_at"])
                    audit = True
            return Reservation(False, blocked_kinds=sorted(set(blocked)), audit_blocked=audit)

        newly_locked = []
        for (kind, _), row in rows.items():
            policy = get_policy(kind)
            if row.last_failure_at is None or now - row.last_failure_at >= policy.window:
                row.failures = 0  # window elapsed (this also resets after a finished lock)
                row.locked_until = None
            row.failures += 1
            row.last_failure_at = now
            if row.failures >= policy.max_failures:
                row.locked_until = now + policy.lock
                newly_locked.append(kind)
            row.save(update_fields=["failures", "last_failure_at", "locked_until"])
        return Reservation(True, newly_locked=sorted(newly_locked))


def succeed(keys: list, reservation: Reservation) -> None:
    """The guarded secret was correct: reset account keys, refund IP keys."""
    with transaction.atomic():
        for key in keys:
            qs = ThrottleState.objects.filter(kind=key.kind, key_hash=digest(key.kind, key.value))
            if key.on_success == "clear":
                qs.update(failures=0, locked_until=None, last_failure_at=None)
            elif key.on_success == "refund":
                qs.update(failures=Greatest(F("failures") - 1, Value(0)))
                if key.kind in reservation.newly_locked:
                    qs.update(locked_until=None)  # this very attempt triggered the lock but it was legitimate


def clear(keys: list) -> None:
    with transaction.atomic():
        for key in keys:
            ThrottleState.objects.filter(kind=key.kind, key_hash=digest(key.kind, key.value)).update(
                failures=0, locked_until=None, last_failure_at=None
            )


def is_locked(key: Key) -> bool:
    row = ThrottleState.objects.filter(kind=key.kind, key_hash=digest(key.kind, key.value)).first()
    return bool(row and row.locked_until and row.locked_until > _now())


def purge_expired() -> int:
    """Delete rows that can no longer affect anything (lock over and window long gone)."""
    now = _now()
    longest = max(get_policy(kind).window for kind in settings.THROTTLE_POLICIES)
    stale = ThrottleState.objects.filter(
        Q(last_failure_at__isnull=True) | Q(last_failure_at__lt=now - 2 * longest)
    ).exclude(locked_until__gt=now)
    count, _ = stale.delete()
    return count
