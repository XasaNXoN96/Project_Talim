#!/usr/bin/env bash
# Reproducible check of the Nginx + client-IP chain (B-1) with a REAL nginx and a REAL gunicorn.
#   Needs: nginx, psql/createdb, backend/.venv with requirements installed, a database role allowed to create databases.
#   Optional: a running clamd (the upload step then goes through the real antivirus).
#   Uses 127.0.0.2/127.0.0.3 as "different client addresses" (the whole 127.0.0.0/8 is local on Linux).
# It creates and drops its own database (talim_nginx_check) and touches nothing else. Usage: backend/deploy/nginx/verify/run.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../../.." && pwd)"
PY="$BACKEND/.venv/bin/python"; GUNICORN="$BACKEND/.venv/bin/gunicorn"
NGINX_PORT=${NGINX_PORT:-18080}; APP_PORT=${APP_PORT:-18000}; CHECK_DB=talim_nginx_check
WORK="$(mktemp -d /tmp/talim-nginx-XXXXXX)"; chmod 755 "$WORK"; mkdir -p "$WORK/logs" "$WORK/static" "$WORK/private"
cd "$BACKEND"

# DB credentials come from backend/.env (never printed)
eval "$("$PY" - <<'PYEOF'
import shlex
from dotenv import dotenv_values
v = dotenv_values(".env")
for k in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
    print(f"export {k}={shlex.quote(v.get(k, ''))}")
PYEOF
)"
export PGPASSWORD="$DB_PASSWORD" PGHOST="${DB_HOST:-localhost}" PGPORT="${DB_PORT:-5432}" PGUSER="$DB_USER"
psql -d postgres -qc "DROP DATABASE IF EXISTS $CHECK_DB" -c "CREATE DATABASE $CHECK_DB"

APP_ENV=(DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 DB_NAME=$CHECK_DB DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
         DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" PYTHONPATH="$BACKEND")
SCAN=clamav
if ! env "${APP_ENV[@]}" "$PY" manage.py check_scanner >/dev/null 2>&1; then SCAN=disabled; echo "NOTE: clamd not reachable: upload checks run WITHOUT the antivirus"; fi
APP_ENV+=(DOCUMENT_SCAN_MODE=$SCAN)
env "${APP_ENV[@]}" "$PY" manage.py migrate -v0
env "${APP_ENV[@]}" "$PY" manage.py seed_roles -v0
env "${APP_ENV[@]}" "$PY" "$HERE/seed_users.py"

render() {  # $1 = read timeout
  sed -e "s#{{BACKEND_PORT}}#$APP_PORT#g" -e "s#{{LISTEN}}#0.0.0.0:$NGINX_PORT#" -e "s#{{SERVER_NAME}}#_#" \
      -e "s#{{ERROR_DIR}}#$HERE/../errors#" -e "s#{{STATIC_DIR}}#$WORK/static#" -e "s#{{READ_TIMEOUT}}#$1#" "$HERE/../talim.conf.template" > "$WORK/site.conf"
  cat > "$WORK/nginx.conf" <<NGX
pid $WORK/nginx.pid;
error_log $WORK/logs/nginx-error.log warn;
events { worker_connections 64; }
http {
  include /etc/nginx/mime.types;
  access_log $WORK/logs/nginx-access.log;
  client_body_temp_path $WORK/body; proxy_temp_path $WORK/proxy; fastcgi_temp_path $WORK/fc; uwsgi_temp_path $WORK/uw; scgi_temp_path $WORK/sc;
  include $WORK/site.conf;
}
NGX
  chmod -R a+rX "$WORK"
}
start_app() {  # $1 = trusted proxies value
  env "${APP_ENV[@]}" DJANGO_TRUSTED_PROXIES="$1" "$GUNICORN" config.wsgi:application --bind "0.0.0.0:$APP_PORT" --workers 2 --timeout 60 \
      --pid "$WORK/gunicorn.pid" --daemon --error-logfile "$WORK/logs/gunicorn.log" --access-logfile -
  for _ in $(seq 40); do curl -s -o /dev/null "http://127.0.0.1:$APP_PORT/healthz/" && return; sleep 0.25; done; echo "gunicorn did not start"; tail "$WORK/logs/gunicorn.log"; exit 1
}
stop_app() { [ -f "$WORK/gunicorn.pid" ] && kill "$(cat "$WORK/gunicorn.pid")" 2>/dev/null || true; sleep 1; rm -f "$WORK/gunicorn.pid"; }
cleanup() { stop_app; [ -f "$WORK/nginx.pid" ] && kill "$(cat "$WORK/nginx.pid")" 2>/dev/null || true; sleep 0.5; psql -d postgres -qc "DROP DATABASE IF EXISTS $CHECK_DB" || true; echo "logs kept in $WORK/logs"; }
trap cleanup EXIT

render 3s
nginx -t -c "$WORK/nginx.conf" 2>&1 | sed 's/^/nginx: /'
nginx -c "$WORK/nginx.conf"
export NGINX_PORT APP_PORT CHECK_DB WORK GUNICORN_PID_FILE="$WORK/gunicorn.pid" DOC_SCAN="$SCAN"
# Phase 1: correct configuration (trusted proxy = 127.0.0.1 only)
start_app 127.0.0.1
"$PY" "$HERE/checks.py" correct
# Phase 2: negative controls (a deliberately wrong configuration must make the checks FAIL as expected)
stop_app; start_app ""
"$PY" "$HERE/checks.py" no_trusted_proxy
stop_app; start_app "127.0.0.0/8"
"$PY" "$HERE/checks.py" too_broad
# Phase 3: failures of the upstream (down, hung): back to the correct configuration
stop_app; start_app 127.0.0.1
"$PY" "$HERE/checks.py" upstream_failures
echo "ALL NGINX CHECKS FINISHED"
