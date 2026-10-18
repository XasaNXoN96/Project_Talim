#!/usr/bin/env bash
# REHEARSAL of release.sh in the sandbox (application runs with config.settings.production, as on a server): real gunicorn, real PostgreSQL (scratch database), real backup.sh, release.sh run as an unprivileged user.
# Proves the release/rollback LOGIC; does NOT prove anything about a real server (systemd, sudoers, nginx in front, real data volumes).
# Needs: root (to switch to the unprivileged user `nobody`), backend/.venv, a DB role with CREATEDB (from backend/.env), openssl, curl.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../.." && pwd)"; PY="$BACKEND/.venv/bin/python"
[ "$(id -u)" -eq 0 ] || { echo "run as root (it switches to an unprivileged user)"; exit 2; }
RUNAS=${RUNAS:-nobody}; PORT=${PORT:-18002}; DB=talim_release_check
WORK="$(mktemp -d /tmp/talim-rel-XXXXXX)"; chmod 777 "$WORK"
mkdir -p "$WORK/releases" "$WORK/backups" "$WORK/private" "$WORK/static"; chmod 777 "$WORK/releases" "$WORK/backups" "$WORK/private" "$WORK/static"; chmod 700 "$WORK/backups"; chown "$RUNAS" "$WORK/backups"
eval "$(cd "$BACKEND" && "$PY" - <<'PYEOF'
import shlex
from dotenv import dotenv_values
v = dotenv_values(".env")
for k in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
    print(f"export {k}={shlex.quote(v.get(k, ''))}")
PYEOF
)"
export PGPASSWORD="$DB_PASSWORD" PGHOST="${DB_HOST:-localhost}" PGPORT="${DB_PORT:-5432}" PGUSER="$DB_USER"
psql -d postgres -qc "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB" || exit 2
SECRET="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(60))')"
FERNET="$("$PY" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
"$PY" -c 'import secrets;print(secrets.token_urlsafe(30))' > "$WORK/pass"; chmod 600 "$WORK/pass"; chown "$RUNAS" "$WORK/pass"
APPENV=(DB_NAME=$DB DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_HOST="$PGHOST" DB_PORT="$PGPORT" DJANGO_SECRET_KEY="$SECRET" OTP_ENCRYPTION_KEYS="$FERNET"
        DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_ALLOWED_HOSTS=localhost DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost DJANGO_TRUSTED_PROXIES=127.0.0.1 DJANGO_ADMIN_URL=gate-rehearsal/ EMAIL_HOST=127.0.0.1 DEFAULT_FROM_EMAIL=noreply@example.test DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" DOCUMENT_SCAN_MODE=clamav
)
cleanup() { [ -f "$WORK/app.pid" ] && kill "$(cat "$WORK/app.pid")" 2>/dev/null; sleep 0.5; psql -d postgres -qc "DROP DATABASE IF EXISTS $DB" || true; }
trap cleanup EXIT

mkrel() {  # $1 name -> a full copy of backend/ with the shared virtualenv
  mkdir -p "$WORK/releases/$1"; tar --exclude=.venv --exclude=__pycache__ --exclude=.env --exclude=.git --exclude=staticfiles -C "$BACKEND/.." -cf - . | tar -xf - -C "$WORK/releases/$1"
  ln -s "$BACKEND/.venv" "$WORK/releases/$1/backend/.venv"; chmod -R a+rX "$WORK/releases/$1"; chmod -R a+w "$WORK/releases/$1"
}
cat > "$WORK/restart.sh" <<RS
#!/usr/bin/env bash
[ -f "$WORK/app.pid" ] && kill "\$(cat "$WORK/app.pid")" 2>/dev/null; sleep 1; rm -f "$WORK/app.pid"
cd "$WORK/current" || exit 1  # current -> releases/<name>/backend
env ${APPENV[@]@Q} PYTHONPATH="\$PWD" "$BACKEND/.venv/bin/gunicorn" config.wsgi:application --bind 127.0.0.1:$PORT --workers 1 --pid "$WORK/app.pid" --daemon --error-logfile "$WORK/gunicorn.log"
RS
chmod 755 "$WORK/restart.sh"
RELENV=(RELEASES_DIR="$WORK/releases" CURRENT_LINK="$WORK/current" HEALTH_URL="http://127.0.0.1:$PORT/healthz/" HEALTH_HOST=localhost RESTART_CMD="$WORK/restart.sh" HEALTH_WAIT_SECONDS=8
        PRE_BACKUP_CMD="$WORK/backup_now.sh")
