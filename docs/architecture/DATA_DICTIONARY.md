# AgentTest Lab — Data model, relational constraints and transaction design

## Canonical relational aggregates (v4.1: authoritative)

Previous v4.0 terminology is mapped to **one** physical table per aggregate. Never generate two tables for one alias.

| Previous functional term | Canonical table | Mapping |
|---|---|---|
| `datasets` | `datasets` | Unchanged |
| `dataset_versions` | `dataset_versions` | Unchanged |
| `test_cases` | `test_cases` | Unchanged |
| `agent_builds` | `agent_builds` | Unchanged |
| `trace_imports` | `trace_imports` | Unchanged |
| `evaluation_runs` | `evaluation_runs` | Unchanged |
| `case_runs` | `case_results` | Renamed alias |
| `grader_results` | `grader_results` | Unchanged |
| `regression_comparisons` | `comparisons` | Renamed alias |
| `ci_verdicts` | `ci_verdicts` | Unchanged |

All canonical tables must have a physical column contract below; shared per-product platform tables are covered in governance.

## RLS and role design (not executed migration)
- Separate migration/owner role from API/worker read-write roles; application roles never hold BYPASSRLS/superuser or table owner privileges.
- Enable RLS and FORCE where suitable, separate `USING` and `WITH CHECK`; set `app.tenant_id` with `SET LOCAL` inside transactional request after auth membership resolution.
- Transaction-pool reused sessions must not inherit tenant variables. Test PgBouncer/pooled mode after selected provider is known.
- Compound FK + membership/policy validation is required despite RLS; no cross-tenant object keys or storage ACL inheritance.
- Synthetic two-tenant fixtures cover SELECT/INSERT/UPDATE/DELETE, foreign keys, joined views, workers and pooled connections.

## SQL transaction boundaries
1. Job accepted: domain validation + write `jobs` + `outbox` + `idempotency_records` in a **single commit**; return 202 only after commit succeeds.
2. Worker lease: visibility timeout/fencing token; dedupe message ID in inbox; at-least-once delivery with idempotent handlers.
3. Approval: compare `version` and content SHA, actor role+tenant, policy, expiry and external permission; conflicting writers return 409.
4. External effect: commit unique effect reservation → invoke outside DB transaction → store external ID/outcome; timeout -> `UNKNOWN_REMOTE` -> provider-specific lookup/reconciliation; never retry blindly.
5. Artifact: quarantine content until checksum, MIME, virus/format checks and final tenant-owner authorization; download intent scoped and revocation bounded by provider semantics.

## Domain-specific invariants and source column dictionary
Trace redaction before LLM judge; no arbitrary executable artifacts; separate customer tenant datasets and evaluation runs; never infer correctness from LLM judge alone.

# AgentTest Lab — proposed physical model, not executed DDL

## Shared physical schema model (applied independently per product)

All tenant-owned tables: `tenant_id UUID NOT NULL`, `id UUID NOT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `PRIMARY KEY (tenant_id,id)`.
A child FK must use `(tenant_id,parent_id) REFERENCES parent(tenant_id,id)`; foreign UUID alone is insufficient. Database roles: migration owner != API/worker; API/worker roles have no SUPERUSER/BYPASSRLS privileges. Proposed RLS uses `tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid` with `USING` and `WITH CHECK`; tenant context set `SET LOCAL` **inside a transaction** using server-verified membership, never client supplied. Connection pool reuse without transaction isolation is prohibited.

Other independent core tables for every product: `tenants`, `users`, `memberships`, `jobs`, `outbox_events`, `inbox_receipts`, `idempotency_records`, `audit_events`, `artifact_references` (tenant-scoped). Their schema and cleanup/retention must be supplied by the shared-platform contract before migration code.

Immutable audit records require explicit retention/legal basis. Event idempotency does not imply exactly-once external effects; use reconciliation and unique natural business keys. Soft deletion alone is not a privacy deletion implementation.


## Domain tables

### `datasets`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `name` | `text NOT NULL` |
| `owner_id` | `uuid NOT NULL` |
| `latest_version` | `int NOT NULL DEFAULT 0` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, name)`.
**Domain constraints:** case versions immutable.

### `dataset_versions`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `dataset_id` | `uuid NOT NULL` |
| `version_number` | `int NOT NULL` |
| `sha256` | `char(64) NOT NULL` |
| `case_count` | `int NOT NULL` |
| `artifact_key` | `text NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, dataset_id, version_number)`.
**Scoped FK:** `(tenant_id,dataset_id) -> datasets(tenant_id,id)`.
**Domain constraints:** duplicate case key rejected.

### `agent_builds`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `name` | `text NOT NULL` |
| `build_sha256` | `char(64) NOT NULL` |
| `tool_manifest_sha256` | `char(64) NOT NULL` |
| `prompt_version` | `text NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, build_sha256)`.
**Domain constraints:** manifest must be frozen.

