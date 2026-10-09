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
