from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.access.roles import ROLE_PERMISSIONS, RoleCode


class Command(BaseCommand):
    help = "Create/update the role groups and their permissions. Idempotent; never grants superuser rights."

    def handle(self, *args, **options):
        verbose = options.get("verbosity", 1) > 0
        for code in RoleCode.values:
            perms = []
            for dotted in ROLE_PERMISSIONS[code]:
                app_label, codename = dotted.split(".", 1)
                try:
                    perms.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
                except Permission.DoesNotExist as exc:
                    raise CommandError(f"Unknown permission: {dotted}") from exc
            group, created = Group.objects.get_or_create(name=code)
            group.permissions.set(perms)
            if verbose:
                self.stdout.write(f"{'created' if created else 'updated'}: {code} ({len(perms)} permissions)")
