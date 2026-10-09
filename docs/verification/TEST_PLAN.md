# AgentTest Lab — Verifiable test and evaluation plan

| Test ID | Scenario | Fixture / setup | Expected acceptance result | Execution |
|---|---|---|---|---|
| EV-T01 | Dataset hash differs between runs | different version | comparability blocked | NOT RUN |
| EV-T02 | Missing baseline paired cases | mismatched case IDs | coverage flagged; no pass verdict | NOT RUN |
| EV-T03 | PII embedded in agent trace | secret fixture | redact/quarantine before log | NOT RUN |
| EV-T04 | AI judge disagrees with labeled corpus | adjudicated gold labels | calibration error reported | NOT RUN |
| EV-T05 | Tool call arguments invalid | malformed JSONL | schema rejection with location | NOT RUN |
| EV-T06 | Duplicate CI publish | retry after timeout | one logical verdict or safe reconcile | NOT RUN |

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
