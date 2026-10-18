"""Employee profile photos: one safe path.

Upload -> the shared validation + antivirus (apps.documents.files) -> decoded with Pillow and RE-ENCODED to a small JPEG.
Re-encoding drops metadata (EXIF location, camera, embedded payloads) and makes the stored bytes ours, not the client's.
The file lives in the private storage under a random name and has no public URL (see EmployeePhotoView)."""
import io

from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from apps.documents import files
from apps.documents.validation import UploadRejected

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
SIZE = 512
ALLOWED_KINDS = {"png", "jpeg"}


def prepare_photo(uploaded, *, request=None, user=None) -> bytes:
    """Returns the JPEG bytes to store. Raises UploadRejected with a message fit for the form."""
    if uploaded.size > MAX_BYTES:
        raise UploadRejected("too_large", _("Surat hajmi 5 MB dan oshmasligi kerak."))
    if request is not None:
        checked = files.check_or_audit(uploaded, request=request, user=user, object_type="Employee")
    else:
        checked = files.screen_upload(uploaded)
    if checked.kind not in ALLOWED_KINDS:
        raise UploadRejected("not_image", _("Faqat JPG yoki PNG rasm yuklash mumkin."))
    try:
        probe = Image.open(io.BytesIO(checked.data))
        if probe.width * probe.height > MAX_PIXELS:
            raise UploadRejected("too_many_pixels", _("Rasm juda katta (piksellar soni)."))
        probe.verify()
        image = Image.open(io.BytesIO(checked.data))
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        image = ImageOps.fit(image, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, "JPEG", quality=85, optimize=True)
    except UploadRejected:
        raise
    except Exception as exc:  # noqa: BLE001 - any decoder failure means "not a usable picture"
        raise UploadRejected("not_image", _("Rasmni o‘qib bo‘lmadi. Boshqa fayl tanlang.")) from exc
    return out.getvalue()
