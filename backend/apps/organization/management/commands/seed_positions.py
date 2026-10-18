from django.core.management.base import BaseCommand

from apps.organization.models import Position

# Starter list of positions, to be confirmed by the department (they stay editable in the portal).
POSITIONS = [
    "Bo‘lim boshlig‘i", "Bo‘lim boshlig‘i o‘rinbosari", "Bosh mutaxassis", "Metodist", "Inspektor", "Buxgalter", "Kadrlar bo‘yicha mutaxassis",
    "Maktab direktori", "Muassasa mudiri", "Direktor o‘rinbosari (o‘quv ishlari bo‘yicha)",
    "Direktor o‘rinbosari (ma’naviy-ma’rifiy ishlar bo‘yicha)", "Direktor o‘rinbosari (moliya-xo‘jalik ishlari bo‘yicha)",
    "O‘qituvchi", "Amaliy psixolog", "Kutubxonachi", "Ijtimoiy pedagog", "Tarbiyachi",
]


class Command(BaseCommand):
    help = "Add the starter list of positions. Idempotent: existing positions are never changed or removed."

    def handle(self, *args, **options):
        created = [name for name in POSITIONS if Position.objects.get_or_create(name=name)[1]]
        self.stdout.write(f"positions added: {len(created)}, already present: {len(POSITIONS) - len(created)}")
