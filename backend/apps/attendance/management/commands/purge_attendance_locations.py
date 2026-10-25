from apps.attendance.services import purge_locations
from apps.core.jobs import TrackedCommand


class Command(TrackedCommand):
    help = (
        "Wipe the coordinates of attendance presses older than ATTENDANCE_LOCATION_RETENTION_DAYS (default 90). The times and the "
        "inside/outside flag stay. Safe to repeat. Schedule once a day (docs/SCHEDULER.md)."
    )
    job_name = "purge_attendance_locations"

    def run_job(self, run, *args, **options):
        run.processed = purge_locations()
        self.stdout.write(f"wiped: {run.processed}")
