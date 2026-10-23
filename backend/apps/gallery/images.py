"""Gallery photos: the achievements picture path (validation + antivirus + re-encode to JPEG without metadata, max 1600 px), plus a thumbnail."""
import io

from PIL import Image

from apps.achievements.images import prepare_image

THUMB = 480


def prepare_photo(uploaded, *, request=None, user=None):
    """Returns (full JPEG bytes, thumbnail JPEG bytes). Raises UploadRejected with a message fit for the form."""
    full = prepare_image(uploaded, request=request, user=user)
    image = Image.open(io.BytesIO(full))
    image.thumbnail((THUMB, THUMB), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=80, optimize=True)
    return full, out.getvalue()
