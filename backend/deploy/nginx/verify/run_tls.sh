#!/usr/bin/env bash
# TLS chain check with a REAL nginx (production template) and a REAL gunicorn running config.settings.production, using a THROW-AWAY
# self-signed certificate. What this proves: the template is valid, HTTP redirects, TLS 1.2/1.3 only, cookies/headers/redirect logic of the
# production settings behind TLS termination, forged proxy headers are ignored. What it does NOT prove: a real certificate and chain,
# DNS, the public internet, firewall, or HSTS preload. Usage: backend/deploy/nginx/verify/run_tls.sh   (needs nginx, openssl, backend/.venv, a DB role with CREATEDB)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../../.." && pwd)"
PY="$BACKEND/.venv/bin/python"; GUNICORN="$BACKEND/.venv/bin/gunicorn"
HTTP_PORT=${HTTP_PORT:-18081}; HTTPS_PORT=${HTTPS_PORT:-18443}; APP_PORT=${APP_PORT:-18001}; CHECK_DB=talim_tls_check
WORK="$(mktemp -d /tmp/talim-tls-XXXXXX)"; chmod 755 "$WORK"; mkdir -p "$WORK/logs" "$WORK/static" "$WORK/private"
cd "$BACKEND"
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
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" -keyout "$WORK/tls.key" -out "$WORK/tls.crt" 2>/dev/null
chmod 600 "$WORK/tls.key"

# production settings need these; all values are generated here and thrown away
SECRET="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(70))')"
FERNET="$("$PY" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
ADMIN_URL="gate-$("$PY" -c 'import secrets;print(secrets.token_hex(6))')/"
BASE_ENV=(DB_NAME=$CHECK_DB DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" PYTHONPATH="$BACKEND" DJANGO_SECRET_KEY="$SECRET" OTP_ENCRYPTION_KEYS="$FERNET"
          DJANGO_ALLOWED_HOSTS=localhost EMAIL_HOST=127.0.0.1 DEFAULT_FROM_EMAIL=noreply@example.test DJANGO_ADMIN_URL="$ADMIN_URL"
          DJANGO_CSRF_TRUSTED_ORIGINS="https://localhost:$HTTPS_PORT" DJANGO_TRUSTED_PROXIES=127.0.0.1 DOCUMENT_SCAN_MODE=clamav)
# schema and fictional users through the development settings (same database)
env "${BASE_ENV[@]}" DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 "$PY" manage.py migrate -v0
env "${BASE_ENV[@]}" DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 "$PY" manage.py seed_roles -v0
env "${BASE_ENV[@]}" DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 "$PY" "$HERE/seed_users.py"
env "${BASE_ENV[@]}" DJANGO_SETTINGS_MODULE=config.settings.production "$PY" manage.py collectstatic --noinput -v0 --clear 2>/dev/null || true

sed -e "s#{{BACKEND_PORT}}#$APP_PORT#g" -e "s#{{HTTP_LISTEN}}#127.0.0.1:$HTTP_PORT#" -e "s#{{HTTPS_LISTEN}}#127.0.0.1:$HTTPS_PORT#" -e "s#{{SERVER_NAME}}#localhost#g" \
    -e "s#{{HTTPS_PORT_SUFFIX}}#:$HTTPS_PORT#" -e "s#{{TLS_CERT}}#$WORK/tls.crt#" -e "s#{{TLS_KEY}}#$WORK/tls.key#" -e "s#{{ERROR_DIR}}#$HERE/../errors#" \
    -e "s#{{STATIC_DIR}}#$WORK/static#" -e "s#{{ACCESS_LOG}}#$WORK/logs/talim-access.log#" "$HERE/../talim-production.conf.template" > "$WORK/site.conf"
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
chmod -R a+rX "$WORK"; chmod 600 "$WORK/tls.key"
start_app() {  # $@ = extra environment (e.g. DJANGO_HSTS_SECONDS=60)
  env "${BASE_ENV[@]}" DJANGO_SETTINGS_MODULE=config.settings.production "$@" "$GUNICORN" config.wsgi:application --bind "127.0.0.1:$APP_PORT" --workers 2 --timeout 60 \
      --pid "$WORK/gunicorn.pid" --daemon --error-logfile "$WORK/logs/gunicorn.log"
  for _ in $(seq 60); do (exec 3<>"/dev/tcp/127.0.0.1/$APP_PORT") 2>/dev/null && return; sleep 0.25; done; echo "gunicorn did not start"; tail "$WORK/logs/gunicorn.log"; exit 1
}
stop_app() { [ -f "$WORK/gunicorn.pid" ] && kill "$(cat "$WORK/gunicorn.pid")" 2>/dev/null || true; sleep 1; rm -f "$WORK/gunicorn.pid"; }
cleanup() { stop_app; [ -f "$WORK/nginx.pid" ] && kill "$(cat "$WORK/nginx.pid")" 2>/dev/null || true; sleep 0.5; psql -d postgres -qc "DROP DATABASE IF EXISTS $CHECK_DB" || true; echo "logs kept in $WORK/logs"; }
trap cleanup EXIT

