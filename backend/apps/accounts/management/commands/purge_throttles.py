from django.core.management.base import BaseCommand

from apps.accounts import throttle


class Command(BaseCommand):
    help = "Delete rate-limit rows that no longer matter. Run from cron (e.g. hourly)."

    def handle(self, *args, **options):
        self.stdout.write(f"deleted {throttle.purge_expired()} expired throttle row(s)")
