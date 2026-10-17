"""Upload validation. Everything here decides on the BYTES, never on what the client claims.

What this does and does NOT do
------------------------------
It checks size, an extension allowlist, that the leading bytes (and for Office/ODF files the ZIP structure) match the
extension, that the client-declared MIME type is not contradictory, and it rejects a few well known active-content
markers (PDF JavaScript/launch actions, Office macros). That reduces risk; it is NOT a malware scan. No antivirus is
connected: an infected but well-formed PDF or Office file will pass. Files are therefore only ever served as
attachments (never rendered by the browser) with a neutral content type.
"""
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

from django.conf import settings

ALLOWED = {
    # ext: (detected type label, acceptable declared MIME types)
    "pdf": ("pdf", {"application/pdf"}),
    "png": ("png", {"image/png"}),
    "jpg": ("jpeg", {"image/jpeg", "image/pjpeg"}),
    "jpeg": ("jpeg", {"image/jpeg", "image/pjpeg"}),
    "txt": ("text", {"text/plain"}),
    "docx": ("docx", {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    "xlsx": ("xlsx", {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    "pptx": ("pptx", {"application/vnd.openxmlformats-officedocument.presentationml.presentation"}),
    "odt": ("odt", {"application/vnd.oasis.opendocument.text"}),
    "ods": ("ods", {"application/vnd.oasis.opendocument.spreadsheet"}),
}
GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}
# Any dot-separated part of the client name that is one of these makes the name suspect ("report.php.pdf").
DANGEROUS_PARTS = {
    "php", "php3", "php4", "php5", "phtml", "phar", "asp", "aspx", "jsp", "jspx", "cgi", "pl", "py", "rb", "sh", "bash", "bat", "cmd", "com",
    "exe", "dll", "msi", "scr", "ps1", "vbs", "vbe", "js", "mjs", "jar", "html", "htm", "xhtml", "shtml", "svg", "svgz", "xml", "xsl", "swf",
    "hta", "lnk", "docm", "xlsm", "pptm", "dotm", "xlam", "zip", "rar", "7z", "gz", "tar", "iso", "dmg", "apk",
}
OFFICE_REQUIRED = {"docx": "word/", "xlsx": "xl/", "pptx": "ppt/"}
ODF_MIMETYPE = {"odt": b"application/vnd.oasis.opendocument.text", "ods": b"application/vnd.oasis.opendocument.spreadsheet"}
ZIP_MAX_ENTRIES = 5000
ZIP_MAX_UNCOMPRESSED = 200 * 1024 * 1024
ZIP_MAX_RATIO = 200
PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)\b")


class UploadRejected(Exception):
    """`code` is a short machine-readable reason (safe to log); the message is shown to the user."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CheckedUpload:
    display_name: str
    extension: str
    kind: str
    size: int
    data: bytes
    scan_status: str = "not_scanned"  # clean | not_scanned (scanner disabled); set by apps.documents.files
    scan_engine: str = ""


def max_bytes():
    return int(settings.DOCUMENT_MAX_BYTES)


def clean_display_name(raw: str) -> str:
    """Name for DISPLAY only: no directories, no control or bidi-override characters, bounded length. Never a path."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn") and ch not in "  ")
    name = name.strip().strip(".")
    return name[:150]


def _split(name: str):
    parts = name.lower().split(".")
    return parts[:-1], parts[-1] if len(parts) > 1 else ""


