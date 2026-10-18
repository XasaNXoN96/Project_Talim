#!/usr/bin/env python3
"""Pre-deployment audit of a staging/production host. Run as the application user (NOT root) BEFORE the first start and after every change.
Reads the environment file and the file system, never prints a secret value (only names and verdicts). Exit 0 = no FAIL (SKIPs are listed), 1 = at least one FAIL.
Usage: preflight.py [--env-file /etc/talim/talim.env] [--backend /srv/talim/backend] [--no-django]
A PASS here means "this configuration passes these rules", not "the server works": SMTP delivery, real certificates, DNS, firewall, and the restore of a real
backup are NOT checked here (printed as SKIP) and must be done by the operator (docs/DEPLOYMENT_READINESS.md §4)."""
import argparse
import os
import re
import stat
import subprocess
import sys

PLACEHOLDER = re.compile(r"CHANGE_?ME|<[^>]+>|^$|example\.(com|org)|^xxx|your[-_]", re.I)
REQUIRED = ["DJANGO_SETTINGS_MODULE", "DJANGO_DEBUG", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_ADMIN_URL",
            "DJANGO_TRUSTED_PROXIES", "DJANGO_PRIVATE_MEDIA_ROOT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "OTP_ENCRYPTION_KEYS",
            "DOCUMENT_SCAN_MODE", "EMAIL_HOST", "DEFAULT_FROM_EMAIL"]


def parse_env(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, name, detail=""):
        self.rows.append((status, name, detail))

    def passed(self, name, detail=""):
        self.add("PASS", name, detail)

    def failed(self, name, detail=""):
        self.add("FAIL", name, detail)

    def skipped(self, name, detail=""):
        self.add("SKIP", name, detail)

    @property
    def ok(self):
        return not any(r[0] == "FAIL" for r in self.rows)


