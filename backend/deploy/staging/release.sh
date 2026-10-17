#!/usr/bin/env bash
# Release switch with automatic return to the previous release. Run as the application user (NOT root) on the staging/production host.
#   release.sh deploy <release-name>   state saved -> migrations -> static -> switch symlink -> restart -> health check -> (on failure) back
#   release.sh rollback                switch the symlink back to the previous release, restart, health check
#   release.sh status
# Layout:  $RELEASES_DIR/<name>/ = one full checkout of the repository (backend/ with its own virtualenv at backend/.venv, and assets/ which the
#          backend serves as static files)     $CURRENT_LINK (e.g. /srv/talim/backend) -> $RELEASES_DIR/<name>/backend
# Environment (names only; values come from the operator / the environment file, nothing is stored here):
#   RELEASES_DIR, CURRENT_LINK            required
#   HEALTH_URL                            required, e.g. the local gunicorn address /healthz/ (the application answers 200 {"status":"ok"} only if the DB works)
#   RESTART_CMD                           required, e.g. "sudo systemctl restart talim-gunicorn" (the operator allows exactly this command in sudoers)
#   PRE_BACKUP_CMD                        required; must exit 0, e.g. "$CURRENT_LINK/deploy/backup/backup.sh" (the CURRENT code, i.e. before the switch). A failed backup stops the release BEFORE anything changes.
#   HEALTH_WAIT_SECONDS=60  MIGRATE_CMD_PREFIX=""  (e.g. "env DB_USER=<owner role>" so migrations run with the owner role, not the runtime role)
#   POST_MIGRATE_SQL_CMD                  optional, e.g. a command that applies deploy/postgres/apply_grants.sql after migrate
# What it does NOT do: it never reverts migrations and never restores the database by itself. If the new release applied migrations and
# then failed, the symlink goes back but the database keeps the new schema; the old code may or may not work with it. The output says so.
# Restoring the database from the state saved at the start is a deliberate, separate decision (docs/DEPLOYMENT_READINESS.md §4.15).
# Exit codes: 0 done; 1 release failed and the previous release is serving again; 2 misconfiguration or refused before any change;
#             3 release failed AND the previous release does not answer either (needs an operator NOW).
set -uo pipefail
umask 027
: "${RELEASES_DIR:?}" "${CURRENT_LINK:?}" "${HEALTH_URL:?}" "${RESTART_CMD:?}" "${PRE_BACKUP_CMD:?}"
WAIT=${HEALTH_WAIT_SECONDS:-60}
die() { echo "release: $1" >&2; exit "${2:-2}"; }
[ "$(id -u)" -ne 0 ] || die "refusing to run as root"
cur_name() { [ -L "$CURRENT_LINK" ] && basename "$(dirname "$(readlink "$CURRENT_LINK")")" || true; }
switch_to() { ln -sfn "$RELEASES_DIR/$1/backend" "$CURRENT_LINK.new" && mv -T "$CURRENT_LINK.new" "$CURRENT_LINK"; }
healthy() {  # 0 when the application answers 200 with status ok before the deadline
  local end=$((SECONDS + WAIT)) body
  while [ $SECONDS -lt $end ]; do
    body="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null)" && case "$body" in *'"status": "ok"'*|*'"status":"ok"'*) return 0;; esac
    sleep 1
  done
  return 1
}
restart_and_check() { bash -c "$RESTART_CMD" >/dev/null 2>&1 || return 1; healthy; }

cmd=${1:-}; shift || true
case "$cmd" in
status) echo "current=$(cur_name) previous=$(cat "$RELEASES_DIR/.previous" 2>/dev/null || echo -)"; healthy && echo "health=ok" || { echo "health=FAILED"; exit 1; } ;;
rollback)
  prev="$(cat "$RELEASES_DIR/.previous" 2>/dev/null)" || die "no previous release recorded"
  [ -d "$RELEASES_DIR/$prev" ] || die "previous release directory is gone"
  now="$(cur_name)"; switch_to "$prev"; echo "$now" > "$RELEASES_DIR/.previous"
  restart_and_check && { echo "ROLLBACK_OK now=$prev"; exit 0; } || { echo "ROLLBACK_FAILED: $prev does not answer" >&2; exit 3; } ;;
deploy)
  new=${1:?release name}; [[ "$new" =~ ^[A-Za-z0-9._-]+$ ]] || die "bad release name"
  top="$RELEASES_DIR/$new"; rel="$top/backend"; [ -f "$rel/manage.py" ] || die "no backend/manage.py in $top"
  [ -d "$top/assets" ] || die "no assets/ in $top (the whole repository checkout is one release: the static pages are served from it)"
  PY="$rel/.venv/bin/python"; [ -x "$PY" ] || die "no virtualenv python at $rel/.venv"
  old="$(cur_name)"; [ "$old" != "$new" ] || die "release $new is already current"
  echo "1/6 saving state (backup) ..."; bash -c "$PRE_BACKUP_CMD" || die "backup failed - nothing was changed"
  echo "2/6 migration plan ..."; (cd "$rel" && $PY manage.py migrate --plan | tail -n 5) || die "cannot read the migration plan - nothing was changed"
  echo "3/6 migrate ..."
  if ! (cd "$rel" && ${MIGRATE_CMD_PREFIX:-} $PY manage.py migrate --noinput); then
    echo "release: migrate FAILED; the old release keeps serving (a partly applied migration may need the restore decision)" >&2; exit 1
  fi
  if [ -n "${POST_MIGRATE_SQL_CMD:-}" ]; then bash -c "$POST_MIGRATE_SQL_CMD" || { echo "release: post-migrate step failed" >&2; exit 1; }; fi
  echo "4/6 static ..."; (cd "$rel" && $PY manage.py collectstatic --noinput -v0) || { echo "release: collectstatic failed" >&2; exit 1; }
  echo "5/6 switching to $new ..."; prev_before="$(cat "$RELEASES_DIR/.previous" 2>/dev/null || true)"; echo "$old" > "$RELEASES_DIR/.previous"; switch_to "$new"
  echo "6/6 restart and health check ..."
  if restart_and_check; then echo "RELEASE_OK current=$new previous=${old:--}"; exit 0; fi
  echo "release: $new FAILED the health check - returning to ${old:--}" >&2
  [ -n "$old" ] || die "no previous release to return to" 3
  switch_to "$old"; echo "$prev_before" > "$RELEASES_DIR/.previous"  # the failed release never counts as a release to return to
  if restart_and_check; then
    echo "RELEASE_FAILED_ROLLED_BACK serving=$old. NOTE: migrations of $new were applied and NOT reverted; if $old misbehaves, restore the database from the backup taken at step 1 (decision for the operator)." >&2; exit 1
  fi
  echo "RELEASE_FAILED_AND_PREVIOUS_DOES_NOT_ANSWER - operator action required (database restore / investigation)" >&2; exit 3 ;;
*) die "usage: release.sh deploy <name> | rollback | status" ;;
esac
