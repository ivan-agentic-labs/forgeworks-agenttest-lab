# AgentTest Lab — Verifiable test and evaluation plan

| Test ID | Scenario | Fixture / setup | Expected acceptance result | Execution |
|---|---|---|---|---|
| EV-T01 | Dataset hash differs between runs | different version | comparability blocked | **PASS_LOCAL** — `APP_ENV=test python -W error -m pytest tests/resilience/test_worker_reliability.py::test_comparison_rejects_mutated_or_different_immutable_dataset_version -q`; disposable SQLite/API fixture rejects different immutable version hashes. No external dataset or hosted comparison. |
| EV-T02 | Missing baseline paired cases | mismatched case IDs | coverage flagged; no pass verdict | **PASS_LOCAL** — `APP_ENV=test python -W error -m pytest tests/eval/test_plan_local.py -q` (`test_missing_baseline_pair_is_coverage_gap_and_fails_comparison`); synthetic exact-JSON run records the omitted case as `MISSING` and comparison exports `FAIL`. No production corpus. |
| EV-T03 | PII embedded in agent trace | secret fixture | redact/quarantine before log | **PASS_LOCAL** — `APP_ENV=test python -W error -m pytest tests/unit/test_trace_boundaries.py -k 'nested_structured_pii_fields_are_redacted_before_hashing or provider_credentials_are_redacted_in_neutral_trace_fields' -q`; synthetic trace redaction removes structured PII/provider credentials before the redacted digest. This does not validate a production log sink. |
| EV-T04 | AI judge disagrees with labeled corpus | adjudicated gold labels | calibration error reported | **NOT_RUN** — no local AI-judge/calibration boundary or adjudicated gold corpus exists; no behavior inferred or external provider called. |
| EV-T05 | Tool call arguments invalid | malformed JSONL | schema rejection with location | **NOT_RUN** — the current repository has no implemented tool-argument JSONL schema boundary with a location-bearing rejection contract; no substitute trace test is claimed. |
| EV-T06 | Duplicate CI publish | retry after timeout | one logical verdict or safe reconcile | **PARTIAL_LOCAL** — `APP_ENV=test python -W error -m pytest tests/integration/test_hardening.py::test_comparison_binds_versions_and_creates_export_artifact -q`; repeated comparison idempotency key returns the same logical export and conflicting reuse is rejected. No timeout/failure-injection or external CI publisher was exercised. |

## Coverage and execution gates
- Unit: every pure domain invariant, deterministic cross-validation, state guard, authorization policy and financial arithmetic where relevant.
- Contract: OpenAPI semantic validation, JSON Schema, request/response/error examples, client generation, event backwards compatibility.
- Integration: PostgreSQL tenant/RLS/FKs/transactions, storage capability, OIDC+BFF flow, inbox/outbox/queue, provider-scoped permissions.
- E2E: five canonical success/failure paths including human approval and result retrieval; use separate tenants and consented/synthetic data.
- Agent evaluation: frozen labeled corpus with human adjudication, baseline comparison, model/version pinning, typed outputs, prompt injection and tool abuse fixtures.
- Security: SAST/SCA/secret/DAST and cross-tenant negative tests, SSRF sandbox escape, revocation, external effect uncertainty.
- Reliability: 2x planned load (tentative), forced worker crash, network partitions, point-in-time DB restore, region failure simulation.

## Metrics to establish on actual runs
- paired-case coverage
- grader reproducibility on fixed fixtures
- agreement with adjudicated gold set
- critical policy violation recall
- CI verdict stability across reruns

**No arbitrary success numbers:** Define threshold from buyer risk tolerance and pilot corpus before G1. Store observed accuracy and sample size, confidence/coverage when meaningful, source hash, run logs, costs, p95, failure distribution. A test case being designed is not a passed test.

## Evidence format
`{test_id, requirement_id, revision_sha, input_fixture_sha, dataset_version, environment, exact_command, expected, observed, pass_fail, reviewer, trace_id, issues}`.
