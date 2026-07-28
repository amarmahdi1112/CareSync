\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname = 'caresync_release_probe'
  ) THEN
    CREATE ROLE caresync_release_probe
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      NOREPLICATION NOBYPASSRLS NOLOGIN;
  END IF;
END
$$;

ALTER ROLE caresync_release_probe
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOREPLICATION NOBYPASSRLS NOLOGIN;
ALTER ROLE caresync_release_probe RESET ALL;
ALTER ROLE caresync_release_probe SET default_transaction_read_only = on;
ALTER ROLE caresync_release_probe SET search_path = pg_catalog, public;
ALTER ROLE caresync_release_probe SET statement_timeout = '15s';
ALTER ROLE caresync_release_probe SET lock_timeout = '2s';
SELECT format(
  'ALTER ROLE caresync_release_probe PASSWORD %L',
  :'probe_password'
)
\gexec

SELECT format(
  'REVOKE %I FROM caresync_release_probe',
  parent.rolname
)
FROM pg_catalog.pg_auth_members membership
JOIN pg_catalog.pg_roles parent ON parent.oid = membership.roleid
JOIN pg_catalog.pg_roles member ON member.oid = membership.member
WHERE member.rolname = 'caresync_release_probe'
\gexec

REVOKE ALL PRIVILEGES ON DATABASE :"database_name"
  FROM caresync_release_probe;
GRANT CONNECT ON DATABASE :"database_name" TO caresync_release_probe;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM caresync_release_probe;
GRANT USAGE ON SCHEMA public TO caresync_release_probe;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
  FROM caresync_release_probe;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public
  FROM caresync_release_probe;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public
  FROM caresync_release_probe;

DO $release_probe_column_acl_scrub$
DECLARE
  target record;
BEGIN
  FOR target IN
    SELECT namespace.nspname,
           relation.relname,
           pg_catalog.string_agg(
             pg_catalog.quote_ident(attribute.attname),
             ',' ORDER BY attribute.attnum
           ) AS column_list
    FROM pg_catalog.pg_attribute AS attribute
    JOIN pg_catalog.pg_class AS relation
      ON relation.oid = attribute.attrelid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        attribute.attacl,
        pg_catalog.acldefault('c', relation.relowner)
      )
    ) AS grant_entry
    WHERE namespace.nspname = 'public'
      AND relation.relkind IN ('r','p','v','m','f')
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
      AND grant_entry.grantee =
          pg_catalog.to_regrole('caresync_release_probe')
    GROUP BY namespace.nspname, relation.relname
  LOOP
    EXECUTE pg_catalog.format(
      'REVOKE ALL PRIVILEGES (%s) ON TABLE %I.%I FROM caresync_release_probe',
      target.column_list,
      target.nspname,
      target.relname
    );
  END LOOP;
END
$release_probe_column_acl_scrub$;

COMMIT;
