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
GRANT USAGE ON SCHEMA public TO fw_agenttest_lab_rw;
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