nginx -t -c "$WORK/nginx.conf" 2>&1 | sed 's/^/nginx: /'
nginx -c "$WORK/nginx.conf"
export HTTP_PORT HTTPS_PORT APP_PORT ADMIN_URL WORK ACCESS_LOG="$WORK/logs/talim-access.log"
start_app DJANGO_HSTS_SECONDS=0
"$PY" "$HERE/checks_tls.py" hsts_off
echo "-- operator smoke script against the same stand (rehearsal mode: self-signed certificate not validated)"
"$PY" "$HERE/../../staging/smoke_remote.py" "https://localhost:$HTTPS_PORT" --admin-path "$ADMIN_URL" --http-port "$HTTP_PORT" --insecure-self-signed
echo "-- negative control: WITHOUT the rehearsal flag the self-signed certificate must be REJECTED"
if "$PY" "$HERE/../../staging/smoke_remote.py" "https://localhost:$HTTPS_PORT" --http-port "$HTTP_PORT" >/dev/null 2>&1; then echo "FAIL: untrusted certificate accepted"; exit 1; else echo "  [PASS] untrusted certificate rejected"; fi
stop_app; start_app DJANGO_HSTS_SECONDS=60
"$PY" "$HERE/checks_tls.py" hsts_on
echo "-- negative control: report-only CSP must make the operator smoke script FAIL"
stop_app; start_app DJANGO_HSTS_SECONDS=0 DJANGO_CSP_REPORT_ONLY=1
if "$PY" "$HERE/../../staging/smoke_remote.py" "https://localhost:$HTTPS_PORT" --http-port "$HTTP_PORT" --insecure-self-signed >"$WORK/smoke_neg.txt" 2>&1; then echo "FAIL: report-only CSP not detected"; exit 1; else grep -q "FAIL\] CSP is enforcing" "$WORK/smoke_neg.txt" && echo "  [PASS] report-only CSP detected" || { echo "FAIL: smoke failed for another reason"; cat "$WORK/smoke_neg.txt"; exit 1; }; fi
echo "-- negative control: no HTTP->HTTPS redirect must make the operator smoke script FAIL"
cp "$WORK/site.conf" "$WORK/site.conf.orig"
sed -i 's#return 301 https://[^;]*;#return 200 "plain http served";#' "$WORK/site.conf"; grep -q "plain http served" "$WORK/site.conf" || { echo "FAIL: mutation did not apply"; exit 1; }
nginx -s reload -c "$WORK/nginx.conf"; sleep 1
if "$PY" "$HERE/../../staging/smoke_remote.py" "https://localhost:$HTTPS_PORT" --http-port "$HTTP_PORT" --insecure-self-signed >"$WORK/smoke_neg2.txt" 2>&1; then echo "FAIL: missing redirect not detected"; exit 1; else grep -q "FAIL\] HTTP redirects" "$WORK/smoke_neg2.txt" && echo "  [PASS] missing redirect detected" || { echo "FAIL: smoke failed for another reason"; cat "$WORK/smoke_neg2.txt"; exit 1; }; fi
cp "$WORK/site.conf.orig" "$WORK/site.conf"; nginx -s reload -c "$WORK/nginx.conf"
echo "ALL TLS CHECKS FINISHED (self-signed certificate: chain validation, DNS and the public internet were NOT tested)"
