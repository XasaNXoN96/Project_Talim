#!/usr/bin/env bash
# Consistent, encrypted backup of the PostgreSQL database AND the private document store.
#
# Consistency rule: the database is dumped FIRST, the files are archived AFTER. Stored files are never overwritten or
# deleted by the application (random names, "removal" only unlinks), so every file the dump refers to is guaranteed to be
# in the archive; files uploaded in between are merely extra. (If this ever changes, stop the application during backups.)
#
# Secrets: only the database content and PRIVATE_MEDIA_ROOT are read. .env files, keys and certificates are never part
# of the backup (patterns are also excluded explicitly). Both outputs are encrypted with AES-256 before they are kept.
# The passphrase lives in a file outside the repository and outside the backup location: keep a copy elsewhere (B-7).
#
# Required environment:
#   BACKUP_DIR               where backups go (a directory only the backup user can read)
#   BACKUP_PASSPHRASE_FILE   file containing the encryption passphrase (mode 600)
#   PRIVATE_MEDIA_ROOT       the private document store (same value the application uses)
#   PGHOST PGPORT PGUSER PGDATABASE and PGPASSFILE (or PGPASSWORD) for pg_dump
# Optional: BACKUP_KEEP=14  (number of newest backups to keep; older talim-* directories are deleted)
set -euo pipefail
umask 077
: "${BACKUP_DIR:?}" "${BACKUP_PASSPHRASE_FILE:?}" "${PRIVATE_MEDIA_ROOT:?}" "${PGDATABASE:?}"
[ -r "$BACKUP_PASSPHRASE_FILE" ] || { echo "passphrase file not readable" >&2; exit 2; }
[ "$(stat -c %a "$BACKUP_PASSPHRASE_FILE")" = "600" ] || { echo "passphrase file must have mode 600" >&2; exit 2; }
[ -d "$PRIVATE_MEDIA_ROOT" ] || { echo "PRIVATE_MEDIA_ROOT does not exist" >&2; exit 2; }
case "$(realpath "$BACKUP_DIR")/" in "$(realpath "$PRIVATE_MEDIA_ROOT")/"*) echo "BACKUP_DIR must not be inside PRIVATE_MEDIA_ROOT" >&2; exit 2;; esac

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; OUT="$BACKUP_DIR/talim-$STAMP"; mkdir -p -m 700 "$OUT"
enc() { openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1" -out "$2"; }

# 1. database first
pg_dump --format=custom --no-owner --no-privileges --file "$OUT/db.dump.plain"
enc "$OUT/db.dump.plain" "$OUT/db.dump.enc"; shred -u "$OUT/db.dump.plain" 2>/dev/null || rm -f "$OUT/db.dump.plain"
# 2. files second
tar --create --file "$OUT/files.tar.plain" --directory "$PRIVATE_MEDIA_ROOT" --exclude='.env*' --exclude='*.key' --exclude='*.pem' .
enc "$OUT/files.tar.plain" "$OUT/files.tar.enc"; shred -u "$OUT/files.tar.plain" 2>/dev/null || rm -f "$OUT/files.tar.plain"
# 3. manifest (hashes of the ENCRYPTED files, so integrity can be checked without the passphrase)
( cd "$OUT" && sha256sum db.dump.enc files.tar.enc > MANIFEST.sha256 )
printf 'created_utc=%s\ndatabase=%s\nformat=pg_dump custom + tar, AES-256-CBC/PBKDF2\n' "$STAMP" "$PGDATABASE" > "$OUT/INFO.txt"
echo "backup written to $OUT"

# 4. retention
if [ -n "${BACKUP_KEEP:-14}" ]; then
  ls -1d "$BACKUP_DIR"/talim-2* 2>/dev/null | sort | head -n "-${BACKUP_KEEP:-14}" | while read -r old; do rm -rf -- "$old"; echo "pruned $old"; done
fi
