import hashlib
from functools import lru_cache

from django.conf import settings
from django.utils.translation import gettext_lazy as _


@lru_cache(maxsize=1)
def asset_version():
    """Short hash of the shipped CSS/JS: it goes into every stylesheet/script URL (?v=...), so a new deployment is never shown with stale cached files."""
    files = [settings.BASE_DIR / "static" / "css" / "backend.css", settings.BASE_DIR / "static" / "js" / "site.js", settings.BASE_DIR / "static" / "js" / "gallery.js", settings.BASE_DIR / "static" / "js" / "portal.js",
             settings.BASE_DIR.parent / "assets" / "css" / "styles.css", settings.BASE_DIR.parent / "assets" / "js" / "app.js"]
    digest = hashlib.sha1()
    for f in files:
        try:
            digest.update(f.read_bytes())
        except OSError:
            digest.update(b"-")
    return digest.hexdigest()[:10]


def site(request):
    from apps.portal.hub import can_open_hub

    return {
        "show_admin_hub": can_open_hub(request.user) if hasattr(request, "user") else False,
        "ASSET_V": asset_version(),
        "SITE_NAME": _("Mirzacho‘l tumani Xalq ta’limi bo‘limi"),
        "SITE_SHORT": _("Xalq ta’limi bo‘limi"),
        "SITE_DISTRICT": _("Mirzacho‘l tumani"),
    }
