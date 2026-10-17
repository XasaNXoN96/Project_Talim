import hashlib

from apps.core.jobs import TrackedCommand

from apps.documents.models import DocumentVersion
from apps.tasks.models import TaskAttachment


class Command(TrackedCommand):
    help = (
        "Integrity check of the private document store: every version row must have its file, with the recorded size "
        "and SHA-256. Use it after a restore (see docs/BACKUP_AND_RESTORE.md). Exit code 1 on any problem."
    )

    job_name = "verify_document_files"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--report-orphans", action="store_true", help="also count stored files that no row refers to (informational: never an error)")

    @staticmethod
    def count_orphans(rows):
        import os

        from django.conf import settings

        known = {r.file.name for r in rows}
        root = str(settings.PRIVATE_MEDIA_ROOT)
        orphans = 0
        for base, _dirs, names in os.walk(root):
            for n in names:
                rel = os.path.relpath(os.path.join(base, n), root)
                if rel not in known and not n.startswith("."):
                    orphans += 1
        return orphans

    def run_job(self, run, *args, **options):
        total = missing = bad = 0
        rows = [*DocumentVersion.objects.iterator(), *TaskAttachment.objects.iterator()]  # removed attachments keep their files
        for v in rows:
            total += 1
            try:
                with v.file.storage.open(v.file.name, "rb") as fh:
                    data = fh.read()
            except (FileNotFoundError, OSError):
                missing += 1
                self.stderr.write(f"MISSING file for version {v.pk}")
                continue
            if len(data) != v.size or hashlib.sha256(data).hexdigest() != v.sha256:
                bad += 1
                self.stderr.write(f"MISMATCH size/sha256 for version {v.pk}")
        run.processed, run.errors = total, missing + bad
        extra = f" orphans={self.count_orphans(rows)}" if options.get("report_orphans") else ""
        self.stdout.write(f"versions={total} missing={missing} mismatched={bad}{extra}")
