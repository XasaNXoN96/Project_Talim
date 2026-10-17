#!/usr/bin/env bash
# Restore a backup into a SCRATCH database and a SCRATCH directory and verify it. Never touches the live database.
#   restore_check.sh <backup-dir>
# Required environment: BACKUP_PASSPHRASE_FILE, PGHOST/PGPORT/PGUSER (+ PGPASSFILE or PGPASSWORD),
#   BACKEND_DIR (path of backend/), PYTHON (interpreter with the project requirements).
# Optional: RESTORE_DB (default talim_restore_check), RESTORE_FILES (default a new temporary directory), KEEP=1 to keep the result.
set -euo pipefail
umask 077
SRC="${1:?usage: restore_check.sh <backup-dir>}"
: "${BACKUP_PASSPHRASE_FILE:?}" "${BACKEND_DIR:?}" "${PYTHON:?}"
RESTORE_DB="${RESTORE_DB:-talim_restore_check}"
[ "$RESTORE_DB" != "${PGDATABASE:-}" ] || { echo "refusing: RESTORE_DB equals PGDATABASE" >&2; exit 2; }
case "$RESTORE_DB" in talim_restore*|*_restore_*|*scratch*|*check*) ;; *) echo "refusing: RESTORE_DB name must contain 'restore', 'scratch' or 'check'" >&2; exit 2;; esac
RESTORE_FILES="${RESTORE_FILES:-$(mktemp -d /tmp/talim-restore-files-XXXXXX)}"
[ -z "$(ls -A "$RESTORE_FILES" 2>/dev/null)" ] || { echo "RESTORE_FILES must be empty" >&2; exit 2; }
WORK="$(mktemp -d /tmp/talim-restore-work-XXXXXX)"
cleanup() { rm -rf "$WORK"; if [ "${KEEP:-0}" != 1 ]; then dropdb --if-exists "$RESTORE_DB" 2>/dev/null || true; rm -rf "$RESTORE_FILES"; fi; }
trap cleanup EXIT
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1" -out "$2"; }

echo "1/6 manifest (integrity of the encrypted files)"; ( cd "$SRC" && sha256sum --check MANIFEST.sha256 )
echo "2/6 decrypt"; dec "$SRC/db.dump.enc" "$WORK/db.dump"; dec "$SRC/files.tar.enc" "$WORK/files.tar"
echo "3/6 restore database into scratch database $RESTORE_DB"; dropdb --if-exists "$RESTORE_DB"; createdb "$RESTORE_DB"
pg_restore --no-owner --exit-on-error --dbname "$RESTORE_DB" "$WORK/db.dump"
echo "4/6 restore files into $RESTORE_FILES"; tar --extract --file "$WORK/files.tar" --directory "$RESTORE_FILES"
echo "5/6 application-level checks against the restored copy"
cd "$BACKEND_DIR"
export DB_NAME="$RESTORE_DB" DJANGO_PRIVATE_MEDIA_ROOT="$RESTORE_FILES" DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}" DOCUMENT_SCAN_MODE=disabled
"$PYTHON" manage.py migrate --check
"$PYTHON" manage.py verify_document_files
echo "6/6 row counts of the restored database"
psql -d "$RESTORE_DB" -Atc "select 'users='||(select count(*) from accounts_user)||' documents='||(select count(*) from documents_document)||' versions='||(select count(*) from documents_documentversion)||' task_attachments='||(select count(*) from tasks_taskattachment)||' audit_rows='||(select count(*) from audit_auditlog)"
echo "RESTORE CHECK PASSED (scratch copy only)"
