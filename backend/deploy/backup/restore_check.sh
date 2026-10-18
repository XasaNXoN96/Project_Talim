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
# view, permissions included, serves the restored documents (anonymous refused, authorised people get byte-identical content) -> the
# restored two-factor secrets can be decrypted with the OTP_ENCRYPTION_KEYS of this run and their current codes are accepted.
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
[ -z "${RESTORE_FILES:-}" ] || [ -z "$(ls -A "$RESTORE_FILES" 2>/dev/null)" ] || die_config "RESTORE_FILES must be empty"

exec 9> "$(dirname "$(realpath "$SRC")")/.restore.lock"
flock -n 9 || { echo "RESTORE_SKIPPED_BUSY: another restore check is running"; exit 75; }

# Holding the lock: no other restore check uses this backup directory. Restored documents of a check that was KILLED (SIGKILL, power cut) would stay in the
# temporary directory as plaintext; remove such leftovers (older than the 3 hour job limit, so nothing live is touched). Only after the lock, so a busy run
# creates nothing.
find "${TMPDIR:-/tmp}" -maxdepth 1 -type d -name 'talim-restore-files-*' -user "$(id -un)" -mmin +240 -exec rm -rf -- {} + 2>/dev/null || true
RESTORE_FILES="${RESTORE_FILES:-$(mktemp -d "${TMPDIR:-/tmp}/talim-restore-files-XXXXXX")}"

cleanup() { rc=$?; if [ "${KEEP:-0}" != 1 ]; then dropdb --if-exists "$RESTORE_DB" 2>/dev/null || true; rm -rf -- "$RESTORE_FILES"; fi; [ $rc -eq 0 ] || echo "RESTORE_FAILED (exit $rc)" >&2; }
trap cleanup EXIT
trap 'exit 143' TERM; trap 'exit 130' INT; trap 'exit 129' HUP   # run the cleanup on termination too
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1"; }

echo "1/6 manifest (integrity of the encrypted files, no passphrase needed)"
# the manifest must list EXACTLY the three files of a backup (no more, no fewer, no paths): an incomplete or padded manifest would leave an archive unchecked
[ -s "$SRC/MANIFEST.sha256" ] || { echo "manifest is missing or empty" >&2; exit 1; }
listed="$(awk 'NF != 2 || length($1) != 64 { bad = 1 } { print $2 } END { if (bad) print "MALFORMED" }' "$SRC/MANIFEST.sha256" | sort | tr '\n' ' ')"
[ "$listed" = "INFO.txt db.dump.enc files.tar.enc " ] || { echo "manifest does not list exactly db.dump.enc, files.tar.enc and INFO.txt (or is malformed)" >&2; exit 1; }
( cd "$SRC" && sha256sum --check --quiet MANIFEST.sha256 )
echo "2/6 scratch database $RESTORE_DB"; dropdb --if-exists "$RESTORE_DB"; createdb "$RESTORE_DB"
echo "3/6 restore database (decrypted on the fly)"; dec "$SRC/db.dump.enc" | pg_restore --no-owner --exit-on-error --dbname "$RESTORE_DB"
echo "4/6 restore files"; dec "$SRC/files.tar.enc" | tar --extract --no-same-owner --no-same-permissions --directory "$RESTORE_FILES"
echo "5/6 application-level checks against the restored copy"
cd "$BACKEND_DIR"
# The application-level steps run as the RESTORE role (PGUSER: it created the scratch database, owns what pg_restore made, and may migrate it), NOT as
# the runtime role that /etc/talim/talim.env puts in DB_USER: the runtime role has no rights on a scratch database and no DDL. An empty DB_PASSWORD makes
# libpq fall back to PGPASSFILE / PGPASSWORD of the restore role. The live database is never contacted with these settings (DB_NAME is the scratch name).
export DB_USER="${PGUSER:?PGUSER (the restore role) is not set}" DB_PASSWORD="${PGPASSWORD:-}" DB_HOST="${PGHOST:-}" DB_PORT="${PGPORT:-}"
export DB_NAME="$RESTORE_DB" DJANGO_PRIVATE_MEDIA_ROOT="$RESTORE_FILES" DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}" DOCUMENT_SCAN_MODE=disabled RESTORE_CHECK=1
# A backup taken before the latest release lacks the newest migrations: that is normal. They are applied to the SCRATCH copy (what a real
# recovery does), and the number is reported; a migration that fails on restored data fails the check.
pending="$("$PYTHON" manage.py showmigrations --plan | grep -c '^\[ \]' || true)"
echo "migrations pending in the restored copy: $pending"
"$PYTHON" manage.py migrate --noinput > /dev/null
verify_out="$("$PYTHON" manage.py verify_document_files --report-orphans --no-record)"; echo "$verify_out"
access_out="$("$PYTHON" manage.py verify_restored_access)"; echo "$access_out"
# the 2FA secrets are encrypted with OTP_ENCRYPTION_KEYS, which is NOT in the backup: this proves the key configured for THIS run opens them
tf_out="$("$PYTHON" manage.py verify_restored_two_factor)"; echo "$tf_out"
echo "6/6 row counts of the restored database (numbers only)"
counts="$(psql -d "$RESTORE_DB" -Atc "select 'users='||(select count(*) from accounts_user)||' documents='||(select count(*) from documents_document)||' versions='||(select count(*) from documents_documentversion)||' task_attachments='||(select count(*) from tasks_taskattachment)||' audit_rows='||(select count(*) from audit_auditlog)")"
echo "$counts"
if [ "${MARK_VERIFIED:-0}" = 1 ]; then  # the newest copy PROVEN restorable is protected from retention (backup.sh)
  printf 'verified_utc=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" > "$SRC/RESTORE_VERIFIED" 2>/dev/null || echo "warning: could not mark the copy as restore-verified (directory not writable)" >&2
fi
echo "RESTORE_OK name=$(basename "$SRC") $counts $(echo "$verify_out" | grep -o 'orphans=[0-9]*' | head -1) migrations_applied_after_restore=$pending $(echo "$tf_out" | grep -o 'devices=[0-9]*' | sed s/devices=/two_factor_devices=/)"
