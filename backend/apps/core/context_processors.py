from django.utils.translation import gettext_lazy as _


def site(request):
    from apps.portal.hub import can_open_hub

    return {
        "show_admin_hub": can_open_hub(request.user) if hasattr(request, "user") else False,
        "SITE_NAME": _("Mirzacho‘l tumani Xalq ta’limi bo‘limi"),
        "SITE_SHORT": _("Xalq ta’limi bo‘limi"),
        "SITE_DISTRICT": _("Mirzacho‘l tumani"),
    }
