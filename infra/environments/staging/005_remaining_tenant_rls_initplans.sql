-- Ten unchanged ALL / TO PUBLIC tenant predicates; query-constant context.
-- Migration role search_path=fw_agenttest_lab,pg_catalog.
ALTER POLICY tenant_boundary ON agent_builds USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON artifact_exports USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON artifacts USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY case_results_tenant ON case_results USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON comparisons USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON dataset_sources USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON dataset_versions USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY evaluation_runs_tenant ON evaluation_runs USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON idempotency_keys USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
ALTER POLICY tenant_boundary ON memberships USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid) WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
