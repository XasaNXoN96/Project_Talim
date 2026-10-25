"""Achievement pictures: the shared validation + antivirus (apps.documents.files), then decoded with Pillow and RE-ENCODED to a JPEG of at
most 1600 px on the long side. Re-encoding drops metadata (EXIF location, camera) and any payload hidden in the file."""
import io

from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from apps.documents import files
from apps.documents.validation import UploadRejected

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 1600
ALLOWED_KINDS = {"png", "jpeg"}


def prepare_image(uploaded, *, request=None, user=None, object_type="Achievement") -> bytes:
    if uploaded.size > MAX_BYTES:
        raise UploadRejected("too_large", _("Rasm hajmi 8 MB dan oshmasligi kerak."))
    if request is not None:
        checked = files.check_or_audit(uploaded, request=request, user=user, object_type=object_type)
    else:
        checked = files.screen_upload(uploaded)
    if checked.kind not in ALLOWED_KINDS:
        raise UploadRejected("not_image", _("Faqat JPG yoki PNG rasm yuklash mumkin."))
    try:
        probe = Image.open(io.BytesIO(checked.data))
        if probe.width * probe.height > MAX_PIXELS:
            raise UploadRejected("too_many_pixels", _("Rasm juda katta (piksellar soni)."))
        probe.verify()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(checked.data)))
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, "JPEG", quality=85, optimize=True)
    except UploadRejected:
        raise
    except Exception as exc:  # noqa: BLE001 - any decoder failure means "not a usable picture"
        raise UploadRejected("not_image", _("Rasmni o‘qib bo‘lmadi. Boshqa fayl tanlang.")) from exc
    return out.getvalue()