def _check_zip(data: bytes, ext: str):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadRejected("bad_zip", "Fayl buzilgan yoki kengaytmasiga mos kelmaydi.") from exc
    infos = zf.infolist()
    if len(infos) > ZIP_MAX_ENTRIES:
        raise UploadRejected("zip_entries", "Fayl tarkibi shubhali (juda ko‘p elementlar).")
    total = 0
    for info in infos:
        total += info.file_size
        n = info.filename
        if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") or info.flag_bits & 0x1:
            raise UploadRejected("zip_unsafe", "Fayl tarkibi xavfli yoki shifrlangan.")
        if info.compress_size and info.file_size / info.compress_size > ZIP_MAX_RATIO and info.file_size > 1024 * 1024:
            raise UploadRejected("zip_bomb", "Fayl tarkibi shubhali (haddan tashqari siqilgan).")
    if total > ZIP_MAX_UNCOMPRESSED:
        raise UploadRejected("zip_size", "Fayl ochilgandagi hajmi juda katta.")
    names = [i.filename for i in infos]
    if ext in OFFICE_REQUIRED:
        if "[Content_Types].xml" not in names or not any(n.startswith(OFFICE_REQUIRED[ext]) for n in names):
            raise UploadRejected("office_structure", "Fayl kengaytmasiga mos kelmaydi.")
        if any(n.lower().endswith(("vbaproject.bin", ".exe", ".dll")) or "/activex/" in n.lower() for n in names):
            raise UploadRejected("office_active", "Makros yoki faol tarkibli fayllar qabul qilinmaydi.")
    else:
        try:
            ok = "mimetype" in names and zf.read("mimetype").strip() == ODF_MIMETYPE[ext]
        except (KeyError, RuntimeError, zipfile.BadZipFile):
            ok = False
        if not ok:
            raise UploadRejected("odf_structure", "Fayl kengaytmasiga mos kelmaydi.")
        if any(n.startswith("Scripts/") or n.startswith("Basic/") for n in names):
            raise UploadRejected("office_active", "Makros yoki faol tarkibli fayllar qabul qilinmaydi.")


def validate_upload(uploaded) -> CheckedUpload:
    """Raises UploadRejected. `uploaded` is a Django UploadedFile."""
    limit = max_bytes()
    size = getattr(uploaded, "size", None)
    if size is None or size <= 0:
        raise UploadRejected("empty", "Fayl bo‘sh.")
    if size > limit:
        raise UploadRejected("too_large", f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasligi kerak.")
    name = clean_display_name(getattr(uploaded, "name", ""))
    if not name or "\x00" in (getattr(uploaded, "name", "") or ""):
        raise UploadRejected("bad_name", "Fayl nomi noto‘g‘ri.")
    stem_parts, ext = _split(name)
    if ext not in ALLOWED:
        raise UploadRejected("extension", "Bu fayl turi ruxsat etilmagan. Ruxsat etilgan: " + ", ".join(sorted(ALLOWED)) + ".")
    if any(p in DANGEROUS_PARTS for p in stem_parts):
        raise UploadRejected("double_extension", "Fayl nomida xavfli kengaytma bor (masalan, report.php.pdf).")
    declared = (getattr(uploaded, "content_type", "") or "").split(";")[0].strip().lower()
    kind, mimes = ALLOWED[ext]
    if declared not in GENERIC_MIME and declared not in mimes:
        raise UploadRejected("mime_mismatch", "Fayl turi kengaytmasiga mos kelmaydi.")
    uploaded.seek(0)
    data = uploaded.read(limit + 1)
    if len(data) > limit:
        raise UploadRejected("too_large", f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasligi kerak.")
    uploaded.seek(0)
    if kind == "pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejected("signature", "Fayl mazmuni kengaytmasiga mos kelmaydi.")
        if PDF_ACTIVE.search(data):
            raise UploadRejected("pdf_active", "Faol tarkibli (skript, ilova) PDF qabul qilinmaydi.")
    elif kind == "png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise UploadRejected("signature", "Fayl mazmuni kengaytmasiga mos kelmaydi.")
    elif kind == "jpeg":
        if not data.startswith(b"\xff\xd8\xff"):
            raise UploadRejected("signature", "Fayl mazmuni kengaytmasiga mos kelmaydi.")
    elif kind == "text":
        if b"\x00" in data:
            raise UploadRejected("signature", "Fayl mazmuni kengaytmasiga mos kelmaydi.")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected("signature", "Matn fayli UTF-8 bo‘lishi kerak.") from exc
    else:
        if not data.startswith(b"PK\x03\x04"):
            raise UploadRejected("signature", "Fayl mazmuni kengaytmasiga mos kelmaydi.")
        _check_zip(data, ext)
    return CheckedUpload(display_name=name, extension=ext, kind=kind, size=len(data), data=data)
