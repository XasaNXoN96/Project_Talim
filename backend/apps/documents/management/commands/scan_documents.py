from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.jobs import TrackedCommand
from apps.audit.services import record
from apps.documents import scanner
from apps.documents.models import DocumentVersion
from apps.tasks.models import TaskAttachment


class Command(TrackedCommand):
    help = (
        "Scan stored document versions that were never scanned (uploaded while the scanner was off) or, with --all, every "
        "version again (e.g. after a signature update). A version found infected is marked 'infected' and is never served. "
        "Fails closed: if the scanner cannot answer, nothing is changed and the command exits with an error."
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--all", action="store_true", help="re-scan versions already marked clean as well")

    job_name = "scan_documents"

    def run_job(self, run, *args, **options):
        if scanner.mode() == "disabled":
            raise CommandError("DOCUMENT_SCAN_MODE=disabled: nothing to do.")
        counts = {"clean": 0, "infected": 0, "missing": 0}
        for model in (DocumentVersion, TaskAttachment):
            self._scan(model, options["all"], counts, run)
        run.errors += counts["missing"]  # a stored file that cannot be read is a problem to be told about (exit code 1)
        self.stdout.write(f"clean={counts['clean']} infected={counts['infected']} missing_files={counts['missing']}")

    def _scan(self, model, rescan_all, counts, run):
        qs = model.objects.exclude(scan_status="infected")
        if not rescan_all:
            qs = qs.filter(scan_status="not_scanned")
        for version in qs.iterator():
            try:
                with version.file.storage.open(version.file.name, "rb") as fh:
                    data = fh.read()
            except (FileNotFoundError, OSError):
                counts["missing"] += 1
                continue
            try:
                result = scanner.scan_bytes(data)
            except scanner.ScanFailed as exc:
                raise CommandError(f"Scanner failure ({exc.code}); stopped. Counts so far: {counts}") from exc
            run.processed += 1
            version.scan_engine = result.engine
            if hasattr(version, "scanned_at"):
                version.scanned_at = timezone.now()
            if result.clean:
                version.scan_status = "clean"
                counts["clean"] += 1
            else:
                version.scan_status = "infected"
                counts["infected"] += 1
                record(AuditLog.Action.FILE_THREAT_DETECTED, object_type=model.__name__, object_id=version.pk, meta={"signature": result.signature, "source": "rescan"})
            fields = ["scan_status", "scan_engine"] + (["scanned_at"] if hasattr(version, "scanned_at") else [])
            version.save(update_fields=fields)
