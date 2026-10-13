# AgentTest Lab — Complete Detailed Project Specification

**Version:** 2.2.0-detailed-full  
**Date:** 2026-10-13  
**Status:** FINAL  

> AgentTest Lab provides reproducible evaluation of AI agents. Deterministic grading is the sole source of truth. An optional AI judge is advisory only and cannot override deterministic results.

---

## 1. Executive Definition

Teams upload redacted traces and versioned datasets. The system pins every input that can affect the outcome, runs a pure deterministic grader, optionally invokes a bounded judge, compares runs when requested, and produces a CI verdict with coverage and regression information.

---

## 2. Detailed Workflow

1. Ingest traces. Schema validation and secret/redaction scan run immediately. Detected secrets cause rejection.
2. Pin dataset digest, agent build, prompt version, tool versions, and grader version. Missing pins fail the run.
3. Execute deterministic grader. It must return identical results for identical pins. Scores are rounded to 4 decimal places.
4. Optionally run AI judge under strict input limits. Result is stored separately and labeled advisory.
5. For paired comparison (exactly two runs in P0), compute regressions and improvements.
6. Apply regression policy (default: 0 critical regressions and ≤ 2% case regression rate).
7. Emit CI verdict bound to the run digest.
8. Evidence retains both deterministic and advisory results.

---

## 3. Redaction and Pinning

All potentially sensitive string fields must be redacted or digested before upload. Known secret patterns trigger automatic rejection.  
Every run records the full set of pins. This is required for reproducibility and meaningful comparison.

---

## 4. Grader and Judge Contract

Grader is a pure function with no external calls.  
Judge output never changes the deterministic pass/fail or the CI verdict unless the workspace explicitly configures it as advisory display only.  
Paired runs must share the same dataset version.

---

## 5. Closing

These rules are final for P0. AgentTest Lab will not execute arbitrary code and will not treat model output as ground truth.

*End of AgentTest Lab Complete Detailed Specification*
