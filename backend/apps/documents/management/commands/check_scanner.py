from django.conf import settings
from django.core.management.base import CommandError

from apps.core.jobs import TrackedCommand

from apps.documents import scanner


class Command(TrackedCommand):
    help = "Check that the antivirus daemon answers (exit code 1 otherwise). Use it from monitoring or after maintenance."

    job_name = "check_scanner"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--eicar", action="store_true", help="also require the daemon to DETECT the standard EICAR test string "
                            "(proves a usable signature database is loaded; run it after install and after every freshclam problem)")

    def run_job(self, run, *args, **options):
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
        if options.get("eicar"):
            # the standard, harmless EICAR antivirus test string, assembled at run time so that this file is not itself flagged
            eicar = (b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" + b"!$H+H*")
            try:
                verdict = scanner.scan_bytes(eicar)
            except scanner.ScanFailed as exc:
                raise CommandError(f"the EICAR scan failed ({exc.code}).") from exc
            if verdict.clean:
                raise CommandError("clamd did NOT detect the standard EICAR test string: no usable signature database is loaded "
                                   "(run freshclam, restart clamd). Uploads must not be accepted on this server.")
            self.stdout.write("clamd OK (PING, a clean scan, and the EICAR test string was DETECTED)")
            run.processed = 1
            return
        run.processed = 1
        self.stdout.write("clamd OK (PING and a test scan succeeded)")
