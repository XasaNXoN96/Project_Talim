from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.access.roles import ROLE_PERMISSIONS, RoleCode


class Command(BaseCommand):
    help = (
        "Create the role groups and add the permissions the code defines for them. Idempotent. Never touches users, assignments or personal permissions, "
        "never grants superuser rights. Permissions that someone added to a role group by hand are KEPT and reported; they are removed only with --prune. "
        "Use --dry-run to see exactly what would change without changing anything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="show the plan per role (+ added, - removed, = kept extra) and change nothing")
        parser.add_argument("--prune", action="store_true", help="also REMOVE permissions that are not part of a role's definition (explicit opt-in)")

    def plan(self):
        """[(code, group_or_None, wanted_perms, to_add, extras)] -- computed without writing anything."""
        out = []
        for code in RoleCode.values:
            wanted = []
            for dotted in ROLE_PERMISSIONS[code]:
                app_label, codename = dotted.split(".", 1)
                try:
                    wanted.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
                except Permission.DoesNotExist as exc:
                    raise CommandError(f"Unknown permission: {dotted}") from exc
            group = Group.objects.filter(name=code).first()
            have = {p.pk: p for p in group.permissions.select_related("content_type")} if group else {}
            wanted_pks = {p.pk for p in wanted}
            to_add = [p for p in wanted if p.pk not in have]
            extras = [p for pk, p in have.items() if pk not in wanted_pks]
            out.append((code, group, wanted, to_add, extras))
        return out

    @staticmethod
    def name(p):
        return f"{p.content_type.app_label}.{p.codename}"

    def handle(self, *args, **options):
        verbose = options.get("verbosity", 1) > 0
        dry, prune = options["dry_run"], options["prune"]
        changed = False
        for code, group, wanted, to_add, extras in self.plan():
            lines = []  # (loud, text)
            if group is None:
                lines.append((False, f"role {code}: {'would create' if dry else 'create'} group"))
            lines += [(False, f"role {code}: + {self.name(p)}") for p in to_add]
            for p in extras:
                if prune:
                    lines.append((True, f"role {code}: - {self.name(p)} ({'would be removed' if dry else 'REMOVED'} by --prune: not in the role definition)"))
                else:
                    lines.append((True, f"role {code}: = {self.name(p)} kept (not in the role definition; removal needs --prune)"))
            if not dry:
                if group is None:
                    group = Group.objects.create(name=code)
                    to_add = wanted
                group.permissions.add(*to_add)
                if prune and extras:
                    group.permissions.remove(*extras)
            changed = changed or bool(to_add or group is None or (prune and extras))
            for loud, text in lines:
                if loud:
                    self.stderr.write(text)  # extras are what an operator must notice: shown even when quiet
                elif verbose:
                    self.stdout.write(text)
            if verbose and not lines:
                self.stdout.write(f"role {code}: up to date ({len(wanted)} permissions)")
        if dry:
            self.stdout.write("DRY RUN: nothing was changed." + ("" if changed else " The roles are up to date."))
