"""Achievement video files: ONE path, decided on the BYTES (never on what the client says).

1. size cap (settings.ACHIEVEMENT_VIDEO_MAX_BYTES) and a name/extension that matches the content (mp4 or webm);
2. detection by signature: MP4 = an `ftyp` box with a known brand; WebM = the EBML header with doc type "webm";
3. MP4 structure: the top-level boxes must tile the file exactly and contain `moov` and `mdat` (a truncated or disguised file is refused);
4. antivirus (clamd, fail-closed: no clean verdict = refused);
5. camera metadata: in an MP4 the `udta` and `meta` boxes of `moov` (phones put the GPS position and device there) are overwritten in place
   with a `free` box of the same size, so every offset stays valid and the position is gone. WebM metadata is NOT stripped (documented).
The video is NOT re-encoded: playback needs a browser-compatible codec (H.264/AAC in MP4, VP8/VP9 in WebM); that is the sender's job."""
import hashlib
import struct
from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.documents import files, scanner
from apps.documents.validation import UploadRejected

MP4_BRANDS = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash", b"msdh", b"qt  "}
EXTENSIONS = {"mp4": "mp4", "m4v": "mp4", "webm": "webm"}
CONTENT_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
MAX_BOXES = 5000


@dataclass(frozen=True)
class CheckedVideo:
    data: bytes
    ext: str  # mp4 | webm
    content_type: str
    sha256: str
    scan_status: str


def max_bytes():
    return int(settings.ACHIEVEMENT_VIDEO_MAX_BYTES)


def mb(n):
    return max(n // (1024 * 1024), 1)


def detect(data: bytes):
    """'mp4' | 'webm' | None, from the first bytes only."""
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in MP4_BRANDS:
        return "mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3" and b"webm" in data[:64]:
        return "webm"
    return None


def _boxes(data, start, end):
    """Yield (offset, size, type, header_size) of the boxes that tile data[start:end] exactly; raise ValueError otherwise."""
    pos, count = start, 0
    while pos < end:
        count += 1
        if count > MAX_BOXES or end - pos < 8:
            raise ValueError("box table")
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            if end - pos < 16:
                raise ValueError("box size")
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise ValueError("box size")
        yield pos, size, kind, header
        pos += size


def check_mp4_structure(data):
    kinds = [kind for _pos, _size, kind, _h in _boxes(data, 0, len(data))]
    if b"moov" not in kinds or b"mdat" not in kinds:
        raise ValueError("moov/mdat missing")


def neutralize_mp4(data: bytes) -> bytes:
    """Overwrite moov/udta and moov/meta (camera, GPS) with a `free` box of the same length. Same length: no offset in the file moves."""
    out = bytearray(data)
    for pos, size, kind, header in _boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        for cpos, csize, ckind, cheader in _boxes(data, pos + header, pos + size):
            if ckind in (b"udta", b"meta"):
                out[cpos + 4:cpos + 8] = b"free"
                out[cpos + cheader:cpos + csize] = b"\0" * (csize - cheader)
    return bytes(out)


def _read(uploaded):
    uploaded.seek(0)
    return b"".join(uploaded.chunks())


def prepare_video(uploaded, *, request=None, user=None) -> CheckedVideo:
    """Returns the bytes to store. Raises UploadRejected with a message fit for the form; refusals are audited (reason code only)."""
    try:
        return _prepare(uploaded)
    except UploadRejected as exc:
        if request is not None:
            if exc.code == "malware":
                record(AuditLog.Action.FILE_THREAT_DETECTED, request=request, user=user, object_type="Achievement", meta={"signature": getattr(exc, "signature", "")})
            record(AuditLog.Action.DOCUMENT_UPLOAD_REJECTED, request=request, user=user, object_type="Achievement", meta={"reason": exc.code, "kind": "video"})
        raise


def _prepare(uploaded) -> CheckedVideo:
    limit = max_bytes()
    if uploaded.size > limit:
        raise UploadRejected("too_large", _("Video hajmi %(mb)d MB dan oshmasligi kerak.") % {"mb": mb(limit)})
    name = (uploaded.name or "").lower()
    ext = EXTENSIONS.get(name.rsplit(".", 1)[-1] if "." in name else "")
    if ext is None:
        raise UploadRejected("bad_extension", _("Faqat MP4 yoki WebM video yuklash mumkin."))
    data = _read(uploaded)
    if len(data) > limit:  # the declared size can lie
        raise UploadRejected("too_large", _("Video hajmi %(mb)d MB dan oshmasligi kerak.") % {"mb": mb(limit)})
    if detect(data) != ext:
        raise UploadRejected("content_mismatch", _("Fayl mazmuni video formatiga mos kelmaydi."))
    if ext == "mp4":
        try:
            check_mp4_structure(data)
        except (ValueError, struct.error) as exc:
            raise UploadRejected("corrupt", _("Video fayli buzilgan yoki to‘liq emas.")) from exc
    scan_status = "not_scanned"
    if scanner.mode() != "disabled":
        try:
            result = scanner.scan_bytes(data, timeout=settings.CLAMAV_VIDEO_TIMEOUT)
        except scanner.ScanFailed as exc:
            raise UploadRejected(exc.code, files.SCAN_MESSAGES.get(exc.code, files.SCAN_MESSAGES["scan_error"])) from exc
        if not result.clean:
            err = UploadRejected("malware", _("Faylda zararli dastur aniqlandi. Fayl qabul qilinmadi."))
            err.signature = result.signature
            raise err
        scan_status = "clean"
    if ext == "mp4":
        try:
            data = neutralize_mp4(data)
        except (ValueError, struct.error) as exc:
            raise UploadRejected("corrupt", _("Video fayli buzilgan yoki to‘liq emas.")) from exc
    return CheckedVideo(data=data, ext=ext, content_type=CONTENT_TYPES[ext], sha256=hashlib.sha256(data).hexdigest(), scan_status=scan_status)
