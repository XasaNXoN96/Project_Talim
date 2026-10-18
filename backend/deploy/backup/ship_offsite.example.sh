#!/usr/bin/env bash
# EXAMPLE ONLY — not installed, not scheduled, NOT TESTED against a real remote machine (the development sandbox has no rsync/ssh).
# It shows the intended shape of moving the already-ENCRYPTED backups to a second machine; read docs/BACKUP_AND_RESTORE.md §6 first.
#
# Properties it is designed to have:
#   * the local RESTORE_VERIFIED marker is NOT sent: it proves the LOCAL copy restorable, not the remote one (verify the remote copy by restoring it there);
#   * only COMPLETE backups (folders with a manifest; never *.partial) are sent; the passphrase file is never sent;
#   * the remote copy is append-only from this machine's side: --ignore-existing, no --delete, and the SSH key on the remote is restricted
#     (forced command, e.g. rrsync in write-only mode, no shell, no deletion), so a compromised application server cannot erase the history;
#   * integrity is checked ON THE REMOTE after the transfer (sha256sum --check of the manifest), not assumed from rsync's exit code;
#   * host key pinning (StrictHostKeyChecking=yes with a known_hosts file you provisioned), a dedicated key readable only by the backup user.
# Required environment (names/paths only, no secrets in this file): BACKUP_DIR, OFFSITE_TARGET (user@host:/path), OFFSITE_SSH_KEY, OFFSITE_KNOWN_HOSTS.
# Exit codes: 0 all complete backups present and verified remotely; 1 transfer or remote verification failed; 2 misconfiguration.
set -euo pipefail
umask 077
: "${BACKUP_DIR:?}" "${OFFSITE_TARGET:?}" "${OFFSITE_SSH_KEY:?}" "${OFFSITE_KNOWN_HOSTS:?}"
[ "$(stat -c %a "$OFFSITE_SSH_KEY")" = "600" ] || { echo "configuration error: ssh key must have mode 600" >&2; exit 2; }
host="${OFFSITE_TARGET%%:*}"; path="${OFFSITE_TARGET#*:}"
ssh_opts=(-i "$OFFSITE_SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$OFFSITE_KNOWN_HOSTS" -o BatchMode=yes)
for dir in $(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name 'talim-[0-9]*Z' -not -name '*.partial' | sort); do
  [ -f "$dir/MANIFEST.sha256" ] || continue
  name="$(basename "$dir")"
  rsync -a --ignore-existing --exclude=RESTORE_VERIFIED -e "ssh ${ssh_opts[*]}" "$dir" "$OFFSITE_TARGET/"
  ssh "${ssh_opts[@]}" "$host" "cd '$path/$name' && sha256sum --check --quiet MANIFEST.sha256" || { echo "remote verification FAILED for $name" >&2; exit 1; }
  echo "verified remotely: $name"
done
