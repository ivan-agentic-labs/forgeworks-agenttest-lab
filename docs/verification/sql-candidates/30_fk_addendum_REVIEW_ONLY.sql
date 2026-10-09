-- DESIGN-ONLY SQL. NOT VALIDATED BY A LIVE POSTGRESQL INSTANCE.
-- Review business semantics, existing data, and ON DELETE decision before adoption.
-- Apply after 10_schema_candidate.sql, on an isolated disposable database only.

ALTER TABLE grader_results
  ADD CONSTRAINT fk_g1_grader_results_case_result_id
  FOREIGN KEY (tenant_id, case_result_id)
  REFERENCES case_results (tenant_id, id)
  ON DELETE RESTRICT;

ALTER TABLE test_cases
  ADD CONSTRAINT fk_g1_test_cases_dataset_version_id
  FOREIGN KEY (tenant_id, dataset_version_id)
  REFERENCES dataset_versions (tenant_id, id)
  ON DELETE RESTRICT;

ALTER TABLE test_cases
  ADD CONSTRAINT fk_g1_test_cases_input_artifact_id
  FOREIGN KEY (tenant_id, input_artifact_id)
  REFERENCES artifact_references (tenant_id, id)
  ON DELETE RESTRICT;

ALTER TABLE trace_imports
  ADD CONSTRAINT fk_g1_trace_imports_dataset_version_id
  FOREIGN KEY (tenant_id, dataset_version_id)
  REFERENCES dataset_versions (tenant_id, id)
  ON DELETE RESTRICT;

ALTER TABLE trace_imports
  ADD CONSTRAINT fk_g1_trace_imports_artifact_id
  FOREIGN KEY (tenant_id, artifact_id)
  REFERENCES artifact_references (tenant_id, id)
  ON DELETE RESTRICT;
