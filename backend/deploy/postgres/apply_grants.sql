-- Runtime privileges of the application role. Run as the OWNER role (or a superuser) AFTER EVERY `manage.py migrate`; it is idempotent.
--   psql -d <database> -v app=talim_app -v db=<database> -f apply_grants.sql
-- The roles themselves are created once with create_roles.sql. Nothing here contains a password.
--
-- Principles: the application role is not a superuser and cannot create databases, roles, tables or schemas; it can read and write rows,
-- but it cannot rewrite the migration history, and the audit log is APPEND-ONLY for it at the database level (no UPDATE/DELETE/TRUNCATE).
-- The one UPDATE it keeps on the audit log is the user_id column, because deleting a user sets that column to NULL (ON DELETE SET NULL).
GRANT CONNECT ON DATABASE :"db" TO :"app";
GRANT USAGE ON SCHEMA public TO :"app";
REVOKE CREATE ON SCHEMA public FROM :"app";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app";
-- append-only audit log
REVOKE UPDATE, DELETE, TRUNCATE ON audit_auditlog FROM :"app";
GRANT UPDATE (user_id) ON audit_auditlog TO :"app";
-- the migration history belongs to the owner role
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON django_migrations FROM :"app";