def check_env_values(env, report):
    """Pure rules about the values (no file system, no database)."""
    missing = [k for k in REQUIRED if k not in env]
    report.passed("all required variables are present") if not missing else report.failed("required variables missing", ", ".join(missing))
    placeholders = [k for k in REQUIRED if k in env and PLACEHOLDER.search(env[k])]
    report.passed("no placeholder values") if not placeholders else report.failed("placeholder or empty values", ", ".join(placeholders))
    report.passed("DEBUG is off") if env.get("DJANGO_DEBUG", "").lower() in ("0", "false", "no", "off") else report.failed("DJANGO_DEBUG must be off")
    report.passed("production settings module") if env.get("DJANGO_SETTINGS_MODULE") == "config.settings.production" else report.failed("DJANGO_SETTINGS_MODULE must be config.settings.production")
    report.passed("secret key length >= 50") if len(env.get("DJANGO_SECRET_KEY", "")) >= 50 and "insecure" not in env.get("DJANGO_SECRET_KEY", "").lower() else report.failed("DJANGO_SECRET_KEY too short or a development value", "need >= 50 random characters; create one on the server: python -c 'import secrets;print(secrets.token_urlsafe(70))' (do not paste it anywhere else)")
    hosts = [h.strip() for h in env.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
    report.passed("ALLOWED_HOSTS has no wildcard") if hosts and not any(h in ("*", ".") or h.startswith("*") for h in hosts) else report.failed("ALLOWED_HOSTS empty or wildcard")
    origins = [o.strip() for o in env.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
    report.passed("CSRF trusted origins are https only") if origins and all(o.startswith("https://") and "*" not in o for o in origins) else report.failed("CSRF trusted origins must be explicit https:// origins")
    admin_path = env.get("DJANGO_ADMIN_URL", "").strip("/")
    report.passed("Django admin is not at a guessable path") if len(admin_path) >= 12 and admin_path.lower() not in ("administrator", "django-admin", "djangoadmin", "management", "dashboard") else report.failed("DJANGO_ADMIN_URL must be a long unguessable path (>= 12 characters), not admin/")
    report.passed("scanner is fail-closed (clamav)") if env.get("DOCUMENT_SCAN_MODE") == "clamav" else report.failed("DOCUMENT_SCAN_MODE must be clamav (fail-closed)")
    report.passed("CSP is enforcing (report-only not set)") if env.get("DJANGO_CSP_REPORT_ONLY", "0").lower() in ("0", "false", "no", "off", "") else report.failed("DJANGO_CSP_REPORT_ONLY is on: CSP would not block")
    try:
        from cryptography.fernet import Fernet
        keys = [k.strip() for k in env.get("OTP_ENCRYPTION_KEYS", "").split(",") if k.strip()]
        for k in keys:
            Fernet(k.encode())
        report.passed("OTP encryption keys are valid Fernet keys", f"{len(keys)} key(s)") if keys else report.failed("OTP_ENCRYPTION_KEYS empty")
    except Exception:  # noqa: BLE001 - never echo the value
        report.failed("OTP_ENCRYPTION_KEYS is not a valid Fernet key list", "create a key: python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'; comma-separated, newest first; store a copy OUTSIDE the server and the backups")
    report.passed("database runtime role differs from a typical owner/superuser name") if env.get("DB_USER", "") not in ("postgres", "root", "talim_owner") else report.failed("DB_USER must be the restricted runtime role, not postgres/owner")
    report.passed("HSTS decision recorded", f"DJANGO_HSTS_SECONDS={env.get('DJANGO_HSTS_SECONDS', '0')}") if re.fullmatch(r"\d+", env.get("DJANGO_HSTS_SECONDS", "0")) else report.failed("DJANGO_HSTS_SECONDS must be an integer")


def check_files(env_file, env, report):
    try:
        st = os.stat(env_file)
    except OSError:
        report.failed("environment file readable", "cannot stat it")
        return
    mode = stat.S_IMODE(st.st_mode)
    report.passed("environment file is not world-accessible", oct(mode)) if not mode & 0o007 else report.failed("environment file is world-accessible", oct(mode))
    report.passed("environment file is not writable by group/others", oct(mode)) if not mode & 0o022 else report.failed("environment file writable by group/others", oct(mode))
    report.passed("environment file is not owned by the running user") if st.st_uid != os.getuid() or os.getuid() == 0 else report.failed("environment file is owned by the application user (it could rewrite its own secrets); use root:talim 0640")
    for var, label in (("DJANGO_PRIVATE_MEDIA_ROOT", "document store"),):
        path = env.get(var)
        if not path or not os.path.isdir(path):
            report.failed(f"{label} directory exists", f"{var} does not exist: sudo install -d -o talim -g talim -m 0750 <path>")
            continue
        m = stat.S_IMODE(os.stat(path).st_mode)
        report.passed(f"{label} is not accessible to others", oct(m)) if not m & 0o007 else report.failed(f"{label} is accessible to others", oct(m))
        report.passed(f"{label} is writable by the application user") if os.access(path, os.W_OK) else report.failed(f"{label} is not writable by the application user")
    report.passed("running as an unprivileged user") if os.getuid() != 0 else report.failed("running as root")


def check_backup_env(path, env, report):
    """The backup/restore environment file (names, paths; secrets live in separate 0600 files). Pure file and value rules + one optional psql probe."""
    try:
        values = parse_env(open(path).read())
        st = os.stat(path)
    except OSError:
        report.failed("backup environment file readable", "cannot read it (create /etc/talim/backup.env: DEPLOYMENT_READINESS §4.11)")
        return
    mode = stat.S_IMODE(st.st_mode)
    report.passed("backup environment file is not world-accessible", oct(mode)) if not mode & 0o007 else report.failed("backup environment file is world-accessible", oct(mode))
    missing = [k for k in ("BACKUP_DIR", "BACKUP_PASSPHRASE_FILE", "PGUSER") if not values.get(k)]
    report.passed("BACKUP_DIR, BACKUP_PASSPHRASE_FILE and PGUSER are set") if not missing else report.failed("backup variables missing", ", ".join(missing))
    if values.get("PGUSER") and values["PGUSER"] == env.get("DB_USER"):
        report.failed("backup role must differ from the runtime role", "PGUSER equals DB_USER: the restore check needs CREATEDB, which the runtime role must never get (deploy/postgres/create_backup_role.sql)")
    elif values.get("PGUSER"):
        report.passed("backup role differs from the runtime role")
    if values.get("PGUSER") in ("postgres", "root"):
        report.failed("backup role must not be a superuser account", values["PGUSER"])
    pf = values.get("BACKUP_PASSPHRASE_FILE")
    if pf:
        try:
            pm = stat.S_IMODE(os.stat(pf).st_mode)
            size = os.path.getsize(pf)
            report.passed("passphrase file is mode 0600", oct(pm)) if pm == 0o600 else report.failed("passphrase file must be mode 0600", oct(pm))
            report.passed("passphrase file holds at least 20 characters") if size >= 20 else report.failed("passphrase file is shorter than 20 characters")
            inside = [d for d in (values.get("BACKUP_DIR"), env.get("DJANGO_PRIVATE_MEDIA_ROOT")) if d and os.path.realpath(pf).startswith(os.path.realpath(d) + os.sep)]
            report.passed("passphrase file lies outside the backup directory and the document store") if not inside else report.failed("passphrase file lies inside the backup directory or the document store")
        except OSError:
            report.failed("passphrase file readable", "cannot stat it")
    bd = values.get("BACKUP_DIR")
    if bd and os.path.isdir(bd):
        bm = stat.S_IMODE(os.stat(bd).st_mode)
        report.passed("backup directory is private", oct(bm)) if not bm & 0o077 else report.failed("backup directory must be 0700", oct(bm))
    elif bd:
        report.failed("backup directory exists", bd)
    pg = values.get("PGPASSFILE")
    if pg:
        try:
            gm = stat.S_IMODE(os.stat(pg).st_mode)
            report.passed("PGPASSFILE is mode 0600", oct(gm)) if gm == 0o600 else report.failed("PGPASSFILE must be mode 0600", oct(gm))
        except OSError:
            report.failed("PGPASSFILE readable", "cannot stat it")
    # does the role really have what the restore check needs? (only when psql is installed and the role can connect)
    probe_env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}   # ambient PG* settings must not leak in: test the role AS CONFIGURED in backup.env
    probe_env.update({k: v for k, v in values.items() if k.startswith("PG")}, PGDATABASE="postgres")
    probe_env.setdefault("PGHOST", env.get("DB_HOST", ""))
    try:
        r = subprocess.run(["psql", "-Atc", "select rolcreatedb, rolsuper, rolcreaterole from pg_roles where rolname = current_user"], env=probe_env, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        report.skipped("backup role rights (CREATEDB, not superuser)", "psql not installed here")
        return
    if r.returncode != 0:
        report.failed("backup role can connect", "psql could not connect with the PG* settings of backup.env: " + (r.stderr.strip().splitlines() or [""])[-1][:120])
    else:
        createdb, superuser, createrole = (r.stdout.strip().split("|") + ["", "", ""])[:3]
        report.passed("backup role has CREATEDB (needed by the restore check) and is not a superuser") if createdb == "t" and superuser == "f" and createrole == "f" else report.failed("backup role rights wrong", f"createdb={createdb} superuser={superuser} createrole={createrole}")


def check_tools(backend, report, skip=False):
    if skip:
        report.skipped("nginx / systemd-analyze", "skipped by --skip-tools (rehearsal without those tools)")
    else:
        _run_tools(backend, report)
    report.skipped("SMTP delivery", "operator: send one test message to a mailbox you control and look at it")
    report.skipped("real TLS certificate and chain", "operator: open the staging address in a browser and run the post-deploy list (§4.16)")
    report.skipped("firewall and DNS", "operator-owned; not checked here")


def _run_tools(backend, report):
    def run(cmd, name, ok_codes=(0,)):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            report.skipped(name, f"{cmd[0]} not installed here")
            return
        report.passed(name) if r.returncode in ok_codes else report.failed(name, (r.stderr or r.stdout).strip().splitlines()[-1][:160] if (r.stderr or r.stdout).strip() else f"rc={r.returncode}")
    run(["nginx", "-t"], "nginx configuration test")
    for unit in ("talim-gunicorn.service", "talim-job@.service"):
        path = os.path.join(backend, "deploy", "systemd", unit)
        if os.path.exists(path):
            run(["systemd-analyze", "verify", path], f"systemd-analyze verify {unit}")


def check_django(backend, env, report):
    base = dict(os.environ, **env, PYTHONPATH=backend)
    py = os.path.join(backend, ".venv", "bin", "python")
    py = py if os.path.exists(py) else sys.executable

    def manage(*args):
        return subprocess.run([py, "manage.py", *args], cwd=backend, env=base, capture_output=True, text=True, timeout=300)
    r = manage("check", "--deploy")
    warnings = re.findall(r"\((security\.W\d+)\)", r.stdout + r.stderr)
    unexpected = [w for w in warnings if w != "security.W004"]  # W004 (HSTS) is a documented, deliberate warning until real HTTPS is verified
    if r.returncode == 0 and not unexpected and "ERROR" not in r.stderr:
        report.passed("check --deploy (only the documented HSTS warning allowed)", "W004 present" if warnings else "")
    else:
        report.failed("check --deploy", ", ".join(unexpected) or f"rc={r.returncode}")
    r = manage("makemigrations", "--check", "--dry-run")
    report.passed("no model changes without a migration") if r.returncode == 0 else report.failed("makemigrations --check")
    r = manage("shell", "-c", (
        "from django.db import connection as c\n"
        "cur=c.cursor()\n"
        "cur.execute(\"select rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname=current_user\")\n"
        "su,cd,cr=cur.fetchone()\n"
        "cur.execute(\"select has_table_privilege('audit_auditlog','UPDATE') or has_table_privilege('audit_auditlog','DELETE') or has_table_privilege('audit_auditlog','TRUNCATE')\")\n"
        "w=cur.fetchone()[0]\n"
        "cur.execute(\"select has_schema_privilege('public','CREATE')\")\n"
        "ddl=cur.fetchone()[0]\n"
        "print('DBROLE', 'super' if su else 'ok', 'createdb' if cd else 'ok', 'createrole' if cr else 'ok', 'auditwrite' if w else 'ok', 'ddl' if ddl else 'ok')\n"))
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("DBROLE")]
    if not line:
        report.failed("database role inspection", "could not connect with the runtime role")
    else:
        parts = line[-1].split()[1:]
        report.passed("runtime DB role: no superuser/createdb/createrole") if parts[:3] == ["ok", "ok", "ok"] else report.failed("runtime DB role is too powerful", " ".join(parts[:3]))
        report.passed("runtime DB role cannot rewrite the audit log") if parts[3] == "ok" else report.failed("runtime DB role can UPDATE/DELETE/TRUNCATE audit_auditlog (run deploy/postgres/apply_grants.sql)")
        report.passed("runtime DB role cannot create objects in schema public") if parts[4] == "ok" else report.failed("runtime DB role can create objects in schema public (apply_grants.sql)")
    r = manage("check_scanner")
    report.passed("scanner (ClamAV) answers") if r.returncode == 0 else report.failed("scanner (ClamAV) does not answer", "documents stay quarantined (fail-closed) - fix before use")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="/etc/talim/talim.env")
    ap.add_argument("--backend", default="/srv/talim/backend")
    ap.add_argument("--skip-tools", action="store_true", help="do not call nginx/systemd-analyze (they are listed as SKIP)")
    ap.add_argument("--backup-env", default=None, help="also audit the backup/restore environment file (e.g. /etc/talim/backup.env)")
    ap.add_argument("--no-django", action="store_true", help="skip the checks that start Django and connect to the database")
    a = ap.parse_args(argv)
    report = Report()
    try:
        env = parse_env(open(a.env_file).read())
    except OSError:
        print("FAIL environment file cannot be read")
        return 1
    check_env_values(env, report)
    check_files(a.env_file, env, report)
    if a.backup_env:
        check_backup_env(a.backup_env, env, report)
    check_tools(a.backend, report, a.skip_tools)
    if not a.no_django:
        check_django(a.backend, env, report)
    for status, name, detail in report.rows:
        print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    n = {s: sum(1 for r in report.rows if r[0] == s) for s in ("PASS", "FAIL", "SKIP")}
    print(f"PREFLIGHT {'OK' if report.ok else 'FAILED'}: {n['PASS']} pass, {n['FAIL']} fail, {n['SKIP']} skipped (skipped = operator must check)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
