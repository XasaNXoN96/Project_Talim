-- One-time creation of the two database roles (run as a PostgreSQL superuser, e.g. `sudo -u postgres psql -f create_roles.sql ...`).
--   psql -v owner=talim_owner -v app=talim_app -v db=talim \
--        -v owner_password="$(cat /etc/talim/db_owner.secret)" -v app_password="$(cat /etc/talim/db_app.secret)" -f create_roles.sql
-- Passwords are passed as psql variables from files outside Git (mode 0600): this file contains none, and nothing is echoed.
--   owner: owns the tables, used ONLY for `manage.py migrate` during a release (set DB_USER/DB_PASSWORD for that command).
--   app:   what gunicorn and the scheduled jobs use at run time (DB_USER/DB_PASSWORD in /etc/talim/talim.env).
-- Neither role is a superuser, neither can create roles or databases (the restore check uses a THIRD, separate role with CREATEDB; see docs).
CREATE ROLE :"owner" LOGIN PASSWORD :'owner_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE :"app"   LOGIN PASSWORD :'app_password'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE :"db" OWNER :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
\connect :"db"
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO :"owner";
