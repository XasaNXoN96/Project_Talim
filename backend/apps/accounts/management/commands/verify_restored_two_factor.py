import os
import re

import pyotp
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import CommandError

from apps.accounts import otp
from apps.accounts.models import TotpDevice
from apps.core.jobs import TrackedCommand


class Command(TrackedCommand):
    help = (
        "Part of the restore check: against a RESTORED COPY (never the live database), prove that the two-factor secrets can still be used "
        "with the OTP_ENCRYPTION_KEYS configured for this run: every confirmed authenticator device must decrypt, and the current code "
        "computed from it must be accepted by the real verification routine. Prints counts only (never a secret, a key or a code). "
        "A wrong or missing key fails the check: that is exactly the situation after a restore without the right key. "
        "Refuses to run unless RESTORE_CHECK=1 and the database name says restore/scratch/check."
    )
    job_name = "verify_document_files"  # lock/record are not used (see --no-record); the name only picks a lock id for the base class

    def handle(self, *args, **options):
        name = settings.DATABASES["default"]["NAME"]
        if os.environ.get("RESTORE_CHECK") != "1" or not re.search(r"restore|scratch|check", name):
            raise CommandError("refusing: this command is only for a scratch copy made by restore_check.sh (RESTORE_CHECK=1).")
        options["no_record"] = True
        super().handle(*args, **options)

    def run_job(self, run, *args, **options):
        devices = list(TotpDevice.objects.exclude(confirmed_at__isnull=True))
        decryptable = accepted = 0
        for device in devices:
            run.processed += 1
            try:
                secret = otp.decrypt_secret(device.secret_encrypted)
            except ImproperlyConfigured:
                run.errors += 1
                continue
            decryptable += 1
            if otp.verify_totp(device, pyotp.TOTP(secret).now()):
                accepted += 1
            else:
                run.errors += 1
        self.stdout.write(f"two_factor_check devices={len(devices)} decryptable={decryptable} accepted={accepted} failed={run.errors}")
