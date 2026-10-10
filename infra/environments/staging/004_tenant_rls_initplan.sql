-- Preserve tenant equality for datasets read/write; cache session setting once.
-- Migration only with search_path=fw_agenttest_lab,pg_catalog.
ALTER POLICY datasets_tenant ON datasets
  USING (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid)
  WITH CHECK (tenant_id = NULLIF((SELECT current_setting('app.tenant_id', true)), '')::uuid);
