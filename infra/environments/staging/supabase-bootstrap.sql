-- Staging only: fresh private schema in the connected Supabase project.
-- Apply exactly once through the migration/provisioning role. Never at app startup.
CREATE SCHEMA fw_agenttest_lab;
REVOKE ALL ON SCHEMA fw_agenttest_lab FROM PUBLIC, anon, authenticated;
SET LOCAL search_path TO fw_agenttest_lab, pg_catalog;
ALTER DEFAULT PRIVILEGES IN SCHEMA fw_agenttest_lab REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA fw_agenttest_lab REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;
-- Source: 001_agenttest_mvp.sql
-- AgentTest MVP disposable migration; review-only FK addendum is excluded.
CREATE TABLE IF NOT EXISTS tenants(id uuid PRIMARY KEY,slug text UNIQUE NOT NULL,status text NOT NULL);
CREATE TABLE IF NOT EXISTS datasets(tenant_id uuid NOT NULL,id uuid NOT NULL,name text NOT NULL,owner_id text NOT NULL,latest_version integer NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id) REFERENCES tenants(id));
CREATE TABLE IF NOT EXISTS dataset_versions(tenant_id uuid NOT NULL,id uuid NOT NULL,dataset_id uuid NOT NULL,version_number integer NOT NULL,sha256 char(64) NOT NULL,case_count integer NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,dataset_id,version_number),FOREIGN KEY(tenant_id,dataset_id) REFERENCES datasets(tenant_id,id));
CREATE TABLE IF NOT EXISTS agent_builds(tenant_id uuid NOT NULL,id uuid NOT NULL,build_sha256 char(64) NOT NULL,tool_manifest_sha256 char(64) NOT NULL,prompt_version text NOT NULL,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id) REFERENCES tenants(id));
CREATE TABLE IF NOT EXISTS evaluation_runs(tenant_id uuid NOT NULL,id uuid NOT NULL,dataset_version_id uuid NOT NULL,agent_build_id uuid NOT NULL,grader_sha256 char(64) NOT NULL,status text NOT NULL,PRIMARY KEY(tenant_id,id),FOREIGN KEY(tenant_id,dataset_version_id) REFERENCES dataset_versions(tenant_id,id),FOREIGN KEY(tenant_id,agent_build_id) REFERENCES agent_builds(tenant_id,id));
CREATE TABLE IF NOT EXISTS case_results(tenant_id uuid NOT NULL,id uuid NOT NULL,run_id uuid NOT NULL,case_key text NOT NULL,grade_status text NOT NULL,score numeric NOT NULL,grader_sha256 char(64) NOT NULL,trace_digest char(64) NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,run_id,case_key),FOREIGN KEY(tenant_id,run_id) REFERENCES evaluation_runs(tenant_id,id));
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY;ALTER TABLE case_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY datasets_tenant ON datasets USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY evaluation_runs_tenant ON evaluation_runs USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY case_results_tenant ON case_results USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

