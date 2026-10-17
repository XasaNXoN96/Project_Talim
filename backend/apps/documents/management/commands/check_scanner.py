from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.documents import scanner


class Command(BaseCommand):
    help = "Check that the antivirus daemon answers (exit code 1 otherwise). Use it from monitoring or after maintenance."

    def handle(self, *args, **options):
        if scanner.mode() == "disabled":
            raise CommandError("DOCUMENT_SCAN_MODE=disabled: uploads are NOT scanned (allowed in development only).")
        if not scanner.ping():
            where = settings.CLAMAV_SOCKET or f"{settings.CLAMAV_HOST}:{settings.CLAMAV_PORT}"
            raise CommandError(f"clamd does not answer at {where}: uploads are being refused (fail-closed).")
        try:
            result = scanner.scan_bytes(b"clean test content")
        except scanner.ScanFailed as exc:
            raise CommandError(f"clamd answers PING but a scan failed ({exc.code}).") from exc
        if not result.clean:
            raise CommandError("A harmless test string was reported as a threat: check the signature databases.")
        self.stdout.write("clamd OK (PING and a test scan succeeded)")