### `evaluation_runs`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `dataset_version_id` | `uuid NOT NULL` |
| `agent_build_id` | `uuid NOT NULL` |
| `grader_sha256` | `char(64) NOT NULL` |
| `status` | `text NOT NULL` |
| `expected_case_count` | `int NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `INDEX (tenant_id, created_at DESC)`.
**Scoped FK:** `(tenant_id,dataset_version_id) -> dataset_versions(tenant_id,id)`; `(tenant_id,agent_build_id) -> agent_builds(tenant_id,id)`.
**Domain constraints:** cannot pass with incomplete case set.

### `case_results`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `run_id` | `uuid NOT NULL` |
| `test_case_id` | `uuid NOT NULL` |
| `case_key` | `text NOT NULL` |
| `grader_sha256` | `char(64) NOT NULL` |
| `grade_status` | `text NOT NULL` |
| `score` | `numeric(8,6)` |
| `trace_sha256` | `char(64) NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, run_id, case_key, grader_sha256)`.
**Scoped FK:** `(tenant_id,run_id) -> evaluation_runs(tenant_id,id)`; `(tenant_id,test_case_id) -> test_cases(tenant_id,id)`. Version invariant: test_cases.dataset_version_id MUST equal evaluation_runs.dataset_version_id. Enforce under DB transaction (constraint trigger or snapshot table) rather than trusting LLM-supplied identifiers.
**Domain constraints:** missing is not pass.

### `comparisons`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `baseline_run_id` | `uuid NOT NULL` |
| `candidate_run_id` | `uuid NOT NULL` |
| `policy_version` | `text NOT NULL` |
| `paired_case_count` | `int NOT NULL` |
| `missing_case_count` | `int NOT NULL` |
| `delta_score` | `numeric(8,6)` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, baseline_run_id, candidate_run_id, policy_version)`.
**Scoped FK:** `(tenant_id,baseline_run_id) -> evaluation_runs(tenant_id,id)`; `(tenant_id,candidate_run_id) -> evaluation_runs(tenant_id,id)`.
**Domain constraints:** same dataset case keys and grader criteria required.

### `ci_verdicts`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `comparison_id` | `uuid NOT NULL` |
| `verdict` | `text NOT NULL` |
| `policy_version` | `text NOT NULL` |
| `signed_artifact_sha256` | `char(64) NOT NULL` |
| `issued_at` | `timestamptz NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id, comparison_id, policy_version)`.
**Scoped FK:** `(tenant_id,comparison_id) -> comparisons(tenant_id,id)`.
**Domain constraints:** indeterminate is not pass.

## Transaction boundaries

- Creating a job: validate actor+tenant+resource; insert job and outbox in same PostgreSQL commit, then return HTTP 202. Broker delivery happens after transaction commit.
- External mutation: reserve unique business effect key and approval snapshot inside DB transaction; call external API outside transaction; reconcile remote effect ID after uncertain timeout.
- Final approval: optimistic `version`/If-Match plus exact content digest; reject stale updates.
- Tenant isolation test: same IDs searched under different tenant contexts must not disclose existence or associated storage objects.

## Schema proof not yet collected

Column design is not a generated migration and has not been executed against PostgreSQL. FK/index names, enum strategy, JSONB evidence fields, full SQL migration, query plans, retention and concurrency isolation must be validated during implementation.


> **DDL status:** conceptual physical design; no migration executed or database schema proved. Exact FK constraint names, indexes, query plans, row locks and RLS enforcement require G2/G4 evidence. The appended v3.2 dictionary is historic source input, not an executed implementation.


## v4.1 — Added physical model definitions and closure notes

These are **design-only table contracts**, not executed migrations. Explicit FK/index names, datatype behavior, RLS, and transaction isolation remain subject to PostgreSQL tests.

### `test_cases`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `dataset_version_id` | `UUID NOT NULL` |
| `case_key` | `TEXT NOT NULL` |
| `input_artifact_id` | `UUID NOT NULL` |
| `expected_assertions` | `JSONB NOT NULL` |
| `case_digest` | `CHAR(64) NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id,dataset_version_id,case_key)`.
**Scoped FK:** `(tenant_id,dataset_version_id) -> dataset_versions`; `(tenant_id,input_artifact_id) -> artifact_references`.
**Domain constraints:** Test case immutable once dataset version is sealed; input is never executable code.

### `trace_imports`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `dataset_version_id` | `UUID NOT NULL` |
| `artifact_id` | `UUID NOT NULL` |
| `trace_format` | `TEXT NOT NULL` |
| `schema_version` | `TEXT NOT NULL` |
| `status` | `TEXT NOT NULL` |
| `digest_sha256` | `CHAR(64) NOT NULL` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id,dataset_version_id,digest_sha256)`.
**Scoped FK:** `(tenant_id,dataset_version_id) -> dataset_versions`; `(tenant_id,artifact_id) -> artifact_references`.
**Domain constraints:** Redaction and tenancy validation before import; normalize timestamps but preserve source digest.

### `grader_results`

| Column | PostgreSQL design type / rule |
|---|---|
| `tenant_id` | `UUID NOT NULL` |
| `id` | `UUID NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `case_result_id` | `UUID NOT NULL` |
| `grader_key` | `TEXT NOT NULL` |
| `grader_version` | `TEXT NOT NULL` |
| `outcome` | `TEXT NOT NULL` |
| `score` | `NUMERIC(8,4)` |
| `evidence_sha256` | `CHAR(64)` |

**Keys/indexes:** `PRIMARY KEY (tenant_id,id)`; `UNIQUE (tenant_id,case_result_id,grader_key,grader_version)`.
**Scoped FK:** `(tenant_id,case_result_id) -> case_results`.
**Domain constraints:** Unknown/timeout/missing evidence must not be silently counted as pass; versioned grading policy required.


### Domain-specific mapping decisions

- `case_results` and `comparisons` are canonical persistence; business aliases in earlier text are deprecated.
- Dataset versions, imported traces, case results, and grader results form distinct auditables; no opaque aggregate JSON should replace source lineage.
