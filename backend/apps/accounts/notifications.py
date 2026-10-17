"""E-mail notices about security-relevant changes to an account.

They help a person notice a takeover ("I did not do this"). They never contain secrets: no passwords, codes, links or
backup codes. A delivery failure never breaks the action that triggered it and logs only the error type.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from django.utils.translation import gettext, override
from django.utils.translation import gettext_lazy as _

from apps.audit.services import client_ip

from apps.core.locale import user_language

logger = logging.getLogger(__name__)

EVENTS = {
    "password_changed": (_("Parolingiz almashtirildi"), _("Hisobingiz paroli almashtirildi. Boshqa qurilmalardagi sessiyalar yopildi.")),
    "password_reset": (_("Parolingiz tiklandi"), _("Parolni tiklash havolasi orqali hisobingizga yangi parol o‘rnatildi. Barcha sessiyalar yopildi.")),
    "two_factor_enabled": (_("Ikki bosqichli himoya yoqildi"), _("Hisobingizda ikki bosqichli himoya (2FA) yoqildi.")),
    "two_factor_disabled": (_("Ikki bosqichli himoya o‘chirildi"), _("Hisobingizda ikki bosqichli himoya (2FA) o‘chirildi. Endi hisob faqat parol bilan himoyalangan.")),
    "backup_codes_regenerated": (_("Zaxira kodlar yangilandi"), _("Hisobingizning zaxira kodlari yangilandi; eskilari bekor qilindi.")),
    "two_factor_reset": (_("2FA administrator tomonidan tiklandi"), _("Hisobingizning ikki bosqichli himoyasi administrator tomonidan olib tashlandi. Keyingi kirishda uni qayta sozlaysiz.")),
    "invitation": (_("Xodimlar portaliga taklif"), _("Siz uchun xodimlar portalida hisob yaratildi.")),
}


def notify_security_event(user, event, request=None):
    if not user.email or event not in EVENTS:
        return False
    when = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    ip = client_ip(request) if request is not None else None
    with override(user_language(user)):  # the e-mail is written in the RECIPIENT's language
        subject, line = (str(x) for x in EVENTS[event])
        body = gettext("Assalomu alaykum!\n\n%(line)s\n\nVaqt: %(when)s") % {"line": line, "when": when}
        if ip:
            body += gettext("\nManzil (IP): %(ip)s") % {"ip": ip}
        body += "\n\n" + gettext("Agar buni siz qilmagan bo‘lsangiz, zudlik bilan administratorga murojaat qiling va parolingizni almashtiring.") + "\n"
    try:
        EmailMessage(f"{settings.TWO_FACTOR_ISSUER}: {subject}", body, to=[user.email]).send()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Security notice could not be sent (%s)", type(exc).__name__)
        return False
