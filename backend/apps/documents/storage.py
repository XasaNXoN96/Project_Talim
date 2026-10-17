"""Private file storage. Files live OUTSIDE static/media roots and have no URL: they can only leave through
the download view, after a permission check."""
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None, file_permissions_mode=0o600, directory_permissions_mode=0o700)

    def url(self, name):  # never produce a public address
        raise ValueError("Private documents have no public URL.")


def new_storage_name(extension: str) -> str:
    """Random name; the client-supplied name never influences the path. Extension comes from our allowlist."""
    token = uuid.uuid4().hex
    return f"{token[:2]}/{token}.{extension}"
