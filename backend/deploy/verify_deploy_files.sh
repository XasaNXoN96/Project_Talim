#!/usr/bin/env bash
# Static checks of the scheduling files WITHOUT installing anything: builds a throw-away root with the paths the units expect and
# runs systemd-analyze, checks every OnCalendar expression, the crontab syntax, and logrotate's config parser.
# Usage: backend/deploy/verify_deploy_files.sh        (needs systemd-analyze; logrotate is optional)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT
mkdir -p "$root/etc/systemd/system" "$root/etc/talim" "$root/srv/talim/backend/.venv/bin" "$root/usr/bin" "$root/var/backups/talim" "$root/run/talim" "$root/var/log/talim"
cp -r "$here"/systemd/*.service "$here"/systemd/*.timer "$here"/systemd/*.service.d "$root/etc/systemd/system/"
: > "$root/etc/talim/talim.env"; : > "$root/srv/talim/backend/manage.py"
: > "$root/etc/talim/backup.env"
for exe in srv/talim/backend/.venv/bin/python usr/bin/logger; do printf '#!/bin/sh\n' > "$root/$exe"; chmod +x "$root/$exe"; done  # stand-ins: only their existence is checked
for u in sysinit.target basic.target shutdown.target timers.target; do printf "[Unit]\nDescription=stub\n" > "$root/etc/systemd/system/$u"; done
printf "[Unit]\nDescription=stub\n[Service]\nExecStart=/usr/bin/logger\n" > "$root/etc/systemd/system/postgresql.service"  # the system's own units, absent from the throw-away root
id talim >/dev/null 2>&1 || echo "note: user 'talim' does not exist on this machine: systemd-analyze will warn about User=" >&2
echo "== systemd-analyze verify"
# (user "talim" may not exist where this runs: those warnings are filtered, everything else is shown and fails the script)
out="$(systemd-analyze --root="$root" verify "$root"/etc/systemd/system/talim-*.timer "$root"/etc/systemd/system/talim-job@send_task_reminders.service "$root"/etc/systemd/system/talim-job@run_backup.service "$root"/etc/systemd/system/talim-job@run_restore_check.service "$root"/etc/systemd/system/talim-job-failed@x.service 2>&1 | grep -v "talim' \|User=\|Group=\|Failed to resolve user\|Failed to resolve group" || true)"
[ -z "$out" ] && echo "clean" || { echo "$out"; exit 1; }
echo "== OnCalendar"
for t in "$here"/systemd/*.timer; do
  expr="$(sed -n 's/^OnCalendar=//p' "$t")"; printf '%-40s ' "$(basename "$t")"
  systemd-analyze calendar "$expr" | sed -n 's/^ *Next elapse: //p'
done
echo "== crontab syntax"
python3 - "$here/systemd/crontab.example" <<'PY'
import re, sys
bad = 0
for n, line in enumerate(open(sys.argv[1]), 1):
    line = line.rstrip("\n")
    if not line.strip() or line.startswith("#") or re.match(r"^[A-Z]+=", line):
        continue
    parts = line.split(None, 5)
    ok = len(parts) == 6 and all(re.fullmatch(r"(\*|\d+|\*/\d+|\d+-\d+)(,(\d+|\*/\d+|\d+-\d+))*", p) for p in parts[:5])
    ok = ok and "flock -n /run/talim/" in parts[5] and "/srv/talim/backend/.venv/bin/python" in parts[5]
    if not ok:
        print(f"line {n}: not a valid job line"); bad += 1
sys.exit(1 if bad else 0)
PY
echo "ok"
if command -v logrotate >/dev/null; then echo "== logrotate"; sed "s/ talim talim/ $(id -un) $(id -gn)/" "$here/logrotate/talim" > "$root/logrotate.conf"; logrotate -d "$root/logrotate.conf" 2>&1 | grep -E "error|reading config" || true; fi