cat > "$WORK/backup_now.sh" <<BK
#!/usr/bin/env bash
env BACKUP_DIR="$WORK/backups" BACKUP_PASSPHRASE_FILE="$WORK/pass" PRIVATE_MEDIA_ROOT="$WORK/private" PGDATABASE=$DB PGHOST=$PGHOST PGPORT=$PGPORT PGUSER=$PGUSER PGPASSWORD=$PGPASSWORD "$BACKEND/deploy/backup/backup.sh" >/dev/null
BK
chmod 755 "$WORK/backup_now.sh"
# the unprivileged user runs release.sh with the application environment (migrations also run as that user)
rel() { runuser -u "$RUNAS" -- env "${RELENV[@]}" "${APPENV[@]}" PYTHONPATH= "${RELEASE_SH:-$HERE/release.sh}" "$@"; }
serving() { basename "$(dirname "$(readlink "/proc/$(cat "$WORK/app.pid" 2>/dev/null || echo 0)/cwd" 2>/dev/null)")"; }
FAIL=0; N=0
ok() { N=$((N+1)); if [ "$2" = 0 ]; then echo "  [PASS] $1"; else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi; }
is() { [ "$1" = "$2" ]; echo $?; }

mkrel r1; mkrel r2; mkrel r3; mkrel r4
# r3: a harmless new migration + an application that cannot start. r4: a migration that raises.
LAST="$(ls "$BACKEND/apps/core/migrations" | grep -E '^[0-9]{4}_' | sort | tail -1 | sed 's/\.py$//')"
cat > "$WORK/releases/r3/backend/apps/core/migrations/9998_harmless.py" <<MG
from django.db import migrations
class Migration(migrations.Migration):
    dependencies = [("core", "$LAST")]
    operations = [migrations.RunSQL("SELECT 1", migrations.RunSQL.noop)]
MG
echo 'raise RuntimeError("this release cannot start")' >> "$WORK/releases/r3/backend/config/wsgi.py"
cat > "$WORK/releases/r4/backend/apps/core/migrations/9999_boom.py" <<MG
from django.db import migrations
def boom(apps, schema_editor):
    raise RuntimeError("migration failure on purpose")
class Migration(migrations.Migration):
    dependencies = [("core", "$LAST")]
    operations = [migrations.RunPython(boom, migrations.RunPython.noop)]
MG
chmod -R a+rX "$WORK/releases"

