# Strict per-case exact-JSON regression policy (G3)

For independent CI acceptance, supply
`policy_version: strict-exact-no-regression-v1` when creating an AgentTest
comparison. This is an **opt-in policy**, not a silent change to
`deterministic-v1`, and does not execute external agent providers.

## Semantics

- Both immutable runs **must** reference the same dataset version.
- Both runs **must** have mode `exact-json-v1` and the same
  installed implementation digest. Caller-supplied `external-scores` runs are
  explicitly rejected under this policy.
- Existing completeness rules still apply: missing, timed-out or invalid
  case results fail the comparison.
- Every paired case's computed candidate score must be at least its own
  baseline score. Regressions are counted independently of the aggregate mean.
- The aggregate threshold is *also* enforced, but cannot override a
  per-case regression. A mean-neutral swap of success/failure across cases
  fails under this policy even if `delta_score == 0`.
- The canonical signed CI-verdict export includes a non-negative integer
  `regressed_case_count`. Offline verification requires that this field
  exists on strict-policy signed artifacts, lies within the paired case count,
  and equals zero on PASS.

This is **no-regression**, not **all-cases-pass**: an unchanged pre-existing
failed baseline case is not a new regression and might still yield PASS.
A separate product/owner acceptance decision must determine whether known
baseline failures are allowed. It never converts a caller-supplied score into
independently measured agent execution.

## Verification

Run the existing application/unit CI suite on disposable SQLite and PostgreSQL
and inspect `tests/integration/test_exact_grader.py` and
`tests/unit/test_verdict_verification.py`. These tests use fixed synthetic
dataset bytes, a real deterministic local JSON grader and offline generated
Ed25519 keys. They do not use a customer agent or live provider credentials.

**Production gate remains NO-GO** until owner-authorized provider traces,
authenticated tenant access, review of the exact grader rubric, and
independently verified signed output have succeeded.
