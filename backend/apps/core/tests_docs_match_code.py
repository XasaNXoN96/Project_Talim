"""The operator documents name files, commands, flags, units and variables. A staging run is only reproducible if every name exists.
This reads the three operator documents and checks each reference against the repository, so a rename or a typo fails a test instead of an operator."""
import re
from pathlib import Path

from django.core.management import get_commands
from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
DOCS = [REPO / "docs" / n for n in ("STAGING_OPERATOR_CHECKLIST.md", "STAGING_RUNBOOK.md", "STAGING_BLOCKERS.md")]
TEXT = {p.name: p.read_text() for p in DOCS}
ALL = "\n".join(TEXT.values())


def source_of(*parts):
    return (BACKEND.joinpath(*parts)).read_text()


class OperatorDocumentsMatchTheCode(SimpleTestCase):
    def test_every_repository_path_named_in_the_documents_exists(self):
        missing = []
        for m in re.finditer(r"(?<![\w/.])((?:backend/)?deploy/[A-Za-z0-9_./@\-]*[A-Za-z0-9_])(?![A-Za-z0-9_./@\-*])", ALL):  # a glob such as verify_*.sh is not a path  # inside backticks or inside a shell command alike
            ref = m.group(1)
            rel = ref.removeprefix("backend/")
            if not (BACKEND / rel).exists():
                missing.append(ref)
        self.assertEqual(sorted(set(missing)), [])

    def test_every_manage_py_command_exists(self):
        known = set(get_commands())
        named = set(re.findall(r"manage\.py ([a-z_]+)", ALL))
        self.assertTrue({"seed_roles", "check_scanner", "migrate", "collectstatic", "verify_document_files"} <= named)
        self.assertEqual(sorted(named - known), [])

    def test_every_flag_of_our_own_commands_and_scripts_exists_in_their_source(self):
        sources = {"seed_roles": source_of("apps/access/management/commands/seed_roles.py"), "check_scanner": source_of("apps/documents/management/commands/check_scanner.py"),
                   "preflight.py": source_of("deploy/staging/preflight.py"), "smoke_remote.py": source_of("deploy/staging/smoke_remote.py")}
        problems = []
        for line in ALL.splitlines():
            for name, text in sources.items():
                if name in line:
                    for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", re.split(r"&&|\||;|`", line.split(name, 1)[1])[0]):  # only this command: stop at && | ; or the closing backtick
                        if flag.startswith("--insecure") and name == "smoke_remote.py":
                            flag = "--insecure-self-signed"
                        if flag not in text and flag not in ("--no-record",):
                            problems.append((name, flag))
        self.assertEqual(problems, [])

    def test_every_systemd_unit_named_exists_and_instances_point_at_real_commands(self):
        units = set(re.findall(r"talim-[A-Za-z0-9_]+(?:@[A-Za-z0-9_]*)?\.(?:service|timer)", ALL))
        systemd = BACKEND / "deploy" / "systemd"
        commands = set(get_commands())
        problems = []
        for u in sorted(units):
            if "@" in u:
                template, _, rest = u.partition("@")
                instance = rest.rsplit(".", 1)[0]
                if not (systemd / f"{template}@.service").exists():
                    problems.append(u)
                if instance and instance not in commands:
                    problems.append(u + " (no such manage.py command)")
            elif not (systemd / u).exists():
                problems.append(u)
        self.assertEqual(problems, [])

    def test_every_release_variable_of_the_checklist_is_read_by_release_sh(self):
        text = source_of("deploy/staging/release.sh")
        for var in ("RELEASES_DIR", "CURRENT_LINK", "HEALTH_URL", "HEALTH_HOST", "RESTART_CMD", "PRE_BACKUP_CMD", "MIGRATE_CMD_PREFIX", "POST_MIGRATE_SQL_CMD"):
            self.assertIn(var, ALL, var)
            self.assertIn(var, text, var)

    def test_environment_variable_names_in_the_checklist_exist_in_the_code(self):
        settings_text = "\n".join(p.read_text() for p in (BACKEND / "config" / "settings").glob("*.py"))
        code = settings_text + source_of("deploy/staging/preflight.py") + source_of("deploy/backup/backup.sh") + source_of("deploy/backup/restore_check.sh") + source_of("apps/core/backup_jobs.py")
        section = TEXT["STAGING_OPERATOR_CHECKLIST.md"].split("## 4.")[1].split("## 5.")[0]
        problems = [v for v in sorted(set(re.findall(r"\b((?:DJANGO|DB|EMAIL|OTP|CLAMAV|BACKUP|DOCUMENT|NOTIFICATION)_[A-Z_]+|PGUSER|PGPASSFILE|PGHOST|PGPORT|PGDATABASE|PRIVATE_MEDIA_ROOT)\b", section))) if v not in code]
        self.assertEqual(problems, [])

    def test_the_sql_and_script_commands_in_the_checklist_use_variables_the_files_define(self):
        roles = source_of("deploy/postgres/create_roles.sql") + source_of("deploy/postgres/create_backup_role.sql") + source_of("deploy/postgres/apply_grants.sql")
        for var in ("owner", "app", "db", "owner_password", "app_password", "backup_role", "backup_password"):
            self.assertIn(f"-v {var}=", TEXT["STAGING_OPERATOR_CHECKLIST.md"], var)
            self.assertIn(f":{'\"' if not var.endswith('password') else chr(39)}{var}", roles, var)
