#!/usr/bin/env bash
# REHEARSAL of preflight.py in the sandbox: scratch database and roles (deploy/postgres), a generated production-shaped environment file, real
# check --deploy, a real clamd answering PING (set CLAMAV_HOST/CLAMAV_PORT if it is not on 127.0.0.1:3310), run as an unprivileged user.
# Proves the CHECKER works (it passes a correct set-up and FAILS on each deliberate mistake). It does not prove a real server is correctly set up.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../.." && pwd)"; PY="$BACKEND/.venv/bin/python"
[ "$(id -u)" -eq 0 ] || { echo "run as root (it switches to an unprivileged user)"; exit 2; }
RUNAS=${RUNAS:-nobody}; cd "$BACKEND"
eval "$("$PY" - <<'PYEOF'
import shlex
from dotenv import dotenv_values
v = dotenv_values(".env")
for k in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
    print(f"export ADMIN_{k}={shlex.quote(v.get(k, ''))}")
PYEOF
)"
export PGPASSWORD="$ADMIN_DB_PASSWORD" PGHOST="${ADMIN_DB_HOST:-localhost}" PGPORT="${ADMIN_DB_PORT:-5432}" PGUSER="$ADMIN_DB_USER"
ADMIN_PSQL="runuser -u postgres -- env -u PGUSER -u PGPASSWORD -u PGHOST -u PGPORT psql"
SUFFIX="$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"; DB="talim_pre_$SUFFIX"; OWNER="talim_pre_owner_$SUFFIX"; APP="talim_pre_app_$SUFFIX"
OWNER_PW="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(24))')"; APP_PW="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(24))')"
WORK="$(mktemp -d /tmp/talim-pre-XXXXXX)"; chmod 755 "$WORK"; mkdir "$WORK/private"; chown "$RUNAS" "$WORK/private"; chmod 700 "$WORK/private"
# a copy of the code without the developer .env (an unprivileged user must not need it, and cannot read it)
mkdir -p "$WORK/code"; tar --exclude=.venv --exclude=__pycache__ --exclude=.env --exclude=.git -C "$BACKEND/.." -cf - . | tar -xf - -C "$WORK/code"; ln -s "$BACKEND/.venv" "$WORK/code/backend/.venv"; chmod -R a+rX "$WORK/code"
cleanup() { $ADMIN_PSQL -d postgres -qc "DROP DATABASE IF EXISTS \"$DB\"" -c "DROP ROLE IF EXISTS \"$BK\"" -c "DROP ROLE IF EXISTS \"$NOCD\"" -c "DROP ROLE IF EXISTS \"$APP\"" -c "DROP ROLE IF EXISTS \"$OWNER\"" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
$ADMIN_PSQL -d postgres -qv ON_ERROR_STOP=1 -v owner="$OWNER" -v app="$APP" -v db="$DB" -v owner_password="$OWNER_PW" -v app_password="$APP_PW" -f "$BACKEND/deploy/postgres/create_roles.sql" || exit 2
BASE=(DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 DB_NAME="$DB" DB_HOST="$PGHOST" DB_PORT="$PGPORT" DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" DOCUMENT_SCAN_MODE=disabled DJANGO_ALLOWED_HOSTS=testserver PYTHONPATH=)
env "${BASE[@]}" DB_USER="$OWNER" DB_PASSWORD="$OWNER_PW" "$PY" manage.py migrate -v0 || exit 2
PGPASSWORD="$OWNER_PW" PGUSER="$OWNER" psql -d "$DB" -qv ON_ERROR_STOP=1 -v app="$APP" -v db="$DB" -f "$BACKEND/deploy/postgres/apply_grants.sql" >/dev/null || exit 2
# the third (backup/restore) role, a role WITHOUT CREATEDB, passphrase and pgpass files, backup directory: owned by the unprivileged user
BK="talim_pre_backup_$SUFFIX"; NOCD="talim_pre_nocd_$SUFFIX"; BK_PW="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(24))')"
$ADMIN_PSQL -d postgres -qv ON_ERROR_STOP=1 -v backup_role="$BK" -v backup_password="$BK_PW" -f "$BACKEND/deploy/postgres/create_backup_role.sql" || exit 2
$ADMIN_PSQL -d postgres -qc "CREATE ROLE \"$NOCD\" LOGIN PASSWORD '$BK_PW' NOSUPERUSER NOCREATEDB" || exit 2
mkdir "$WORK/backups"; chown "$RUNAS" "$WORK/backups"; chmod 700 "$WORK/backups"
"$PY" -c 'import secrets;print(secrets.token_urlsafe(40))' > "$WORK/backup.pass"; chmod 600 "$WORK/backup.pass"; chown "$RUNAS" "$WORK/backup.pass"
printf '127.0.0.1:5432:*:%s:%s\n127.0.0.1:5432:*:%s:%s\n' "$BK" "$BK_PW" "$NOCD" "$BK_PW" > "$WORK/backup.pgpass"; chmod 600 "$WORK/backup.pgpass"; chown "$RUNAS" "$WORK/backup.pgpass"
SECRET="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(70))')"; FERNET="$("$PY" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
mkenv() {  # $1 = file, rest = overrides KEY=VALUE
  local f=$1; shift
  { echo "DJANGO_SETTINGS_MODULE=config.settings.production"; echo "DJANGO_DEBUG=0"; echo "DJANGO_SECRET_KEY=$SECRET"; echo "DJANGO_ALLOWED_HOSTS=staging.invalid"
    echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://staging.invalid"; echo "DJANGO_ADMIN_URL=gate-$SUFFIX-rehearsal/"; echo "DJANGO_TRUSTED_PROXIES=127.0.0.1"
    echo "DJANGO_PRIVATE_MEDIA_ROOT=$WORK/private"; echo "DJANGO_HSTS_SECONDS=0"; echo "DB_NAME=$DB"; echo "DB_USER=$APP"; echo "DB_PASSWORD=$APP_PW"
    echo "DB_HOST=$PGHOST"; echo "DB_PORT=$PGPORT"; echo "OTP_ENCRYPTION_KEYS=$FERNET"; echo "DOCUMENT_SCAN_MODE=clamav"; echo "EMAIL_HOST=smtp.staging.invalid"
    echo "DEFAULT_FROM_EMAIL=noreply@staging.invalid"; } > "$f.base"
  python3 - "$f.base" "$f" "$@" <<'PYEOF'
import sys
src, dst, *over = sys.argv[1:]
d = dict(l.rstrip("\n").split("=", 1) for l in open(src))
for o in over:
    k, _, v = o.partition("=")
    if v == "__DROP__": d.pop(k, None)
    else: d[k] = v
open(dst, "w").write("".join(f"{k}={v}\n" for k, v in d.items()))
PYEOF
  rm -f "$f.base"; chown root:"$(id -gn "$RUNAS")" "$f"; chmod 640 "$f"
}
run_pre() { runuser -u "$RUNAS" -- env PATH="$PATH" "$PY" "$HERE/preflight.py" --env-file "$1" --backend "$WORK/code/backend" --skip-tools; }
FAIL=0; N=0
expect() {  # $1 label, $2 expected rc, $3 env file, $4 text that must appear in the output ('' = none)
  out="$(run_pre "$3" 2>&1)"; rc=$?; N=$((N+1))
  if [ "$rc" = "$2" ] && { [ -z "$4" ] || echo "$out" | grep -q -- "$4"; }; then echo "  [PASS] $1 (rc=$rc)"; else echo "  [FAIL] $1 (rc=$rc, expected $2)"; echo "$out" | grep -E "FAIL|PREFLIGHT" | head -5; FAIL=$((FAIL+1)); fi
}
echo "== correct set-up"
mkenv "$WORK/good.env"; expect "a correct set-up passes" 0 "$WORK/good.env" "PREFLIGHT OK"
out="$(run_pre "$WORK/good.env" 2>&1)"; N=$((N+1)); if echo "$out" | grep -q -e "$SECRET" -e "$APP_PW" -e "$FERNET"; then echo "  [FAIL] a secret value was printed"; FAIL=$((FAIL+1)); else echo "  [PASS] no secret value is printed"; fi
echo "== each deliberate mistake must FAIL"
mkenv "$WORK/e1.env" DJANGO_DEBUG=1;                          expect "DEBUG on" 1 "$WORK/e1.env" "DEBUG"
mkenv "$WORK/e2.env" DJANGO_ALLOWED_HOSTS='*';                expect "wildcard ALLOWED_HOSTS" 1 "$WORK/e2.env" "wildcard"
mkenv "$WORK/e3.env" DJANGO_SECRET_KEY=CHANGE_ME_x;           expect "placeholder secret" 1 "$WORK/e3.env" "placeholder"
mkenv "$WORK/e4.env" DOCUMENT_SCAN_MODE=disabled;             expect "scanner not fail-closed" 1 "$WORK/e4.env" "fail-closed"
mkenv "$WORK/e5.env" DJANGO_CSP_REPORT_ONLY=1;                expect "CSP report-only" 1 "$WORK/e5.env" "CSP"
mkenv "$WORK/e6.env" DJANGO_CSRF_TRUSTED_ORIGINS=http://staging.invalid; expect "CSRF origin over http" 1 "$WORK/e6.env" "https"
mkenv "$WORK/e7.env" OTP_ENCRYPTION_KEYS=not-a-key;           expect "bad OTP key" 1 "$WORK/e7.env" "Fernet"
mkenv "$WORK/e8.env" DB_USER="$OWNER" DB_PASSWORD="$OWNER_PW"; expect "runtime role is the owner role" 1 "$WORK/e8.env" "audit"
mkenv "$WORK/e9.env" EMAIL_HOST=__DROP__;                     expect "missing variable" 1 "$WORK/e9.env" "missing"
mkenv "$WORK/e10.env"; chmod 644 "$WORK/e10.env";             expect "world-readable environment file" 1 "$WORK/e10.env" "world"
mkenv "$WORK/e11.env"; chown "$RUNAS" "$WORK/e11.env";        expect "environment file owned by the app user" 1 "$WORK/e11.env" "owned by"
chmod 755 "$WORK/private"; mkenv "$WORK/e12.env";             expect "document store open to others" 1 "$WORK/e12.env" "accessible to others"; chmod 700 "$WORK/private"
mkbk() {  # $1 = file, rest = overrides KEY=VALUE for backup.env
  local f=$1; shift
  python3 - "$f" "BACKUP_DIR=$WORK/backups" "BACKUP_PASSPHRASE_FILE=$WORK/backup.pass" "PGUSER=$BK" "PGHOST=127.0.0.1" "PGPORT=5432" "PGPASSFILE=$WORK/backup.pgpass" "$@" <<'PYEOF'
import sys
dst, *over = sys.argv[1:]
d = {}
for o in over:
    k, _, v = o.partition("=")
    if v == "__DROP__": d.pop(k, None)
    else: d[k] = v
open(dst, "w").write("".join(f"{k}={v}\n" for k, v in d.items()))
PYEOF
  chown root:"$(id -gn "$RUNAS")" "$f"; chmod 640 "$f"
}
run_pre_bk() { runuser -u "$RUNAS" -- env PATH="$PATH" "$PY" "$HERE/preflight.py" --env-file "$1" --backup-env "$2" --backend "$WORK/code/backend" --skip-tools; }
expect_bk() {  # label, expected rc, backup env file, text
  out="$(run_pre_bk "$WORK/good.env" "$3" 2>&1)"; rc=$?; N=$((N+1))
  if [ "$rc" = "$2" ] && { [ -z "$4" ] || echo "$out" | grep -q -- "$4"; }; then echo "  [PASS] $1 (rc=$rc)"; else echo "  [FAIL] $1 (rc=$rc, expected $2)"; echo "$out" | tail -6; FAIL=$((FAIL+1)); fi
}
echo "== backup/restore environment (three separate roles)"
mkbk "$WORK/bk_good.env"; expect_bk "a correct backup environment passes, the backup role really has CREATEDB" 0 "$WORK/bk_good.env" "backup role has CREATEDB"
mkbk "$WORK/bk1.env" PGUSER="$APP" ; expect_bk "backup role = runtime role" 1 "$WORK/bk1.env" "must differ"
mkbk "$WORK/bk2.env" PGUSER="$NOCD"; expect_bk "backup role without CREATEDB" 1 "$WORK/bk2.env" "rights wrong"
mkbk "$WORK/bk3.env" PGUSER=postgres; expect_bk "backup role named postgres" 1 "$WORK/bk3.env" "superuser account"
chmod 644 "$WORK/backup.pass"; mkbk "$WORK/bk4.env"; expect_bk "passphrase file mode 0644" 1 "$WORK/bk4.env" "mode 0600"; chmod 600 "$WORK/backup.pass"
cp "$WORK/backup.pass" "$WORK/backups/inside.pass"; chown "$RUNAS" "$WORK/backups/inside.pass"; chmod 600 "$WORK/backups/inside.pass"
mkbk "$WORK/bk5.env" BACKUP_PASSPHRASE_FILE="$WORK/backups/inside.pass"; expect_bk "passphrase file inside the backup directory" 1 "$WORK/bk5.env" "inside the backup directory"
mkbk "$WORK/bk6.env" PGUSER=__DROP__; expect_bk "PGUSER missing" 1 "$WORK/bk6.env" "missing"
chmod 755 "$WORK/backups"; mkbk "$WORK/bk7.env"; expect_bk "backup directory open to others" 1 "$WORK/bk7.env" "0700"; chmod 700 "$WORK/backups"
echo "RESULT: $((N-FAIL))/$N passed"; [ "$FAIL" = 0 ] && echo "PREFLIGHT REHEARSAL OK (sandbox; not a real server)" || { echo "PREFLIGHT REHEARSAL FAILED"; exit 1; }
