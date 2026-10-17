#!/usr/bin/env bash
# Restore a backup into a SCRATCH database and a SCRATCH directory and verify it end to end. NEVER touches the live database or files.
#   restore_check.sh <backup-dir>
# Required environment: BACKUP_PASSPHRASE_FILE, PGHOST/PGPORT/PGUSER (+ PGPASSFILE or PGPASSWORD; the role must be allowed to create
#   databases), BACKEND_DIR (path of backend/), PYTHON (interpreter with the project requirements).
# Optional: RESTORE_DB (default talim_restore_check), RESTORE_FILES (default a new temporary directory, must be empty),
#   DJANGO_SETTINGS_MODULE (default config.settings.dev), KEEP=1 to keep the scratch copy for inspection.
#
# Steps: manifest -> decrypt (streamed, no plaintext on disk) -> pg_restore into the scratch DB -> files into the scratch directory ->
# migrate (pending migrations are applied to the scratch copy) -> every file referenced by a row exists with the recorded size and SHA-256 (+ orphan count) -> the existing download
# view, permissions included, serves the restored documents (anonymous refused, authorised people get byte-identical content).
# Exit codes: 0 restore verified; 1 any step failed (wrong passphrase, damaged archive, inconsistent data ...); 2 misconfiguration;
# 75 another restore check is running. stdout ends with RESTORE_OK name=<dir> ... on success. The scratch copy is removed on exit.
set -euo pipefail
umask 077
SRC="${1:?usage: restore_check.sh <backup-dir>}"
: "${BACKUP_PASSPHRASE_FILE:?BACKUP_PASSPHRASE_FILE is not set}" "${BACKEND_DIR:?BACKEND_DIR is not set}" "${PYTHON:?PYTHON is not set}"
die_config() { echo "configuration error: $1" >&2; exit 2; }
[ -d "$SRC" ] || die_config "backup directory not found"
[ -r "$BACKUP_PASSPHRASE_FILE" ] || die_config "passphrase file not readable"
[ "$(stat -c %a "$BACKUP_PASSPHRASE_FILE")" = "600" ] || die_config "passphrase file must have mode 600"
RESTORE_DB="${RESTORE_DB:-talim_restore_check}"
[ "$RESTORE_DB" != "${PGDATABASE:-}" ] && [ "$RESTORE_DB" != "${DB_NAME:-}" ] || die_config "RESTORE_DB equals the live database"
case "$RESTORE_DB" in talim_restore*|*_restore_*|*scratch*|*check*) ;; *) die_config "RESTORE_DB name must contain 'restore', 'scratch' or 'check'";; esac
RESTORE_FILES="${RESTORE_FILES:-$(mktemp -d "${TMPDIR:-/tmp}/talim-restore-files-XXXXXX")}"
[ -z "$(ls -A "$RESTORE_FILES" 2>/dev/null)" ] || die_config "RESTORE_FILES must be empty"

exec 9> "$(dirname "$(realpath "$SRC")")/.restore.lock"
flock -n 9 || { echo "RESTORE_SKIPPED_BUSY: another restore check is running"; exit 75; }

cleanup() { rc=$?; if [ "${KEEP:-0}" != 1 ]; then dropdb --if-exists "$RESTORE_DB" 2>/dev/null || true; rm -rf -- "$RESTORE_FILES"; fi; [ $rc -eq 0 ] || echo "RESTORE_FAILED (exit $rc)" >&2; }
trap cleanup EXIT
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1"; }

echo "1/6 manifest (integrity of the encrypted files, no passphrase needed)"; ( cd "$SRC" && sha256sum --check --quiet MANIFEST.sha256 )
echo "2/6 scratch database $RESTORE_DB"; dropdb --if-exists "$RESTORE_DB"; createdb "$RESTORE_DB"
echo "3/6 restore database (decrypted on the fly)"; dec "$SRC/db.dump.enc" | pg_restore --no-owner --exit-on-error --dbname "$RESTORE_DB"
echo "4/6 restore files"; dec "$SRC/files.tar.enc" | tar --extract --directory "$RESTORE_FILES"
echo "5/6 application-level checks against the restored copy"
cd "$BACKEND_DIR"
export DB_NAME="$RESTORE_DB" DJANGO_PRIVATE_MEDIA_ROOT="$RESTORE_FILES" DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}" DOCUMENT_SCAN_MODE=disabled RESTORE_CHECK=1
# A backup taken before the latest release lacks the newest migrations: that is normal. They are applied to the SCRATCH copy (what a real
# recovery does), and the number is reported; a migration that fails on restored data fails the check.
pending="$("$PYTHON" manage.py showmigrations --plan | grep -c '^\[ \]' || true)"
echo "migrations pending in the restored copy: $pending"
"$PYTHON" manage.py migrate --noinput > /dev/null
verify_out="$("$PYTHON" manage.py verify_document_files --report-orphans --no-record)"; echo "$verify_out"
access_out="$("$PYTHON" manage.py verify_restored_access)"; echo "$access_out"
echo "6/6 row counts of the restored database (numbers only)"
counts="$(psql -d "$RESTORE_DB" -Atc "select 'users='||(select count(*) from accounts_user)||' documents='||(select count(*) from documents_document)||' versions='||(select count(*) from documents_documentversion)||' task_attachments='||(select count(*) from tasks_taskattachment)||' audit_rows='||(select count(*) from audit_auditlog)")"
echo "$counts"
echo "RESTORE_OK name=$(basename "$SRC") $counts $(echo "$verify_out" | grep -o 'orphans=[0-9]*' | head -1) migrations_applied_after_restore=$pending"
