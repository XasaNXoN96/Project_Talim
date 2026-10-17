from apps.core.jobs import TrackedCommand
from apps.organization.import_views import wipe_expired


class Command(TrackedCommand):
    help = (
        "Empty the parsed rows (personal data) of employee-import previews that were not confirmed within EMPLOYEE_IMPORT_TTL_MINUTES. "
        "Only previews that are still waiting AND older than the limit are touched; completed, cancelled and young ones are left alone. "
        "Safe to repeat. Schedule every 15 minutes (docs/SCHEDULER.md)."
    )
    job_name = "purge_employee_imports"

    def run_job(self, run, *args, **options):
        run.processed = wipe_expired()
        self.stdout.write(f"wiped: {run.processed}")
