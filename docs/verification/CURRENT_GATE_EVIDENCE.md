# Current G1/G2 evidence — 2026-10-09

The owner authorizes engineering directly on main. Owner design approval is permission to proceed; it is not an independent domain/security/legal signoff or a G1-E test result. Five repositories remain independent/public. No production deployment or customer data is included.

| Area | Status | Evidence and limit |
|---|---|---|
| G2 repository bootstrap | VERIFIED | Independent repositories, blueprint documentation, contracts, engineering config, SDK and Actions; committed contents read back from GitHub. |
| Contract semantics/client | VERIFIED, scoped | Independent OpenAPI validator, event-schema checks, generated TypeScript compilation and selected runtime response validation. This does not prove all application response paths. |
| Implemented PostgreSQL MVP runtime | VERIFIED, disposable | Migrations 001/002, non-owner runtime role, forced tenant RLS, negative access and product-specific concurrent commands. Design-candidate schema/FK addendum is not applied or accepted by these tests. |
| Logical restore | VERIFIED, disposable | Fresh database dump/restore, table digests, columns, constraints, RLS flags and restored non-owner membership/context behavior. Not PITR, regional failover or production RTO/RPO. |
| JWT/OIDC | PARTIAL | Fixed algorithms, mandatory claims/UUID tenant, expiry/issuer/audience checks, offline key rotation and explicit configuration. Real IdP sessions, provisioning, BFF, CSRF and revocation remain open. |
| Storage/real source bytes | PARTIAL | APIShield local bytes and DataReconcile/AgentTest persisted report/export downloads have integrity evidence. External storage scanning, retention/deletion and source/dataset ingestion remain open. |
| Remote sandbox/provider/GitHub App | BLOCKED | Remote execution/effects fail closed. No independent escape/egress/SSRF proof, installed product GitHub App or real provider quality/cost proof. |
| Domain/privacy/operations/acceptance | OPEN | Human-adjudicated corpus/thresholds, legal/domain/accessibility review, independent signoff and production operating evidence are not supplied. |
| G1-E overall | OPEN/BLOCKED | Individual test success is not whole-gate acceptance. |

## Exact source receipt

Source: `5a279750c65cc97ade3606ee9e0e66bbe1639b48`. This immutable receipt covers that exact source, including synthetic/disposable limits. Later engineering commits require their own CI results; current main workflow status is authoritative for those commits.

- [G1 Contract Verification](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37888172802): **success** at `5a279750c65cc97ade3606ee9e0e66bbe1639b48`.
- [AgentTest PostgreSQL Runtime Proof](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37888173138): **success** at `5a279750c65cc97ade3606ee9e0e66bbe1639b48`.
- [AgentTest MVP Application CI](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37888172803): **success** at `5a279750c65cc97ade3606ee9e0e66bbe1639b48`.

- AgentTest PostgreSQL Runtime Proof: 1 passed in 1.09s
- AgentTest PostgreSQL Runtime Proof: {"check": "disposable logical restore and restored membership/RLS", "limits": "Not PITR, regional failover, production RTO/RPO or operational signoff", "result": "PASS", "rows": 27, "tables": 11}
- AgentTest MVP Application CI: ======================== 35 passed, 1 skipped in 1.87s =========================

## Current product scope

Disposable logical restore verification now compares actual tenant RLS policy expressions/role bindings, table grants, and non-internal trigger definitions/functions, in addition to row digests, columns, constraints and RLS flags. This remains a logical disposable proof, not PITR, regional failover or production operating acceptance.

Persist supplied case results, compare immutable bindings, sign Ed25519 verdicts and download actual persisted exports. External uploads remain quarantined; dataset source ingestion and external agent execution are unproven.

## Remaining dependency and implementation register

### Verified dataset ingestion continuation, 2026-10-09

Version creation accepts exact inline UTF-8 JSONL with case_key/input/expected per row, verifies digest/count, rejects duplicate JSON and case keys, non-finite numbers and structural budgets, and atomically persists immutable tenant-scoped dataset source snapshots. Migration 003 gives runtime SELECT/INSERT only with forced RLS and tenant-qualified FK. Evaluation re-verifies the snapshot and uses its actual ordered case keys. Missing source versions fail closed outside explicitly seeded development/test stores. artifact_id remains caller metadata and is not a verified external storage object. Supplied case scores are caller evidence, not proof of provider execution; external storage, provider adapter and observed evaluation quality remain open.

### Evaluation evidence continuation, 2026-10-09

Duplicate case keys now fail instead of silently overwriting evidence; unknown keys fail instead of being ignored. Current metadata-only versions still define positional `case-1` through `case-N` keys, not verified uploaded datasets. Missing expected results remain PARTIAL with null scores. Dataset/run budgets are 1000 cases, keys are bounded to 128 characters, and seeds must fit signed 64-bit PostgreSQL storage. Regression tests verify typed failures and no persisted run on invalid case binding. Actual dataset-byte ingestion and provider execution remain unfinished.

1. Configure a real IdP and provisioned internal identities; finish BFF/session/CSRF/revocation and test them. This includes unfinished code, not only credentials.
2. Configure external private storage/scanning/retention/deletion and implement remaining source/dataset/upload adapters; do not treat placeholder metadata or quarantined objects as verified bytes.
3. Supply an isolated runner/network policy and product GitHub App configuration; implement and prove sandbox, webhook/revocation and approval-bound remote effects before enabling them.
4. Supply approved evaluation corpora/thresholds and provider budget; implement real source/scanner/agent paths and establish observed quality/cost/load/recovery results.
5. Obtain domain/legal/privacy/operations/independent acceptance. Production remains outside this authorized execution scope.

No background completion, production readiness or full-G1-E PASS is asserted.

## Runtime release controls — engineering continuation 2026-10-12

This change implements hosted revision/fingerprint identity, bounded private metrics, sanitized request logs, a fixed-origin deployment proof and a trusted-key production acceptance validator. Negative tests cover tampered/wrong-target receipts, open controls, invalid timing, staging relabelling, metric secrecy and incomplete responses. The production template remains unsigned and OPEN; no actual reviewer, production receipt, or authenticated hosted acceptance is asserted.

The local executor disconnected before publication. The publishable patch was reconstructed through the GitHub API; GitHub Actions at its exact committed bytes is the required regression evidence before promotion. Earlier local test counts are not proof for the reconstructed commit. Read the exact CI jobs and deployment source pin for current status.
