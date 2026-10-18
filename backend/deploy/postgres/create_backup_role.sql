-- One-time creation of the THIRD database role, used only by the backup and restore-check jobs (run as a PostgreSQL superuser).
--   psql -v backup_role=talim_backup -v backup_password="$(cat <file 0600>)" -f create_backup_role.sql
-- It can read all data of every database it is allowed to connect to (pg_read_all_data: needed by pg_dump) and may CREATE DATABASE (the restore check
-- restores into a scratch database). It is NOT a superuser, cannot create roles, owns nothing in the live database and cannot change it.
-- Put it in /etc/talim/backup.env as PGUSER (+ PGPASSFILE=/etc/talim/backup.pgpass). The runtime role never gets CREATEDB.
CREATE ROLE :"backup_role" LOGIN PASSWORD :'backup_password' NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT pg_read_all_data TO :"backup_role";
