-- REVIEW CANDIDATE ONLY. SQLAlchemy PostgreSQL dialect compilation, NO live PostgreSQL.
-- NOT APPROVED AS EXECUTABLE MIGRATION. fw_agenttest_lab_rw must be created with NOLOGIN,
-- checked grants and no table ownership or BYPASSRLS. A distinct migration
-- owner deploys schema. API service must authenticate membership, set SET LOCAL
-- app.tenant_id within transaction, and never pass SQL through to users.
-- Global tenants/users need dedicated authorization rules (not generic RLS).
-- No automatic fw_agenttest_lab_rw GRANT is provided; least-privilege permissions undecided.
-- Audit events require retention controls and legal review.
-- PostgreSQL version/vendor and migration ordering are not yet approved.

CREATE TABLE tenants (
	id UUID NOT NULL, 
	slug TEXT NOT NULL, 
	status TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
)

;


CREATE TABLE users (
	id UUID NOT NULL, 
	issuer TEXT NOT NULL, 
	subject TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_users_issuer_sub UNIQUE (issuer, subject)
)

;


CREATE TABLE agent_builds (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	name TEXT NOT NULL, 
	build_sha256 CHAR(64) NOT NULL, 
	tool_manifest_sha256 CHAR(64) NOT NULL, 
	prompt_version TEXT NOT NULL, 
	CONSTRAINT pk_agent_builds_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_agent_builds_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_agent_builds_tenant_id_build_sha256 UNIQUE (tenant_id, build_sha256)
)

;


CREATE TABLE artifact_references (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	object_key TEXT NOT NULL, 
	sha256 CHAR(64) NOT NULL, 
	media_type TEXT NOT NULL, 
	status TEXT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_artifact_references PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_artifact_references_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_artifact_key UNIQUE (tenant_id, object_key)
)

;


