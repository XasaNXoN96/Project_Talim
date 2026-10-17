from django.utils.translation import gettext_lazy as _


def site(request):
    return {
        "SITE_NAME": _("Mirzacho‘l tumani Xalq ta’limi bo‘limi"),
        "SITE_SHORT": _("Xalq ta’limi bo‘limi"),
        "SITE_DISTRICT": _("Mirzacho‘l tumani"),
    }
