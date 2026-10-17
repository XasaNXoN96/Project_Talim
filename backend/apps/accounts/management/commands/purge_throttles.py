from apps.accounts import throttle
from apps.core.jobs import TrackedCommand


class Command(TrackedCommand):
    help = "Delete rate-limit rows whose lock is over and whose window is long gone; an active lock is never deleted. Safe to repeat. Schedule hourly."
    job_name = "purge_throttles"

    def run_job(self, run, *args, **options):
        run.processed = throttle.purge_expired()
        self.stdout.write(f"deleted {run.processed} expired throttle row(s)")
