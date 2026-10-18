#!/usr/bin/env bash
# Consistent, encrypted backup of the PostgreSQL database AND the private document store.
#
# What it guarantees (and what it does not):
#   * the database is dumped FIRST (one consistent snapshot), the files are archived AFTER. Stored files are never overwritten or
#     deleted by the application (random names, "removal" only unlinks), so every file the dump refers to is in the archive; files
#     uploaded in between are merely extra. (If this ever changes, stop the application during backups.)
#   * NOTHING unencrypted ever touches the disk: pg_dump and tar are streamed straight into openssl (AES-256-CBC, PBKDF2 600000
#     iterations, salt). A failure of either side fails the whole run (pipefail).
#   * a backup is written to talim-<stamp>.partial and renamed to talim-<stamp> only when EVERYTHING succeeded (dump readable by
#     pg_restore --list, archive listable, manifest verified). A failed run leaves nothing behind and never counts for retention.
#   * "created and readable" is NOT "restorable": a restore into a scratch database is a separate check (restore_check.sh).
#   * the passphrase file lives outside the backup directory and outside the document store; the application keys
#     (DJANGO_SECRET_KEY, OTP_ENCRYPTION_KEYS), .env files, certificates and database passwords are NEVER part of the backup and
#     must be kept in a separate, equally protected place (docs/BACKUP_AND_RESTORE.md).
#
# Required environment:
#   BACKUP_DIR               where backups go (a directory only the backup user can use; created with mode 700 if missing)
#   BACKUP_PASSPHRASE_FILE   file containing the passphrase (mode 600, at least 20 characters)
#   PRIVATE_MEDIA_ROOT       the private document store (same value the application uses)
#   PGDATABASE (and PGHOST PGPORT PGUSER, PGPASSFILE or PGPASSWORD) for pg_dump
# Optional: BACKUP_KEEP=14  (number of newest COMPLETE backups to keep; nothing else is ever deleted)
#
# Exit codes: 0 ok; 1 a step failed (nothing is kept); 2 misconfiguration (nothing was started); 4 the copy was created and kept but old copies could not be deleted;
#             75 another backup holds the lock (nothing was done; not a failure).
# stdout: progress lines and one final machine-readable line  BACKUP_OK name=<dir> db_bytes=<n> files=<n>  (no paths of secrets, no data).
set -euo pipefail
umask 077
: "${BACKUP_DIR:?BACKUP_DIR is not set}" "${BACKUP_PASSPHRASE_FILE:?BACKUP_PASSPHRASE_FILE is not set}" "${PRIVATE_MEDIA_ROOT:?PRIVATE_MEDIA_ROOT is not set}" "${PGDATABASE:?PGDATABASE is not set}"
die_config() { echo "configuration error: $1" >&2; exit 2; }
[ -r "$BACKUP_PASSPHRASE_FILE" ] || die_config "passphrase file not readable"
[ "$(stat -c %a "$BACKUP_PASSPHRASE_FILE")" = "600" ] || die_config "passphrase file must have mode 600"
[ "$(wc -c < "$BACKUP_PASSPHRASE_FILE")" -ge 20 ] || die_config "passphrase is too short (at least 20 characters)"
[ -d "$PRIVATE_MEDIA_ROOT" ] || die_config "PRIVATE_MEDIA_ROOT does not exist"
mkdir -p -m 700 "$BACKUP_DIR"
real_backup="$(realpath "$BACKUP_DIR")"; real_media="$(realpath "$PRIVATE_MEDIA_ROOT")"; real_pass="$(realpath "$BACKUP_PASSPHRASE_FILE")"
case "$real_backup/" in "$real_media/"*) die_config "BACKUP_DIR must not be inside PRIVATE_MEDIA_ROOT";; esac
case "$real_pass" in "$real_backup/"*|"$real_media/"*) die_config "the passphrase file must not live in the backup directory or the document store";; esac
[ "$(stat -c %a "$real_backup")" = "700" ] || die_config "BACKUP_DIR must have mode 700"

# one backup at a time (cron + manual run, two servers on a shared directory): the second one does nothing
exec 9> "$real_backup/.backup.lock"
flock -n 9 || { echo "BACKUP_SKIPPED_BUSY: another backup is running"; exit 75; }

