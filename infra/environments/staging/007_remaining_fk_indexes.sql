-- Additive FK lookup indexes for this product's small staging tables.
-- Apply after bootstrap and prior numbered staging migrations, in one transaction
-- with search_path set to the product schema, pg_catalog. Fail on lock contention.
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
CREATE INDEX IF NOT EXISTS idx_artifact_exports_tenant_artifact ON artifact_exports (tenant_id, artifact_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_tenant_artifact ON comparisons (tenant_id, artifact_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_tenant_candidate ON comparisons (tenant_id, candidate_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_agent_build ON evaluation_runs (tenant_id, agent_build_id);