echo "== 1. first release (empty server)"
rel deploy r1 >"$WORK/o1" 2>&1; rc=$?; ok "r1 deployed (rc=$rc)" "$rc"; ok "r1 is serving" "$(is "$(serving)" r1)"
ok "a backup was taken before the change" "$([ -n "$(ls "$WORK/backups" 2>/dev/null | grep '^talim-')" ] && echo 0 || echo 1)"
echo "== 2. normal update"
rel deploy r2 >"$WORK/o2" 2>&1; rc=$?; ok "r2 deployed (rc=$rc)" "$rc"; ok "r2 is serving" "$(is "$(serving)" r2)"; ok "previous is recorded as r1" "$(is "$(cat "$WORK/releases/.previous")" r1)"
ok "static files of the new release can be read by the web server (world-readable, directories traversable)" "$(n=$(find "$WORK/releases/r2/backend/staticfiles" \( -type f ! -perm -o=r \) -o \( -type d ! -perm -o=rx \) 2>/dev/null | wc -l); [ "$n" = 0 ] && [ -d "$WORK/releases/r2/backend/staticfiles" ] && echo 0 || echo 1)"
echo "== 3. release that migrates and then cannot start -> automatic return"
rel deploy r3 >"$WORK/o3" 2>&1; rc=$?; ok "release reports failure rc=1" "$(is "$rc" 1)"; ok "r2 is serving again" "$(is "$(serving)" r2)"
ok "health answers 200 after the return" "$(curl -fsS -H "Host: localhost" -H "X-Forwarded-Proto: https" "http://127.0.0.1:$PORT/healthz/" >/dev/null 2>&1; echo $?)"
ok "output warns that migrations were NOT reverted" "$(grep -q 'NOT reverted' "$WORK/o3"; echo $?)"
ok "the new migration really stayed applied (honest note)" "$(psql -d $DB -Atc "select count(*) from django_migrations where name='9998_harmless'" | grep -qx 1; echo $?)"
ok "current symlink points to r2" "$(is "$(basename "$(dirname "$(readlink "$WORK/current")")")" r2)"
ok "previous is still r1 after the automatic return (not the failed release)" "$(is "$(cat "$WORK/releases/.previous")" r1)"
echo "== 4. release whose migration fails -> old release keeps serving, symlink untouched"
rel deploy r4 >"$WORK/o4" 2>&1; rc=$?; ok "rc=1" "$(is "$rc" 1)"; ok "r2 still current" "$(is "$(basename "$(dirname "$(readlink "$WORK/current")")")" r2)"; ok "r2 still serving" "$(is "$(serving)" r2)"
echo "== 5. the backup step failing stops everything before any change"
RELENV_SAVE=("${RELENV[@]}"); RELENV=("${RELENV[@]/PRE_BACKUP_CMD=*/PRE_BACKUP_CMD=false}")
mkrel r5; rel deploy r5 >"$WORK/o5" 2>&1; rc=$?; ok "rc=2 (refused)" "$(is "$rc" 2)"; ok "r2 still current" "$(is "$(basename "$(dirname "$(readlink "$WORK/current")")")" r2)"
RELENV=("${RELENV_SAVE[@]}")
echo "== 6. manual rollback to the previous release"
rel rollback >"$WORK/o6" 2>&1; rc=$?; ok "rollback rc=0" "$rc"; ok "r1 is serving" "$(is "$(serving)" r1)"
echo "== 7. refuses to run as root"
env "${RELENV[@]}" "${APPENV[@]}" "$HERE/release.sh" status >/dev/null 2>&1; ok "root is refused" "$(is "$?" 2)"
echo "== 8. NEGATIVE CONTROL: with the health check disabled the broken release is wrongly kept (the checks above would catch it)"
sed 's/^healthy() {/healthy() { return 0; }\nhealthy_unused() {/' "$HERE/release.sh" > "$WORK/release_mutant.sh"; chmod 755 "$WORK/release_mutant.sh"
rel deploy r2 >/dev/null 2>&1   # back to r2 with the real script (r1 -> r2)
RELEASE_SH="$WORK/release_mutant.sh" rel deploy r3 >/dev/null 2>&1
mutant_kept_broken="$([ "$(basename "$(dirname "$(readlink "$WORK/current")")")" = r3 ] && echo 0 || echo 1)"
ok "mutant keeps the broken release (so the real check is what protects us)" "$mutant_kept_broken"
echo "== 9. why the health check sends X-Forwarded-Proto: plain HTTP to production settings is redirected, not served"
rel deploy r2 >/dev/null 2>&1 || true
code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: localhost' "http://127.0.0.1:$PORT/healthz/")"; ok "plain-HTTP request to gunicorn gets a redirect (got $code), so the check must send the header" "$([ "$code" = 301 ] && echo 0 || echo 1)"
echo "RESULT: $((N-FAIL))/$N passed"; [ "$FAIL" = 0 ] && echo "RELEASE REHEARSAL OK (sandbox, scratch database; not a real server)" || { echo "REHEARSAL FAILED"; tail -5 "$WORK"/o* "$WORK/gunicorn.log" 2>/dev/null; exit 1; }