# Holding the lock means no other run is working in this directory, so any *.partial left here belongs to a run that was killed (SIGKILL, power
# cut, OOM) before it could clean up: remove it, otherwise such leftovers pile up until the disk is full. A partial copy is never offered as a backup.
for stale in "$real_backup"/talim-*.partial; do
  [ -d "$stale" ] || continue
  rm -rf -- "$stale" && echo "removed unfinished copy $(basename "$stale") left by an interrupted run"
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
while [ -e "$real_backup/talim-$STAMP" ] || [ -e "$real_backup/talim-$STAMP.partial" ]; do sleep 1; STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; done
FINAL="$real_backup/talim-$STAMP"; OUT="$FINAL.partial"
# SIGTERM/SIGINT/SIGHUP end the script without running an EXIT trap unless they are turned into an exit: do that so an interrupted run cleans up
trap 'exit 143' TERM; trap 'exit 130' INT; trap 'exit 129' HUP
trap 'rc=$?; [ $rc -eq 0 ] || { rm -rf -- "$OUT"; echo "BACKUP_FAILED (exit $rc): nothing was kept" >&2; }' EXIT
mkdir -m 700 "$OUT"
enc() { openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$BACKUP_PASSPHRASE_FILE" -out "$1"; }
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1"; }

echo "1/4 database"
pg_dump --format=custom --no-owner --no-privileges | enc "$OUT/db.dump.enc"
echo "2/4 files"
tar --create --directory "$PRIVATE_MEDIA_ROOT" --exclude='.env*' --exclude='*.key' --exclude='*.pem' --exclude='*.tmp' --exclude='*.part' --exclude='*.lock' --exclude='*.log' . | enc "$OUT/files.tar.enc"
echo "3/4 readability (this is NOT a restore test)"
dec "$OUT/db.dump.enc" | pg_restore --list > /dev/null
files_n="$(dec "$OUT/files.tar.enc" | tar --list | grep -vc '/$' || true)"
db_bytes="$(stat -c %s "$OUT/db.dump.enc")"
{ printf 'created_utc=%s\nformat=pg_dump custom + tar, AES-256-CBC/PBKDF2 (600000)\nfiles=%s\nreadable_check=ok\nrestore_verified=no (see restore_check.sh)\n' "$STAMP" "$files_n"; } > "$OUT/INFO.txt"
echo "4/4 manifest (hashes of the ENCRYPTED files: integrity can be checked without the passphrase)"
( cd "$OUT" && sha256sum db.dump.enc files.tar.enc INFO.txt > MANIFEST.sha256 && sha256sum --check --quiet MANIFEST.sha256 )
mv -- "$OUT" "$FINAL"
trap - EXIT

# retention: only COMPLETE backups of this naming scheme, newest KEEP are kept; a failed run never reaches this point.
# The newest copy that was PROVEN restorable (marked RESTORE_VERIFIED by restore_check.sh) is never deleted, however old it is: while newer copies are
# only "readable", it is the last copy known to work. A copy that cannot be deleted is counted and reported (exit code 4), never hidden.
keep="${BACKUP_KEEP:-14}"
case "$keep" in ''|*[!0-9]*) keep=14;; esac
[ "$keep" -ge 1 ] || keep=1
newest_verified="$(find "$real_backup" -mindepth 2 -maxdepth 2 -name RESTORE_VERIFIED -printf '%h\n' 2>/dev/null | sort | tail -n 1 || true)"
prune_failed=0
while read -r old; do
  [ -n "$old" ] || continue
  if [ "$old" = "$newest_verified" ]; then echo "kept $(basename "$old") (newest restore-verified copy)"; continue; fi
  if rm -rf -- "$old"; then echo "pruned $(basename "$old")"; else prune_failed=$((prune_failed + 1)); echo "PRUNE_FAILED: could not delete $(basename "$old")" >&2; fi
done < <(find "$real_backup" -mindepth 1 -maxdepth 1 -type d -name 'talim-[0-9]*Z' -not -name '*.partial' | sort | head -n "-$keep")
echo "BACKUP_OK name=talim-$STAMP db_bytes=$db_bytes files=$files_n prune_failed=$prune_failed"
[ "$prune_failed" -eq 0 ] || exit 4
