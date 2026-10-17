from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.accounts.models import UserSession
from apps.core.jobs import TrackedCommand

GRACE = timedelta(hours=1)  # an index row younger than this is never removed (its session may not have been saved yet)


class Command(TrackedCommand):
    help = (
        "Delete expired Django sessions, and the 'active sessions' index rows whose session no longer exists. Sessions that are "
        "still valid (and their index rows) are never touched. Replaces `clearsessions` in the schedule (it does the same and "
        "records the run). Safe to repeat. Schedule daily."
    )
    job_name = "clear_expired_sessions"

    def run_job(self, run, *args, **options):
        now = timezone.now()
        expired, _ = Session.objects.filter(expire_date__lt=now).delete()
        live_keys = Session.objects.filter(expire_date__gte=now).values("session_key")
        stale, _ = UserSession.objects.exclude(session_key__in=live_keys).filter(first_seen_at__lt=now - GRACE).delete()
        run.processed = expired + stale
        self.stdout.write(f"expired sessions removed: {expired}; stale index rows removed: {stale}")
