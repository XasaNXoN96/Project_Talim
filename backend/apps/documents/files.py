"""The ONE path every uploaded file takes (documents and task attachments): validate -> antivirus -> store -> serve.
Do not add a second path: security fixes belong here."""
import hashlib
import logging

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record

from . import scanner
from .storage import new_storage_name
from .validation import CheckedUpload, UploadRejected, validate_upload

logger = logging.getLogger(__name__)

SCAN_MESSAGES = {
    "scan_unavailable": _("Fayllarni tekshirish xizmati hozir ishlamayapti. Fayl qabul qilinmadi; keyinroq qayta urinib ko‘ring."),
    "scan_timeout": _("Faylni tekshirish juda uzoq davom etdi. Fayl qabul qilinmadi; keyinroq qayta urinib ko‘ring."),
    "scan_error": _("Faylni tekshirib bo‘lmadi. Fayl qabul qilinmadi."),
}


def screen_upload(uploaded) -> CheckedUpload:
    """Validate, then scan. Raises UploadRejected (code: a validation code, 'malware', or a scan_* failure code).
    The returned upload carries the scan verdict. A file is never accepted when the verdict could not be obtained."""
    checked = validate_upload(uploaded)
    from dataclasses import replace

    if scanner.mode() == "disabled":
        return replace(checked, scan_status="not_scanned", scan_engine="")
    try:
        result = scanner.scan_bytes(checked.data)
    except scanner.ScanFailed as exc:
        raise UploadRejected(exc.code, SCAN_MESSAGES.get(exc.code, SCAN_MESSAGES["scan_error"])) from exc
    if not result.clean:
        exc = UploadRejected("malware", _("Faylda zararli dastur aniqlandi. Fayl qabul qilinmadi."))
        exc.signature = result.signature
        raise exc
    return replace(checked, scan_status="clean", scan_engine=result.engine)


def check_or_audit(uploaded, *, request, user, object_type="Document", object_id=""):
    """screen_upload + audit on refusal. The audit entry holds only the reason code (and the signature name for a threat):
    never the file name or content."""
    try:
        return screen_upload(uploaded)
    except UploadRejected as exc:
        if exc.code == "malware":
            record(AuditLog.Action.FILE_THREAT_DETECTED, request=request, user=user, object_type=object_type, object_id=object_id,
                   meta={"signature": getattr(exc, "signature", "")})
        record(AuditLog.Action.DOCUMENT_UPLOAD_REJECTED, request=request, user=user, object_type=object_type, object_id=object_id, meta={"reason": exc.code})
        raise


def store_file(field_file, checked: CheckedUpload) -> str:
    """Write the bytes under a random name in the private storage; returns the sha256."""
    field_file.save(new_storage_name(checked.extension), ContentFile(checked.data), save=False)
    return hashlib.sha256(checked.data).hexdigest()


def download_response(field_file, *, filename: str):
    """Attachment-only response with a neutral content type. Call it AFTER the permission check."""
    try:
        handle = field_file.storage.open(field_file.name, "rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    response = FileResponse(handle, as_attachment=True, filename=filename, content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


def safe_download_name(title: str, suffix: str) -> str:
    base = "".join(c for c in title if c.isalnum() or c in " ._-")[:60].strip() or "fayl"
    return f"{base}{suffix}"
