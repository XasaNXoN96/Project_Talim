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


# What the portal may show inside the page. Fixed by the extension that validation already matched to the real content;
# the type sent to the browser comes from THIS table, never from the upload. Everything else is download-only.
INLINE_IMAGE = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
INLINE_PDF = {"pdf": "application/pdf"}
INLINE_TEXT = ("txt",)
TEXT_PREVIEW_BYTES = 100_000


def preview_kind(extension: str):
    ext = (extension or "").lower()
    if ext in INLINE_IMAGE:
        return "image"
    if ext in INLINE_PDF:
        return "pdf"
    if ext in INLINE_TEXT:
        return "text"
    return None


def inline_response(field_file, *, extension: str):
    """Image/PDF shown in the portal. Call it AFTER the permission check. Only the fixed types above are ever sent inline;
    the page that embeds it is same-origin, and the file itself may do nothing (no scripts, no framing by other sites)."""
    ext = extension.lower()
    content_type = INLINE_IMAGE.get(ext) or INLINE_PDF.get(ext)
    if content_type is None:
        raise Http404
    try:
        handle = field_file.storage.open(field_file.name, "rb")
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    response = FileResponse(handle, as_attachment=False, content_type=content_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["X-Frame-Options"] = "SAMEORIGIN"  # the portal page embeds it; foreign sites may not
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'"
    return response


def read_text_preview(field_file):
    """(text, truncated) of a plain-text file, decoded leniently; the template escapes it."""
    try:
        with field_file.storage.open(field_file.name, "rb") as handle:
            raw = handle.read(TEXT_PREVIEW_BYTES + 1)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise Http404 from exc
    return raw[:TEXT_PREVIEW_BYTES].decode("utf-8", errors="replace"), len(raw) > TEXT_PREVIEW_BYTES
