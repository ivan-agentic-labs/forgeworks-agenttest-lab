# AgentTest Lab — Product Design Review (canonical summary)
**Status:** `DESIGN REVIEW CANDIDATE`. G1 domain signoff `BLOCKED`. This note **does not claim tested functionality**.

## Purpose and scope
**ICP:** AI engineering teams that version datasets and evaluate agent workflows.

**P0 workflow:** Import trace/dataset → lock dataset version → register agent build/grader → run deterministic grading → optional bounded LLM judge → analyze regression and export CI verdict.

**Explicit exclusions:** No free execution of arbitrary customer code on control plane; no definitive safety guarantee from a single judge.

**Subsystems:** Dataset importer/versioning; trace normalizer; graders; evaluator; comparative CI verdict; secure artifact export.

## API inventory (as currently specified)
| Method/path | `operationId` | Scope |
|---|---|---|
| `POST /v1/datasets` | `post_v1_datasets` | `dataset:create` |
| `POST /v1/datasets/{id}/versions` | `post_v1_datasets_id_versions` | `dataset:write` |
| `POST /v1/agent-builds` | `post_v1_agent_builds` | `build:write` |
| `POST /v1/evaluation-runs` | `post_v1_evaluation_runs` | `evaluation:run` |
| `GET /v1/evaluation-runs/{id}/cases` | `get_v1_evaluation_runs_id_cases` | `evaluation:read` |
| `POST /v1/evaluation-runs/{id}/comparisons` | `post_v1_evaluation_runs_id_comparisons` | `evaluation:compare` |
| `GET /v1/comparisons/{id}/ci-verdict` | `get_v1_comparisons_id_ci_verdict` | `evaluation:read` |
| `POST /v1/artifacts/upload-intents` | `post__v1_artifacts_upload_intents` | `artifact:create` |
| `POST /v1/artifacts/{artifact_id}/commit` | `post__v1_artifacts_artifact_id_commit` | `artifact:commit` |
| `GET /v1/artifacts/{artifact_id}` | `get__v1_artifacts_artifact_id` | `artifact:read` |
| `POST /v1/artifacts/{artifact_id}/download-intents` | `post__v1_artifacts_artifact_id_download_intents` | `artifact:download` |
| `GET /v1/jobs/{job_id}` | `get__v1_jobs_job_id` | `job:read` |

`openapi.yaml` is the source. These routes are not running. Remaining contract hardening: independent validator and SDK; verify existing cursor pagination semantics in runtime; security tests and example/runtime parity.

## Database inventory and handling
From candidate SQL (19 tables): `tenants`, `users`, `agent_builds`, `artifact_references`, `audit_events`, `datasets`, `grader_results`, `idempotency_records`, `inbox_receipts`, `jobs`, `memberships`, `outbox_events`, `test_cases`, `trace_imports`, `dataset_versions`, `evaluation_runs`, `case_results`, `comparisons`, `ci_verdicts`.

- Keep physical table names from `docs/verification/sql-candidates/10_schema_candidate.sql` as **candidate canonical**; historical aliases may not be implemented simultaneously.
- Apply `tenant_id` composite relations, invariant constraints and optimistic version where review/approval is relevant.
- Validate DDL in disposable PostgreSQL with owned migration role, nonowner runtime login role, multiple tenants; DDL presently unexecuted.

## Product-specific invariants and required negative proofs
| ID | Invariant | Negative case required | Evidence |
|---|---|---|---|
| `AT-INV-01` | Evaluation bound to immutable dataset+build+grader versions | Changing grader or dataset invalidates comparable verdict | Runtime test + reviewer signoff |
| `AT-INV-02` | Case result references valid test_case_id in selected dataset version | Cross-version test case FK/scope violation rejected | Runtime test + reviewer signoff |
| `AT-INV-03` | Judge disagreement and missing cases visible in aggregate | Injected null/missing grades cannot silently count PASS | Runtime test + reviewer signoff |
| `AT-INV-04` | No raw credential/PII in uploaded traces by default | Secret-labeled spans redacted/quarantined before grading | Runtime test + reviewer signoff |

## Modules/files planned for ownership (domain and adapters)
- `apps/api/src/agenttest_lab/domain/entities.py`
- `apps/api/src/agenttest_lab/infrastructure/persistence/models.py`
- `apps/api/src/agenttest_lab/infrastructure/persistence/repositories.py`
- `apps/api/src/agenttest_lab/infrastructure/llm/provider_adapter.py`
- `apps/api/src/agenttest_lab/domain/dataset_integrity.py`
- `apps/api/src/agenttest_lab/domain/grader_policy.py`
- `apps/api/src/agenttest_lab/domain/regression_policy.py`
- `apps/api/src/agenttest_lab/domain/privacy_filter.py`
- `apps/api/src/agenttest_lab/application/commands/register_agent_build.py`
- `apps/api/src/agenttest_lab/application/commands/register_dataset_version.py`
- `apps/api/src/agenttest_lab/application/commands/submit_evaluation.py`
- `apps/api/src/agenttest_lab/application/commands/compare_runs.py`
- `apps/api/src/agenttest_lab/infrastructure/trace/jsonl_reader.py`
- `apps/api/src/agenttest_lab/infrastructure/grader/deterministic_rules.py`
- `apps/api/src/agenttest_lab/infrastructure/judge/provider_adapter.py`
- `apps/api/src/agenttest_lab/infrastructure/ci/check_run_adapter.py`
- `apps/api/src/agenttest_lab/application/commands/commit_artifact.py`
- `apps/api/src/agenttest_lab/infrastructure/storage/object_store.py`
- `apps/api/src/agenttest_lab/infrastructure/security/tenant_context.py`
- `apps/api/src/agenttest_lab/infrastructure/persistence/outbox.py`

## Failure semantics
Judge unavailable: deterministic-only partial verdict, not fabricated completion. If downstream AI/provider fails, persist recoverable explicit job state and do not fabricate a successful output. Remote writes require `approval_snapshot` and idempotent effect ledger.

## Evidence and customer acceptance
**Required positive proof:** Reproducible regression metrics with documented grader agreement, trace provenance and CI guardrails.

**Main threats:** Grader bias/drift, dataset contamination/leakage, tenant trace exposure, arbitrary remote code.

**Data/IP/approval:** Processor/controller roles and vendor processing terms must be signed off before real data..

## P0 gates and signoff
- Founder/product owner: validates use-case acceptance from qualified user/buyer; **OPEN**.
- API reviewer: external OAS validation, SDK build, authorization negative tests; **NOT RUN**.
- DB/security reviewer: two-tenant SQL execution, constraints, RLS, IAM and sandbox where required; **NOT RUN**.
- Domain specialist: accessibility, finance, graders, provenance, GitHub contract per product; **OPEN**.
- Ops owner: cost/vendor, data policy, restore and incident evidence; **OPEN**.

**Outcome:** Documentation improved and canonical routes/tables inventoried; no independent product-domain approval or G1 PASS granted.
