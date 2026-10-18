#!/usr/bin/env bash
# REHEARSAL of the real backup topology in the sandbox: THREE separate database roles (owner, runtime app, backup/restore) on a scratch database.
#   backup.sh runs as the backup role; restore_check.sh runs with the backup role for createdb/pg_restore while the environment still carries the RUNTIME
#   role in DB_USER/DB_PASSWORD (as /etc/talim/talim.env does on a server): the application-level checks must use the restore role, not the runtime role.
# Also checks the negative cases: a backup role without CREATEDB fails clearly; restoring onto the live database is refused.
# Needs: root (to talk to the local postgres superuser), backend/.venv, openssl. Not a statement about any real server.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../.." && pwd)"; PY="$BACKEND/.venv/bin/python"
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 2; }
ADMIN_PSQL="runuser -u postgres -- env -u PGUSER -u PGPASSWORD -u PGHOST -u PGPORT psql"
SUF="$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"; DB="talim_bk_live_$SUF"; OWN="talim_bk_owner_$SUF"; APP="talim_bk_app_$SUF"; BK="talim_bk_backup_$SUF"; NOCD="talim_bk_nocreatedb_$SUF"
pw() { "$PY" -c 'import secrets;print(secrets.token_urlsafe(24))'; }
OWN_PW="$(pw)"; APP_PW="$(pw)"; BK_PW="$(pw)"; NOCD_PW="$(pw)"
WORK="$(mktemp -d /tmp/talim-bk-XXXXXX)"; chmod 755 "$WORK"; mkdir "$WORK/media" "$WORK/backups"; chmod 700 "$WORK/backups"
"$PY" -c 'import secrets;print(secrets.token_urlsafe(40))' > "$WORK/pass"; chmod 600 "$WORK/pass"
FERNET="$("$PY" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
RESTORE_DB="talim_restore_check_$SUF"
cleanup() { $ADMIN_PSQL -d postgres -qc "DROP DATABASE IF EXISTS \"$DB\"" -c "DROP DATABASE IF EXISTS \"$RESTORE_DB\"" -c "DROP ROLE IF EXISTS \"$APP\"" -c "DROP ROLE IF EXISTS \"$BK\"" -c "DROP ROLE IF EXISTS \"$NOCD\"" -c "DROP ROLE IF EXISTS \"$OWN\"" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
$ADMIN_PSQL -d postgres -qv ON_ERROR_STOP=1 -v owner="$OWN" -v app="$APP" -v db="$DB" -v owner_password="$OWN_PW" -v app_password="$APP_PW" -f "$BACKEND/deploy/postgres/create_roles.sql" || exit 2
$ADMIN_PSQL -d postgres -qv ON_ERROR_STOP=1 -v backup_role="$BK" -v backup_password="$BK_PW" -f "$BACKEND/deploy/postgres/create_backup_role.sql" || exit 2
$ADMIN_PSQL -d postgres -qc "CREATE ROLE \"$NOCD\" LOGIN PASSWORD '$NOCD_PW' NOSUPERUSER NOCREATEDB; GRANT pg_read_all_data TO \"$NOCD\"" || exit 2
$ADMIN_PSQL -d postgres -qc "GRANT CONNECT ON DATABASE \"$DB\" TO \"$NOCD\"" || exit 2
cd "$BACKEND"
APPENV=(DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 DB_NAME="$DB" DB_HOST=127.0.0.1 DB_PORT=5432 DJANGO_PRIVATE_MEDIA_ROOT="$WORK/media" DOCUMENT_SCAN_MODE=disabled DJANGO_ALLOWED_HOSTS=testserver OTP_ENCRYPTION_KEYS="$FERNET" PYTHONPATH=)
env "${APPENV[@]}" DB_USER="$OWN" DB_PASSWORD="$OWN_PW" "$PY" manage.py migrate -v0 || exit 2
env "${APPENV[@]}" DB_USER="$OWN" DB_PASSWORD="$OWN_PW" "$PY" manage.py seed_roles -v0 || exit 2
PGPASSWORD="$OWN_PW" PGUSER="$OWN" PGHOST=127.0.0.1 psql -d "$DB" -qv ON_ERROR_STOP=1 -v app="$APP" -v db="$DB" -v backup_role="$BK" -f "$BACKEND/deploy/postgres/apply_grants.sql" >/dev/null || exit 2
# fictional data: one user with a confirmed second factor and one document with a stored file (written by the RUNTIME role, as in production)
env "${APPENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" - <<'PYEOF' || exit 2
import django; django.setup()
from django.contrib.auth.models import Group
from apps.access.models import RoleAssignment
from apps.accounts import otp
from apps.accounts.models import User
from apps.documents.models import Document, DocumentCategory
from apps.documents.services import add_version
from apps.documents.testing import upload
from apps.documents.validation import validate_upload
u = User.objects.create_user("bk_hr", "bk_hr@example.test", "Sinov-Parol-13579-x")
RoleAssignment.objects.create(user=u, role=Group.objects.get(name="hr"), scope="all")
d = otp.get_or_create_pending_device(u); otp.confirm_device(d)
cat = DocumentCategory.objects.create(name="Sinov turkumi", is_active=True)
doc = Document.objects.create(title="Sinov hujjati", category=cat, created_by=u, access_level="general")
add_version(doc, validate_upload(upload("a.pdf")), actor=u)
print("fictional data written by the runtime role")
PYEOF
FAIL=0; N=0
ok() { N=$((N+1)); if [ "$2" = 0 ]; then echo "  [PASS] $1"; else echo "  [FAIL] $1"; FAIL=$((FAIL+1)); fi; }
BKENV=(BACKUP_DIR="$WORK/backups" BACKUP_PASSPHRASE_FILE="$WORK/pass" PRIVATE_MEDIA_ROOT="$WORK/media" PGDATABASE="$DB" PGHOST=127.0.0.1 PGPORT=5432)
env "${BKENV[@]}" PGUSER="$BK" PGPASSWORD="$BK_PW" "$HERE/backup.sh" > "$WORK/backup.out" 2>&1; ok "backup.sh runs as the backup role (not the owner, not the runtime role)" "$?"
NAME="$(ls "$WORK/backups" | grep '^talim-' | head -1)"
# what the job process really has: the RUNTIME role in DB_USER/DB_PASSWORD (talim.env) and the BACKUP role in PG* (backup.env)
RESTORE=(env BACKUP_PASSPHRASE_FILE="$WORK/pass" BACKEND_DIR="$BACKEND" PYTHON="$PY" RESTORE_DB="$RESTORE_DB" PGHOST=127.0.0.1 PGPORT=5432 "${APPENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW")
"${RESTORE[@]}" PGUSER="$BK" PGPASSWORD="$BK_PW" "$HERE/restore_check.sh" "$WORK/backups/$NAME" > "$WORK/restore.out" 2>&1; rc=$?
ok "restore_check.sh passes with three separate roles (rc=$rc)" "$rc"
grep -E "RESTORE_OK|RESTORE_FAILED|permission denied|ERROR" "$WORK/restore.out" | head -3 | sed 's/^/        /'
ok "the scratch database is removed afterwards" "$($ADMIN_PSQL -d postgres -Atc "select count(*) from pg_database where datname='$RESTORE_DB'" | grep -qx 0; echo $?)"
"${RESTORE[@]}" PGUSER="$NOCD" PGPASSWORD="$NOCD_PW" "$HERE/restore_check.sh" "$WORK/backups/$NAME" > "$WORK/nocd.out" 2>&1; rc=$?
ok "a backup role WITHOUT CREATEDB fails (rc=$rc) and says why" "$([ "$rc" != 0 ] && grep -qi "permission denied to create database" "$WORK/nocd.out"; echo $?)"
"${RESTORE[@]}" RESTORE_DB="$DB" PGUSER="$BK" PGPASSWORD="$BK_PW" "$HERE/restore_check.sh" "$WORK/backups/$NAME" > "$WORK/live.out" 2>&1; rc=$?
ok "restoring onto the LIVE database name is refused (rc=$rc) before anything is touched" "$([ "$rc" = 2 ] && grep -q "equals the live database" "$WORK/live.out"; echo $?)"
ok "the live database is untouched by all of this" "$(env "${APPENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" -c 'import django;django.setup();from apps.accounts.models import User;print(User.objects.filter(username="bk_hr").count())' | grep -qx 1; echo $?)"
ok "the runtime role still cannot create databases" "$($ADMIN_PSQL -d postgres -Atc "select rolcreatedb from pg_roles where rolname='$APP'" | grep -qx f; echo $?)"
echo "RESULT: $((N-FAIL))/$N passed"; [ "$FAIL" = 0 ] && echo "BACKUP-ROLE REHEARSAL OK (sandbox, scratch roles and databases; not a real server)" || { echo "REHEARSAL FAILED"; tail -5 "$WORK"/restore.out; exit 1; }
