from django.core.management.base import BaseCommand

from apps.organization.import_views import wipe_expired


class Command(BaseCommand):
    help = "Empty the parsed rows (personal data) of employee-import previews that were not confirmed within EMPLOYEE_IMPORT_TTL_MINUTES. Safe to run from cron."

    def handle(self, *args, **options):
        self.stdout.write(f"wiped: {wipe_expired()}")
