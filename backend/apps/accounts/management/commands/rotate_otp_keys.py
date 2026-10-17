import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import TotpDevice
from apps.accounts.otp import _fernet

logger = logging.getLogger("apps.jobs")


class Command(BaseCommand):
    help = (
        "Re-encrypt every stored two-factor secret with the FIRST (newest) key of OTP_ENCRYPTION_KEYS, so that older keys can then be removed. "
        "Procedure (docs/DEPLOYMENT_READINESS.md, key management): 1) put the new key FIRST and keep the old ones in the list; 2) back up the new key; "
        "3) run this command (use --dry-run first); 4) only when it reports 0 not-yet-rotated and 0 failed, remove the old key. "
        "Secrets already under the newest key are left alone, a secret that no listed key opens is counted as failed and left unchanged (exit code 1). "
        "Prints counts only: never a key, a secret or a user name. Manual operation, not scheduled."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="count only; change nothing")

    def handle(self, *args, **options):
        keys = settings.OTP_ENCRYPTION_KEYS
        if not keys:
            raise CommandError("OTP_ENCRYPTION_KEYS is not configured.")
        newest = Fernet(keys[0].encode() if isinstance(keys[0], str) else keys[0])
        multi = _fernet()
        total = already = rotated = failed = 0
        for device in TotpDevice.objects.all().iterator():
            total += 1
            token = device.secret_encrypted.encode()
            try:
                newest.decrypt(token)
                already += 1
                continue
            except InvalidToken:
                pass
            try:
                new_token = multi.rotate(token).decode()
            except InvalidToken:
                failed += 1
                logger.error("two-factor secret %s cannot be opened by any configured key", device.pk)
                continue
            rotated += 1
            if not options["dry_run"]:
                with transaction.atomic():
                    TotpDevice.objects.filter(pk=device.pk).update(secret_encrypted=new_token)
        verb = "would rotate" if options["dry_run"] else "rotated"
        self.stdout.write(f"devices={total} already_on_newest_key={already} {verb}={rotated} failed={failed}")
        if failed:
            raise CommandError(f"{failed} secret(s) cannot be opened by any configured key; nothing was changed for them.")
