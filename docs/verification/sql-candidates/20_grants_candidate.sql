-- DESIGN CANDIDATE FOR DISPOSABLE PROOF ONLY.
-- Privileges apply exclusively to tenant-scoped tables protected by RLS.
-- Keep global `tenants` and `users` restricted to a separately audited provisioning path.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_builds TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE artifact_references TO fw_agenttest_lab_rw;
-- Audit events: append-only for application role, no direct update/delete.
REVOKE ALL ON TABLE audit_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON TABLE audit_events FROM fw_agenttest_lab_rw;
GRANT SELECT, INSERT ON TABLE audit_events TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE datasets TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE grader_results TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE idempotency_records TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE inbox_receipts TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE jobs TO fw_agenttest_lab_rw;
-- G1-D conditional restriction: membership writes disabled for generic app role.
-- Identity/admin provisioning service requires a separate reviewed role and authz gate.
REVOKE INSERT, UPDATE, DELETE ON TABLE memberships FROM fw_agenttest_lab_rw;
GRANT SELECT ON TABLE memberships TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE outbox_events TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE test_cases TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE trace_imports TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE dataset_versions TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE evaluation_runs TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE case_results TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE comparisons TO fw_agenttest_lab_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ci_verdicts TO fw_agenttest_lab_rw;

-- Global identity tables must not be readable via PUBLIC (disposable-proof safeguard).
REVOKE ALL ON TABLE users, tenants FROM PUBLIC;
