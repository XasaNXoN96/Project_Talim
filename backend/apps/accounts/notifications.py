"""E-mail notices about security-relevant changes to an account.

They help a person notice a takeover ("I did not do this"). They never contain secrets: no passwords, codes, links or
backup codes. A delivery failure never breaks the action that triggered it and logs only the error type.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.audit.services import client_ip

logger = logging.getLogger(__name__)

EVENTS = {
    "password_changed": ("Parolingiz almashtirildi", "Hisobingiz paroli almashtirildi. Boshqa qurilmalardagi sessiyalar yopildi."),
    "password_reset": ("Parolingiz tiklandi", "Parolni tiklash havolasi orqali hisobingizga yangi parol o‘rnatildi. Barcha sessiyalar yopildi."),
    "two_factor_enabled": ("Ikki bosqichli himoya yoqildi", "Hisobingizda ikki bosqichli himoya (2FA) yoqildi."),
    "two_factor_disabled": ("Ikki bosqichli himoya o‘chirildi", "Hisobingizda ikki bosqichli himoya (2FA) o‘chirildi. Endi hisob faqat parol bilan himoyalangan."),
    "backup_codes_regenerated": ("Zaxira kodlar yangilandi", "Hisobingizning zaxira kodlari yangilandi; eskilari bekor qilindi."),
    "two_factor_reset": ("2FA administrator tomonidan tiklandi", "Hisobingizning ikki bosqichli himoyasi administrator tomonidan olib tashlandi. Keyingi kirishda uni qayta sozlaysiz."),
    "invitation": ("Xodimlar portaliga taklif", "Siz uchun xodimlar portalida hisob yaratildi."),
}


def notify_security_event(user, event, request=None):
    if not user.email or event not in EVENTS:
        return False
    subject, line = EVENTS[event]
    when = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    ip = client_ip(request) if request is not None else None
    body = (
        f"Assalomu alaykum!\n\n{line}\n\n"
        f"Vaqt: {when}" + (f"\nManzil (IP): {ip}" if ip else "") + "\n\n"
        "Agar buni siz qilmagan bo‘lsangiz, zudlik bilan administratorga murojaat qiling va parolingizni almashtiring.\n"
    )
    try:
        EmailMessage(f"{settings.TWO_FACTOR_ISSUER}: {subject}", body, to=[user.email]).send()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Security notice could not be sent (%s)", type(exc).__name__)
        return False
