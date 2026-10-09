#!/usr/bin/env bash
set -euo pipefail

# This is a runtime proof only for an isolated disposable PostgreSQL service.
[[ "${G1_DISPOSABLE_DB:-}" == 'yes' ]] || { echo 'G1_DISPOSABLE_DB=yes required' >&2; exit 2; }
[[ "${PGHOST:-}" == '127.0.0.1' ]] || { echo 'only 127.0.0.1 is allowed' >&2; exit 2; }
[[ "${PGDATABASE:-}" == 'forgeworks_g1' ]] || { echo 'only disposable database forgeworks_g1 is allowed' >&2; exit 2; }
command -v psql >/dev/null || { echo 'psql unavailable' >&2; exit 2; }

echo 'G2 runtime proof: application-role RLS tenant isolation'
psql -X -v ON_ERROR_STOP=1 <<'SQL'
\set ON_ERROR_STOP on
BEGIN;
-- The session starts as the disposable database owner and only seeds fixtures.
INSERT INTO tenants (id, slug, status)
VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'rls-tenant-a', 'ACTIVE'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'rls-tenant-b', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;
INSERT INTO users (id, issuer, subject)
VALUES ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'https://issuer.synthetic.invalid', 'rls-proof')
ON CONFLICT (id) DO NOTHING;
INSERT INTO datasets (tenant_id, id, name, owner_id)
VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'tenant-a-visible', 'cccccccc-cccc-cccc-cccc-cccccccccccc'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'tenant-b-hidden', 'cccccccc-cccc-cccc-cccc-cccccccccccc')
ON CONFLICT (tenant_id, id) DO NOTHING;
COMMIT;

BEGIN;
SET LOCAL ROLE fw_agenttest_lab_rw;
SET LOCAL app.tenant_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

DO $$
BEGIN
  IF current_user <> 'fw_agenttest_lab_rw' OR session_user = current_user THEN
    RAISE EXCEPTION 'RLS proof did not execute as a non-owner application role';
  END IF;
  IF (SELECT count(*) FROM datasets WHERE id = 'dddddddd-dddd-dddd-dddd-dddddddddddd') <> 1 THEN
    RAISE EXCEPTION 'current tenant cannot see its own dataset';
  END IF;
  IF (SELECT count(*) FROM datasets WHERE id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee') <> 0 THEN
    RAISE EXCEPTION 'cross-tenant dataset is visible';
  END IF;
  IF (SELECT count(*) FROM datasets) <> 1 THEN
    RAISE EXCEPTION 'tenant-scoped SELECT returned unexpected rows';
  END IF;

  BEGIN
    INSERT INTO datasets (tenant_id, id, name, owner_id)
    VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'cross-tenant-write', 'cccccccc-cccc-cccc-cccc-cccccccccccc');
    RAISE EXCEPTION 'cross-tenant INSERT unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;

  UPDATE datasets SET name = 'must-not-change' WHERE id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';
  IF FOUND THEN
    RAISE EXCEPTION 'cross-tenant UPDATE unexpectedly changed a row';
  END IF;
  DELETE FROM datasets WHERE id = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee';
  IF FOUND THEN
    RAISE EXCEPTION 'cross-tenant DELETE unexpectedly changed a row';
  END IF;
END
$$;

ROLLBACK;
SQL

echo 'PASS: non-owner application role cannot read or mutate another tenant'
