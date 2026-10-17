from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import BackupCode, TotpDevice
from apps.accounts.notifications import notify_security_event
from apps.accounts.sessions import invalidate_user_sessions
from apps.accounts.twofactor import requires_two_factor
from apps.audit.models import AuditLog
from apps.audit.services import record


class Command(BaseCommand):
    help = (
        "Recovery for a user who lost the authenticator AND all backup codes. Removes the device and backup codes and "
        "closes all sessions; the user must enrol again at the next sign-in. Needs server access; the action is audited. "
        "Verify the person's identity out of band first (see docs/PRODUCTION_SECURITY_REQUIREMENTS.md)."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username__iexact=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("No such user.") from exc
        if not options["yes"]:
            answer = input(f"Reset 2FA for '{user.get_username()}'? Type the username to confirm: ")
            if answer.strip().lower() != user.get_username().lower():
                raise CommandError("Cancelled.")
        BackupCode.objects.filter(user=user).delete()
        TotpDevice.objects.filter(user=user).delete()
        closed = invalidate_user_sessions(user)
        record(AuditLog.Action.TWO_FACTOR_RESET, user=user, meta={"via": "management_command", "sessions_closed": closed})
        notify_security_event(user, "two_factor_reset")
        enrol = "must enrol again at next sign-in" if requires_two_factor(user) else "may enable it again from the security page"
        self.stdout.write(f"2FA reset for {user.get_username()}; {closed} session(s) closed; the user {enrol}.")
