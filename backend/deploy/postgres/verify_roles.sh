#!/usr/bin/env bash
# Proves the least-privilege setup with the REAL application: creates a scratch database and two scratch roles, migrates as the owner role,
# applies grants, then runs the application's normal write paths as the restricted role, and checks that what it must not do is refused.
# Needs a PostgreSQL role that may create databases and roles (a development/test cluster, never the production cluster).
# Usage: backend/deploy/postgres/verify_roles.sh        (credentials come from backend/.env; nothing is printed)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BACKEND="$(cd "$HERE/../.." && pwd)"; PY="$BACKEND/.venv/bin/python"
cd "$BACKEND"
eval "$("$PY" - <<'PYEOF'
import shlex
from dotenv import dotenv_values
v = dotenv_values(".env")
for k in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
    print(f"export ADMIN_{k}={shlex.quote(v.get(k, ''))}")
PYEOF
)"
export PGPASSWORD="$ADMIN_DB_PASSWORD" PGHOST="${ADMIN_DB_HOST:-localhost}" PGPORT="${ADMIN_DB_PORT:-5432}" PGUSER="$ADMIN_DB_USER"
# Creating roles needs a PostgreSQL superuser (or CREATEROLE + CREATEDB). On a development machine where this runs as root, use the local
# "postgres" account over the socket; otherwise the credentials from .env must carry those rights. Override with ADMIN_PSQL="..." if needed.
if [ -z "${ADMIN_PSQL:-}" ]; then
  if [ "$(id -u)" = 0 ] && id postgres >/dev/null 2>&1; then ADMIN_PSQL="runuser -u postgres -- env -u PGUSER -u PGPASSWORD -u PGHOST -u PGPORT psql"; else ADMIN_PSQL="psql"; fi
fi
SUFFIX="$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
DB="talim_roles_check_$SUFFIX"; OWNER="talim_owner_chk_$SUFFIX"; APP="talim_app_chk_$SUFFIX"
OWNER_PW="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(24))')"; APP_PW="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(24))')"
WORK="$(mktemp -d /tmp/talim-roles-XXXXXX)"
cleanup() { $ADMIN_PSQL -d postgres -qc "DROP DATABASE IF EXISTS \"$DB\"" -c "DROP ROLE IF EXISTS \"$APP\"" -c "DROP ROLE IF EXISTS \"$OWNER\"" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
$ADMIN_PSQL -d postgres -qv ON_ERROR_STOP=1 -v owner="$OWNER" -v app="$APP" -v db="$DB" -v owner_password="$OWNER_PW" -v app_password="$APP_PW" -f "$HERE/create_roles.sql"
APP_ENV=(DJANGO_SETTINGS_MODULE=config.settings.dev DJANGO_DEBUG=0 DB_NAME="$DB" DB_HOST="$PGHOST" DB_PORT="$PGPORT" DJANGO_PRIVATE_MEDIA_ROOT="$WORK/private" DOCUMENT_SCAN_MODE=disabled DJANGO_ALLOWED_HOSTS=testserver PYTHONPATH="$BACKEND")
echo "migrate as the OWNER role"
env "${APP_ENV[@]}" DB_USER="$OWNER" DB_PASSWORD="$OWNER_PW" "$PY" manage.py migrate -v0
env "${APP_ENV[@]}" DB_USER="$OWNER" DB_PASSWORD="$OWNER_PW" "$PY" manage.py seed_roles -v0
echo "apply grants (twice: it must be idempotent)"
for _ in 1 2; do PGPASSWORD="$OWNER_PW" PGUSER="$OWNER" psql -d "$DB" -qv ON_ERROR_STOP=1 -v app="$APP" -v db="$DB" -f "$HERE/apply_grants.sql" >/dev/null; done
echo "run the application as the RESTRICTED role"
env "${APP_ENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" "$HERE/verify_roles_smoke.py"
echo "migrate as the restricted role must be refused"
if env "${APP_ENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" manage.py migrate -v0 >/dev/null 2>&1; then
  if env "${APP_ENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" -c "
import django;django.setup()
from django.db import connection
c=connection.cursor()
try:
    c.execute('CREATE TABLE should_fail (i int)'); print('can create')
except Exception: print('refused')" | grep -q refused; then echo "  [PASS] (migrate had nothing to do; creating a table is refused)"; else echo "  [FAIL] the restricted role can create tables"; exit 1; fi
else echo "  [PASS] migrate as the restricted role is refused"; fi
echo "a table created by a migration but WITHOUT grants must make /healthz/ report 'degraded' (so release.sh rolls back), and apply_grants.sql must cure it"
PGPASSWORD="$OWNER_PW" PGUSER="$OWNER" psql -d "$DB" -qc "CREATE TABLE zz_forgotten_grants (i int)" >/dev/null
health() { env "${APP_ENV[@]}" DB_USER="$APP" DB_PASSWORD="$APP_PW" "$PY" -c "
import django; django.setup()
from django.test import Client
r = Client().get('/healthz/', HTTP_HOST='testserver'); print(r.status_code, r.json()['grants'])" 2>/dev/null; }
if [ "$(health)" = "503 error" ]; then echo "  [PASS] forgotten grants are reported (503, grants=error)"; else echo "  [FAIL] forgotten grants are not detected: $(health)"; exit 1; fi
PGPASSWORD="$OWNER_PW" PGUSER="$OWNER" psql -d "$DB" -qv ON_ERROR_STOP=1 -v app="$APP" -v db="$DB" -f "$HERE/apply_grants.sql" >/dev/null
if [ "$(health)" = "200 ok" ]; then echo "  [PASS] after apply_grants.sql the check is healthy again"; else echo "  [FAIL] still degraded after apply_grants.sql: $(health)"; exit 1; fi
echo "ROLE CHECKS FINISHED"
