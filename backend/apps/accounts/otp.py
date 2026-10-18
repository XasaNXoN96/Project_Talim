"""TOTP secrets, verification and backup codes.

* Secrets are encrypted with Fernet (keys from settings.OTP_ENCRYPTION_KEYS, newest first; older keys still decrypt,
  which allows key rotation). A database leak alone does not reveal the secrets.
* Codes are accepted for the current 30-second step and one step either side; each step can be used only once
  (``last_used_counter``), which blocks replay of a captured code.
* Backup codes are random, shown once, and stored only as password hashes (Argon2 in production).
"""
import hmac
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import BackupCode, TotpDevice

STEP = 30
BACKUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
BACKUP_CODE_LENGTH = 10
BACKUP_CODE_COUNT = 10


def _time() -> float:
    """Single clock for TOTP (patched in tests)."""
    return time.time()


def _fernet() -> MultiFernet:
    keys = settings.OTP_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured("OTP_ENCRYPTION_KEYS is not configured (see backend/.env.example).")
    return MultiFernet([Fernet(k.encode() if isinstance(k, str) else k) for k in keys])


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured("TOTP secret cannot be decrypted with the configured keys.") from exc


def normalise_totp_code(value: str) -> str | None:
    digits = "".join(str(value).split())
    return digits if len(digits) == 6 and digits.isdigit() else None


def get_or_create_pending_device(user) -> TotpDevice:
    """An unconfirmed device holds the new secret (encrypted) while the user scans the QR code."""
    device = TotpDevice.objects.filter(user=user).first()
    if device and device.confirmed_at:
        return device
    if device:
        try:
            decrypt_secret(device.secret_encrypted)
            return device
        except ImproperlyConfigured:
            # An UNCONFIRMED secret that the configured keys cannot open (key lost or changed during an unfinished enrolment): nothing depends on it,
            # so start again with a fresh one. A CONFIRMED device is never touched here (it is returned above); only an administrator drops it (reset_2fa).
            device.delete()
    return TotpDevice.objects.create(user=user, secret_encrypted=encrypt_secret(pyotp.random_base32()))


def regenerate_pending_secret(user) -> TotpDevice:
    TotpDevice.objects.filter(user=user, confirmed_at__isnull=True).delete()
    return get_or_create_pending_device(user)


def provisioning_uri(device: TotpDevice) -> str:
    return pyotp.TOTP(decrypt_secret(device.secret_encrypted)).provisioning_uri(
        name=device.user.get_username(), issuer_name=settings.TWO_FACTOR_ISSUER
    )


def verify_totp(device: TotpDevice, code: str) -> bool:
    """Constant-time check over the allowed window, with replay protection. Returns True at most once per step."""
    normalised = normalise_totp_code(code)
    if normalised is None:
        return False
    totp = pyotp.TOTP(decrypt_secret(device.secret_encrypted))
    current = int(_time()) // STEP
    matched = None
    for counter in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.at(counter * STEP), normalised):
            matched = counter
    if matched is None:
        return False
    # Atomic compare-and-set: of two parallel submissions of the same code only one can win.
    updated = (
        TotpDevice.objects.filter(pk=device.pk)
        .filter(Q(last_used_counter__isnull=True) | Q(last_used_counter__lt=matched))
        .update(last_used_counter=matched)
    )
    return updated == 1


def confirm_device(device: TotpDevice) -> None:
    TotpDevice.objects.filter(pk=device.pk, confirmed_at__isnull=True).update(confirmed_at=timezone.now())


def _normalise_backup(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def generate_backup_codes(user) -> list:
    """Replace all backup codes with a fresh set. Returns the plaintext codes — the only time they exist."""
    plain, rows = [], []
    for _ in range(BACKUP_CODE_COUNT):
        raw = "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(BACKUP_CODE_LENGTH))
        plain.append(f"{raw[:5]}-{raw[5:]}")
        rows.append(BackupCode(user=user, code_hash=make_password(raw)))
    with transaction.atomic():
        BackupCode.objects.filter(user=user).delete()
        BackupCode.objects.bulk_create(rows)
    return plain


def verify_backup_code(user, value: str) -> bool:
    """One-time use. Every unused hash is checked so timing does not reveal which one matched."""
    candidate = _normalise_backup(value)
    if len(candidate) != BACKUP_CODE_LENGTH:
        return False
    matched = None
    for code in BackupCode.objects.filter(user=user, used_at__isnull=True):
        if check_password(candidate, code.code_hash) and matched is None:
            matched = code
    if matched is None:
        return False
    return BackupCode.objects.filter(pk=matched.pk, used_at__isnull=True).update(used_at=timezone.now()) == 1


def remaining_backup_codes(user) -> int:
    return BackupCode.objects.filter(user=user, used_at__isnull=True).count()