CREATE TABLE audit_events (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	actor_key TEXT NOT NULL, 
	action TEXT NOT NULL, 
	resource_key TEXT NOT NULL, 
	data_class TEXT NOT NULL, 
	trace_id TEXT, 
	payload JSONB NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_audit_events_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

;


CREATE TABLE datasets (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	name TEXT NOT NULL, 
	owner_id UUID NOT NULL, 
	latest_version INTEGER DEFAULT 0 NOT NULL, 
	CONSTRAINT pk_datasets_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_datasets_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_datasets_tenant_id_name UNIQUE (tenant_id, name)
)

;


CREATE TABLE grader_results (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	case_result_id UUID NOT NULL, 
	grader_key TEXT NOT NULL, 
	grader_version TEXT NOT NULL, 
	outcome TEXT NOT NULL, 
	score NUMERIC(8, 4), 
	evidence_sha256 CHAR(64), 
	CONSTRAINT pk_grader_results_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_grader_results_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_grader_results_tenant_id_case_result_id_grader_key_8a1f27b0 UNIQUE (tenant_id, case_result_id, grader_key, grader_version)
)

;


CREATE TABLE idempotency_records (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	actor_key TEXT NOT NULL, 
	command_name TEXT NOT NULL, 
	idempotency_key TEXT NOT NULL, 
	request_sha256 CHAR(64) NOT NULL, 
	response_status INTEGER, 
	response_json JSONB, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_idempotency_records PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_idempotency_records_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_idempotency_scope UNIQUE (tenant_id, actor_key, command_name, idempotency_key)
)

;


CREATE TABLE inbox_receipts (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	consumer_name TEXT NOT NULL, 
	event_key TEXT NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_inbox_receipts PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_inbox_receipts_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_inbox_dedupe UNIQUE (tenant_id, consumer_name, event_key)
)

;


CREATE TABLE jobs (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	kind TEXT NOT NULL, 
	status TEXT NOT NULL, 
	version INTEGER DEFAULT 1 NOT NULL, 
	created_by UUID, 
	CONSTRAINT pk_jobs PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_jobs_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)

;


CREATE TABLE memberships (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	user_id UUID NOT NULL, 
	role TEXT NOT NULL, 
	status TEXT NOT NULL, 
	CONSTRAINT pk_memberships PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_memberships_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_memberships_user FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT uq_memberships_user UNIQUE (tenant_id, user_id)
)

;


CREATE TABLE outbox_events (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	event_type TEXT NOT NULL, 
	event_version INTEGER DEFAULT 1 NOT NULL, 
	payload JSONB NOT NULL, 
	event_key TEXT NOT NULL, 
	delivered_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_outbox_events PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_outbox_events_tenant FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_outbox_key UNIQUE (tenant_id, event_key)
)

;


CREATE TABLE test_cases (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	dataset_version_id UUID NOT NULL, 
	case_key TEXT NOT NULL, 
	input_artifact_id UUID NOT NULL, 
	expected_assertions JSONB NOT NULL, 
	case_digest CHAR(64) NOT NULL, 
	CONSTRAINT pk_test_cases_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_test_cases_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_test_cases_tenant_id_dataset_version_id_case_key UNIQUE (tenant_id, dataset_version_id, case_key)
)

;


CREATE TABLE trace_imports (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	dataset_version_id UUID NOT NULL, 
	artifact_id UUID NOT NULL, 
	trace_format TEXT NOT NULL, 
	schema_version TEXT NOT NULL, 
	status TEXT NOT NULL, 
	digest_sha256 CHAR(64) NOT NULL, 
	CONSTRAINT pk_trace_imports_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_trace_imports_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT uq_trace_imports_tenant_id_dataset_version_id_digest_sha256 UNIQUE (tenant_id, dataset_version_id, digest_sha256)
)

;


CREATE TABLE dataset_versions (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	dataset_id UUID NOT NULL, 
	version_number INTEGER NOT NULL, 
	sha256 CHAR(64) NOT NULL, 
	case_count INTEGER NOT NULL, 
	artifact_key TEXT NOT NULL, 
	CONSTRAINT pk_dataset_versions_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_dataset_versions_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_dataset_versions_tenant_id_dataset_id FOREIGN KEY(tenant_id, dataset_id) REFERENCES datasets (tenant_id, id), 
	CONSTRAINT uq_dataset_versions_tenant_id_dataset_id_version_number UNIQUE (tenant_id, dataset_id, version_number)
)

;


CREATE TABLE evaluation_runs (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	dataset_version_id UUID NOT NULL, 
	agent_build_id UUID NOT NULL, 
	grader_sha256 CHAR(64) NOT NULL, 
	status TEXT NOT NULL, 
	expected_case_count INTEGER NOT NULL, 
	CONSTRAINT pk_evaluation_runs_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_evaluation_runs_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_evaluation_runs_tenant_id_dataset_version_id FOREIGN KEY(tenant_id, dataset_version_id) REFERENCES dataset_versions (tenant_id, id), 
	CONSTRAINT fk_evaluation_runs_tenant_id_agent_build_id FOREIGN KEY(tenant_id, agent_build_id) REFERENCES agent_builds (tenant_id, id)
)

;


CREATE TABLE case_results (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	run_id UUID NOT NULL, 
	test_case_id UUID NOT NULL, 
	case_key TEXT NOT NULL, 
	grader_sha256 CHAR(64) NOT NULL, 
	grade_status TEXT NOT NULL, 
	score NUMERIC(8, 6), 
	trace_sha256 CHAR(64) NOT NULL, 
	CONSTRAINT pk_case_results_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_case_results_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_case_results_tenant_id_run_id FOREIGN KEY(tenant_id, run_id) REFERENCES evaluation_runs (tenant_id, id), 
	CONSTRAINT fk_case_results_tenant_id_test_case_id FOREIGN KEY(tenant_id, test_case_id) REFERENCES test_cases (tenant_id, id), 
	CONSTRAINT uq_case_results_tenant_id_run_id_case_key_grader_sha256 UNIQUE (tenant_id, run_id, case_key, grader_sha256)
)

;


CREATE TABLE comparisons (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	baseline_run_id UUID NOT NULL, 
	candidate_run_id UUID NOT NULL, 
	policy_version TEXT NOT NULL, 
	paired_case_count INTEGER NOT NULL, 
	missing_case_count INTEGER NOT NULL, 
	delta_score NUMERIC(8, 6), 
	CONSTRAINT pk_comparisons_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_comparisons_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_comparisons_tenant_id_baseline_run_id FOREIGN KEY(tenant_id, baseline_run_id) REFERENCES evaluation_runs (tenant_id, id), 
	CONSTRAINT fk_comparisons_tenant_id_candidate_run_id FOREIGN KEY(tenant_id, candidate_run_id) REFERENCES evaluation_runs (tenant_id, id), 
	CONSTRAINT uq_comparisons_tenant_id_baseline_run_id_candidate_ru_54cf899e UNIQUE (tenant_id, baseline_run_id, candidate_run_id, policy_version)
)

;


CREATE TABLE ci_verdicts (
	tenant_id UUID NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	comparison_id UUID NOT NULL, 
	verdict TEXT NOT NULL, 
	policy_version TEXT NOT NULL, 
	signed_artifact_sha256 CHAR(64) NOT NULL, 
	issued_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_ci_verdicts_tenant_id_id PRIMARY KEY (tenant_id, id), 
	CONSTRAINT fk_ci_verdicts_tenant_id FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_ci_verdicts_tenant_id_comparison_id FOREIGN KEY(tenant_id, comparison_id) REFERENCES comparisons (tenant_id, id), 
	CONSTRAINT uq_ci_verdicts_tenant_id_comparison_id_policy_version UNIQUE (tenant_id, comparison_id, policy_version)
)

;

-- INDEXES
CREATE INDEX "ix_evaluation_runs_tenant_id_created_at_DESC" ON evaluation_runs (tenant_id, created_at DESC);

-- RLS POLICIES (candidate, role not yet provisioned)
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY p_memberships_tenant ON memberships FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY p_jobs_tenant ON jobs FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;
CREATE POLICY p_outbox_events_tenant ON outbox_events FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE inbox_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE inbox_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY p_inbox_receipts_tenant ON inbox_receipts FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE idempotency_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_records FORCE ROW LEVEL SECURITY;
CREATE POLICY p_idempotency_records_tenant ON idempotency_records FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
-- Audit is append-only for the application role; owner/retention procedure is separate.
CREATE POLICY p_audit_events_read ON audit_events FOR SELECT TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
CREATE POLICY p_audit_events_append ON audit_events FOR INSERT TO fw_agenttest_lab_rw WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE artifact_references ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_references FORCE ROW LEVEL SECURITY;
CREATE POLICY p_artifact_references_tenant ON artifact_references FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets FORCE ROW LEVEL SECURITY;
CREATE POLICY p_datasets_tenant ON datasets FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY p_dataset_versions_tenant ON dataset_versions FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE agent_builds ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_builds FORCE ROW LEVEL SECURITY;
CREATE POLICY p_agent_builds_tenant ON agent_builds FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY p_evaluation_runs_tenant ON evaluation_runs FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE case_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_results FORCE ROW LEVEL SECURITY;
CREATE POLICY p_case_results_tenant ON case_results FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE comparisons ENABLE ROW LEVEL SECURITY;
ALTER TABLE comparisons FORCE ROW LEVEL SECURITY;
CREATE POLICY p_comparisons_tenant ON comparisons FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE ci_verdicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ci_verdicts FORCE ROW LEVEL SECURITY;
CREATE POLICY p_ci_verdicts_tenant ON ci_verdicts FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE test_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_cases FORCE ROW LEVEL SECURITY;
CREATE POLICY p_test_cases_tenant ON test_cases FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE trace_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_imports FORCE ROW LEVEL SECURITY;
CREATE POLICY p_trace_imports_tenant ON trace_imports FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
ALTER TABLE grader_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE grader_results FORCE ROW LEVEL SECURITY;
CREATE POLICY p_grader_results_tenant ON grader_results FOR ALL TO fw_agenttest_lab_rw USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
