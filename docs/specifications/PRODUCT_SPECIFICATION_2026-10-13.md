# AgentTest Lab — revised owner product specification (2026-10-13)

**Source basis:** `AgentTest_Lab_Full_Detailed_v2.2.md`, `AgentTest_Lab_Expanded_Parent_v3.0.md`, `AgentTest_Lab_Ultra_Detailed_Extension.md` and the matching `IR/` catalogue in the owner's uploaded `ForgeWorks_5_Projects_Long_Narrative_plus_IR.zip`.

**Document state:** owner design requirements; not independent evidence of implemented or hosted functionality. This replaces the old bootstrap-era design-review and handoff prose, while preserving actual code/contracts/migrations/tests and dated audit evidence.

## Product scope
Reproducible deterministic AI-agent regression evaluation. It remains a separate backend service connected through the planned shared ForgeWorks front end; not a separate production domain.

## Owner P0 workflow / controls
1. Validate redacted trace and dataset schema and reject known secret patterns before any evaluation.
2. Pin dataset digest, agent build, prompt/tool versions and grader version; missing pins fail safely.
3. Run pure deterministic grader with no external calls; identical pins produce identical result; round scores to four decimals.
4. Optionally run a bounded AI judge only as separately labelled advisory; it never overrides deterministic CI verdict.
5. Compare exactly two runs from the same dataset version in P0 and calculate case regressions/improvements.
6. Enforce policy (default zero critical regressions and <= 2% case regression rate), signed or source-bound CI verdict and audit.
7. Export immutable separate deterministic vs advisory evidence with all input pins.

## Limits and non-goals
Owner-designed default regression gate is zero critical regressions and at most 2% per-case regression; validate thresholds and rounding with fixtures. No arbitrary remote agent execution.

## Implementation records and proof
The uploaded catalogue contains **360 IR IDs but 9 distinct topic patterns**, each repeated 40 times. ID count is not completion count. The distinctive topics are:

- 01. trace ingestion
- 02. redaction scan
- 03. version pinning
- 04. deterministic grading
- 05. judge invocation
- 06. paired comparison
- 07. regression check
- 08. CI verdict
- 09. evidence separation

For each topic, bind the implemented source file, requirement ID, positive/negative test, fixture digest, result, commit SHA, environment, reviewer and known limits. A generic repeated checklist is not a passed test.

## Production acceptance
The latest repository source and actual hosted runtime take precedence over an older blueprint's claim of implementation. Explicitly verify real identity and authorization, RLS/tenant isolation, bounded provider permissions, reconciliation, audit, backup/restore and domain-review acceptance before marking RELEASED. Current gate remains open until source-SHA-bound evidence is accepted.

See [shared-app boundary](../platform/ONE_APP_FIVE_SERVICES.md), [current gate evidence](../verification/CURRENT_GATE_EVIDENCE.md) and [hosted runbook](../../ops/runbooks/RUNTIME_RELEASE_VERIFICATION.md).
