"""Local development only."""
from .base import *  # noqa: F401,F403

DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# E-mail goes to backend/.dev_mail/ (gitignored) so reset links never reach the server log.

# Without a local clamd, uploads would be refused (fail-closed). Set DOCUMENT_SCAN_MODE=disabled in .env to work without one.
