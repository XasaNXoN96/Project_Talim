from django.db import transaction
from django.db.models import Max

from .models import Document, DocumentVersion
from django.utils import timezone

from .files import check_or_audit, store_file  # noqa: F401  (check_or_audit is re-exported for the views)
from .validation import CheckedUpload


def add_version(document: Document, checked: CheckedUpload, *, actor, comment="") -> DocumentVersion:
    with transaction.atomic():
        Document.objects.select_for_update().get(pk=document.pk)  # serialise concurrent uploads: unique version numbers
        number = (document.versions.aggregate(m=Max("number"))["m"] or 0) + 1
        version = DocumentVersion(
            document=document, number=number, original_name=checked.display_name, extension=checked.extension, size=checked.size,
            comment=comment[:200], uploaded_by=actor, scan_status=checked.scan_status, scan_engine=checked.scan_engine,
            scanned_at=timezone.now() if checked.scan_status == "clean" else None,
        )
        version.sha256 = store_file(version.file, checked)
        version.save()
    return version
