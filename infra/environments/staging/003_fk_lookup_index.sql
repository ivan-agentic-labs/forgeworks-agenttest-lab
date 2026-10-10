-- Additive index for evaluation runs by immutable dataset version. Apply with the migration role and
-- search_path set to fw_agenttest_lab, pg_catalog (never the runtime role).
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_dataset_version ON evaluation_runs (tenant_id, dataset_version_id);
