# G1 runtime evidence — agenttest-lab

**Audit snapshot:** 2026-10-09 03:10 UTC  
**Audited current `main` source SHA:** `1de45357101caa63e7c21c03dbb0876e35cb7755`  
**Repository:** `ivan-agentic-labs/forgeworks-agenttest-lab`  
**Evidence boundary:** This record reports evidence that exists on the audited snapshot. It does not grant G1-D/G1-E approval and does not replace an independent reviewer.

## Decision boundary

- **G1-D:** `CONDITIONAL / PENDING SIGNOFF`; no domain, legal, owner, or independent-reviewer approval is fabricated.
- **G1-E:** `OPEN / BLOCKED` overall. The criteria below are individually labelled `VERIFIED` or `PASS_STATIC_LIMITED`; unavailable evidence remains `NOT_RUN` or `BLOCKED`.
- The PostgreSQL proof is disposable and synthetic only. The SQL candidate `30_fk_addendum_REVIEW_ONLY.sql` was not executed or approved.

## GitHub Actions evidence on the audited SHA

All URLs below are retained run links from the audited current `main` SHA and completed with conclusion `success`.

| Evidence | Workflow run | Head SHA | Relevant completed steps / limitation |
|---|---|---|---|
| Application tests and checks | [AgentTest MVP Application CI, run 37877966215](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877966215) | `1de45357101caa63e7c21c03dbb0876e35cb7755` | `python -W error -m pytest tests`; bootstrap/contracts/OpenAPI checks; `bash -n scripts/probe_disposable_postgres.sh` |
| Contract and independent OpenAPI checks | [G1 Contract Verification, run 37877966196](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877966196) | `1de45357101caa63e7c21c03dbb0876e35cb7755` | `verify_bootstrap.py`, `verify_contracts.py`, and `validate_openapi_independent.py` completed successfully |
| Empty disposable PostgreSQL DDL | [G1 Disposable PostgreSQL DDL Proof, run 37877994536](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877994536) | `1de45357101caa63e7c21c03dbb0876e35cb7755` | `bash scripts/probe_disposable_postgres.sh`; empty `forgeworks_g1` service reported 19 user tables |
| Non-owner two-tenant RLS | [same PostgreSQL run, run 37877994536](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877994536) | `1de45357101caa63e7c21c03dbb0876e35cb7755` | `bash scripts/test_disposable_postgres_rls.sh`; non-owner role proved unable to read or mutate the other tenant |

The workflows use pinned `actions/checkout` SHA `3d3c42e5aac5ba805825da76410c181273ba90b` and pinned `actions/setup-python` SHA `5fda3b95a4ea91299a34e894583c3862153e4b97` where applicable. Workflow success is evidence for the named commands only, not a production-readiness certification.

## Local command ledger

Commands were run from the repository root on the audited snapshot. Every command below exited `0`.

| Exact command | Observed outcome |
|---|---|
| `python -W error -m pytest tests` | `19 passed in 2.10s`, exit `0` |
| `python scripts/verify_bootstrap.py` | 94 files scanned; `errors: []`; exit `0` |
| `python scripts/verify_contracts.py` | 12 operations; Draft 2020-12 event schema; `errors: []`; exit `0` |
| `python scripts/validate_openapi_independent.py` | `Independent OpenAPI validator: PASS for openapi.yaml`; exit `0` |
| `bash -n scripts/probe_disposable_postgres.sh` | syntax check passed; exit `0` |
| `bash -n scripts/test_disposable_postgres_rls.sh` | syntax check passed; exit `0` |
| `node --check apps/web/app.js` | syntax check passed; exit `0` |
| `git diff --check` | no whitespace errors; exit `0` |

The local PostgreSQL service was not available in this sandbox; the disposable DDL/RLS outcomes above are therefore cited from the retained GitHub Actions run, not represented as a local run.

## Criterion table

| Criterion | Status | Evidence and scope | Residual limitation |
|---|---|---|---|
| Independent OpenAPI semantic validation | **VERIFIED** | Third-party `openapi-spec-validator` via `scripts/validate_openapi_independent.py`, locally and in the contract workflow on the audited SHA | Static contract validation only; generated client compilation and runtime interoperability are `NOT_RUN` |
| Event schema shape | **PASS_STATIC_LIMITED** | `scripts/verify_contracts.py` validated Draft 2020-12 schema and contract references locally and in CI | No message delivery, compatibility history, or consumer runtime proof |
| Empty disposable PostgreSQL migration/DDL | **VERIFIED** | PostgreSQL 17 service executed `00_role_candidate.sql`, `10_schema_candidate.sql`, and `20_grants_candidate.sql` from an empty database; run reported 19 user tables | Candidate SQL is not a production migration; `30_fk_addendum_REVIEW_ONLY.sql` remains unapproved and was not run |
| Non-owner two-tenant RLS SELECT/INSERT/UPDATE/DELETE negative test | **VERIFIED** | Application role `fw_agenttest_lab_rw`, `SET LOCAL app.tenant_id`, two synthetic tenants; other tenant was invisible and cross-tenant writes did not succeed | Does not prove every transaction-pool reset/bypass scenario or production concurrency |
| Auth and tenant negative tests | **PASS_STATIC_LIMITED** | Local pytest covers missing scope and wrong-tenant synthetic JWT denial (`403`) plus fail-closed terminal cases | HS256 fixture tokens and in-process API; real IdP/OIDC, provisioning, CSRF, revocation, and external access-control tests are `NOT_RUN` |
| E2E API/UI flow | **PASS_STATIC_LIMITED** | Five static UI/API tests exercise dataset, build, evaluation, comparison, signed verdict, and fail-closed paths through FastAPI `TestClient` | Not a real browser sandbox; browser isolation, egress, and deployed UI are `BLOCKED`/`NOT_RUN` |
| Worker reliability | **PASS_STATIC_LIMITED** | Seven local resilience tests cover idempotent retry, immutable version binding, incomplete-result terminal state, timeout/invalid result, determinism, and export handling | No separate worker process crash, network partition, load, region-failure, or production queue test |
| Artifact and integrity tests | **PASS_STATIC_LIMITED** | Local tests cover trace redaction/digest, immutable export SHA-256 and size, provenance binding, and idempotency | External object storage, upload/download integrity in a real provider, retention, and malware scanning are `NOT_RUN` |
| Bootstrap/sensitive-content check | **PASS_STATIC_LIMITED** | `verify_bootstrap.py` passed locally and in CI with no detected errors | Heuristic scan explicitly cannot certify absence of all secrets or personal data |

## Explicitly unavailable evidence

| Area | Status | Reason / next evidence required |
|---|---|---|
| Real IdP/OIDC session, provisioning, CSRF, revocation | **NOT_RUN** | No configured external IdP or retained integration run |
| Browser sandbox escape and egress control | **BLOCKED** | No independent runner/browser isolation environment or egress log |
| External storage/object-provider proof | **NOT_RUN** | The API uses synthetic-local storage semantics; no provider run exists |
| Generated client compilation | **NOT_RUN** | No generated-client toolchain or retained compile run |
| Legal, domain, privacy, accessibility, operations, cost/budget signoff | **BLOCKED** | Required accountable reviewers and signed records are absent |
| Production backup/restore and point-in-time recovery | **NOT_RUN** | No production datastore or restore drill exists |
| Owner/independent reviewer approval | **NOT_RUN** | No approval record may be inferred from CI success |

**Conclusion:** The audited snapshot supports narrow static and disposable-runtime evidence only. It does **not** support a full G1-D or G1-E PASS.
