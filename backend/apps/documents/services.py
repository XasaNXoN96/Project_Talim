import hashlib

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max

from apps.audit.models import AuditLog
from apps.audit.services import record

from .models import Document, DocumentVersion
from .storage import new_storage_name
from .validation import CheckedUpload, UploadRejected, validate_upload


def check_or_audit(uploaded, *, request, user):
    """Validate; on rejection write an audit entry that carries only the machine reason code (no file name, no content)."""
    try:
        return validate_upload(uploaded)
    except UploadRejected as exc:
        record(AuditLog.Action.DOCUMENT_UPLOAD_REJECTED, request=request, user=user, object_type="Document", meta={"reason": exc.code})
        raise


def add_version(document: Document, checked: CheckedUpload, *, actor, comment="") -> DocumentVersion:
    with transaction.atomic():
        Document.objects.select_for_update().get(pk=document.pk)  # serialise concurrent uploads: unique version numbers
        number = (document.versions.aggregate(m=Max("number"))["m"] or 0) + 1
        version = DocumentVersion(
            document=document, number=number, original_name=checked.display_name, extension=checked.extension, size=checked.size,
            sha256=hashlib.sha256(checked.data).hexdigest(), comment=comment[:200], uploaded_by=actor,
        )
        version.file.save(new_storage_name(checked.extension), ContentFile(checked.data), save=False)
        version.save()
    return version