-- Source: 002_agenttest_runtime.sql
-- Runtime extension of canonical MVP tables; apply with the migration role only.
ALTER TABLE dataset_versions ADD COLUMN artifact_id uuid;
ALTER TABLE dataset_versions ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE agent_builds ADD COLUMN name text NOT NULL DEFAULT '';
ALTER TABLE agent_builds ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE evaluation_runs ADD COLUMN grader_config_json jsonb NOT NULL DEFAULT '{}';
ALTER TABLE evaluation_runs ADD COLUMN grader_config_sha char(64);
ALTER TABLE evaluation_runs ADD COLUMN threshold double precision;
ALTER TABLE evaluation_runs ADD COLUMN seed bigint;
ALTER TABLE evaluation_runs ADD COLUMN seed_source text;
ALTER TABLE evaluation_runs ADD COLUMN expected_case_count integer;
ALTER TABLE evaluation_runs ADD COLUMN job_id uuid;
ALTER TABLE evaluation_runs ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
-- Missing/time-out/invalid results have no score, and must remain distinct from zero/PASS.
ALTER TABLE case_results ALTER COLUMN score DROP NOT NULL;
ALTER TABLE case_results ADD CONSTRAINT case_score_range CHECK(score IS NULL OR (score>=0 AND score<=1));
ALTER TABLE case_results ADD COLUMN error_code text;
ALTER TABLE case_results ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
CREATE TABLE memberships(tenant_id uuid NOT NULL REFERENCES tenants(id),user_id uuid NOT NULL,role text NOT NULL,status text NOT NULL,PRIMARY KEY(tenant_id,user_id));
CREATE TABLE artifacts(tenant_id uuid NOT NULL,id uuid NOT NULL,kind text NOT NULL,filename text NOT NULL,size_bytes bigint NOT NULL,sha256 char(64) NOT NULL,declared_media_type text,status text NOT NULL,object_generation text,rejected_reason text,created_at timestamptz NOT NULL,PRIMARY KEY(tenant_id,id));
CREATE TABLE comparisons(tenant_id uuid NOT NULL,id uuid NOT NULL,baseline_id uuid NOT NULL,candidate_id uuid NOT NULL,baseline_version_id uuid NOT NULL,candidate_version_id uuid NOT NULL,baseline_build_id uuid NOT NULL,candidate_build_id uuid NOT NULL,baseline_grader_sha char(64) NOT NULL,candidate_grader_sha char(64) NOT NULL,baseline_config_sha char(64) NOT NULL,candidate_config_sha char(64) NOT NULL,paired integer NOT NULL,missing integer NOT NULL,delta double precision NOT NULL,threshold double precision NOT NULL,policy text NOT NULL,verdict text NOT NULL,artifact_sha char(64) NOT NULL,artifact_id uuid NOT NULL,created_at timestamptz NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,baseline_id,candidate_id,policy),FOREIGN KEY(tenant_id,baseline_id) REFERENCES evaluation_runs(tenant_id,id),FOREIGN KEY(tenant_id,candidate_id) REFERENCES evaluation_runs(tenant_id,id),FOREIGN KEY(tenant_id,artifact_id) REFERENCES artifacts(tenant_id,id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE artifact_exports(tenant_id uuid NOT NULL,id uuid NOT NULL,artifact_id uuid NOT NULL,comparison_id uuid NOT NULL,kind text NOT NULL,sha256 char(64) NOT NULL,binding_json text NOT NULL,created_at timestamptz NOT NULL,PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,comparison_id,kind),FOREIGN KEY(tenant_id,artifact_id) REFERENCES artifacts(tenant_id,id),FOREIGN KEY(tenant_id,comparison_id) REFERENCES comparisons(tenant_id,id));
CREATE TABLE idempotency_keys(tenant_id uuid NOT NULL REFERENCES tenants(id),operation text NOT NULL,key text NOT NULL,fingerprint char(64) NOT NULL,resource_id uuid NOT NULL,created_at timestamptz NOT NULL,PRIMARY KEY(tenant_id,operation,key));
CREATE ROLE fw_agenttest_lab_rw NOLOGIN NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA fw_agenttest_lab TO fw_agenttest_lab_rw;
DO $$
DECLARE tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['datasets','dataset_versions','agent_builds','evaluation_runs','case_results','comparisons','artifacts','artifact_exports','memberships','idempotency_keys']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tbl);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tbl);
    IF tbl NOT IN ('datasets','evaluation_runs','case_results') THEN
      EXECUTE format('CREATE POLICY tenant_boundary ON %I USING (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',tbl);
    END IF;
    EXECUTE format('GRANT SELECT ON %I TO fw_agenttest_lab_rw',tbl);
    IF tbl <> 'memberships' THEN
      EXECUTE format('GRANT INSERT ON %I TO fw_agenttest_lab_rw',tbl);
    END IF;
    IF tbl IN ('datasets','evaluation_runs','artifacts') THEN
      EXECUTE format('GRANT UPDATE,DELETE ON %I TO fw_agenttest_lab_rw',tbl);
    END IF;
  END LOOP;
END $$;

-- Source: 003_agenttest_dataset_sources.sql
CREATE TABLE dataset_sources(
 tenant_id uuid NOT NULL,dataset_version_id uuid NOT NULL,
 source_jsonl text NOT NULL CHECK(octet_length(source_jsonl)<=1048576),
 PRIMARY KEY(tenant_id,dataset_version_id),
 FOREIGN KEY(tenant_id,dataset_version_id) REFERENCES dataset_versions(tenant_id,id)
);
ALTER TABLE dataset_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_sources FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_boundary ON dataset_sources
USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
GRANT SELECT,INSERT ON dataset_sources TO fw_agenttest_lab_rw;

-- Auth-managed tables remain untouched. Return only a boolean for the JWT-bound user.
CREATE FUNCTION fw_agenttest_lab.session_active(session_id uuid, user_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
 SELECT auth.uid() = $2 AND EXISTS (
   SELECT 1 FROM auth.sessions s JOIN auth.users u ON u.id=s.user_id
   WHERE s.id=$1 AND s.user_id=$2
     AND (s.not_after IS NULL OR s.not_after > now())
     AND u.deleted_at IS NULL AND (u.banned_until IS NULL OR u.banned_until <= now())
 );
$$;
REVOKE ALL ON FUNCTION fw_agenttest_lab.session_active(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION fw_agenttest_lab.session_active(uuid, uuid) TO fw_agenttest_lab_rw;
GRANT USAGE ON SCHEMA fw_agenttest_lab TO fw_agenttest_lab_rw;
-- Restrict all product tables, including unexposed tenants, as defense in depth.
DO $$ DECLARE t record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='fw_agenttest_lab' LOOP
   EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY','fw_agenttest_lab',t.tablename);
   EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY','fw_agenttest_lab',t.tablename);
   EXECUTE format('REVOKE ALL ON %I.%I FROM PUBLIC, anon, authenticated','fw_agenttest_lab',t.tablename);
 END LOOP;
END $$;
RESET search_path;
