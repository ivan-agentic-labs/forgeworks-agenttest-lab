# MVP checkpoint — AgentTest Lab

Status: `TESTED` for deterministic synthetic evaluation.

Implemented: tenant-scoped dataset/version and build registration, immutable version references, deterministic grader, redacted synthetic trace digests, case results, baseline/candidate comparison, missing-case and delta policy, and CI verdict artifact digest.

Command: `PYTHONPATH=apps/api/src python -W error -m pytest tests/integration -q`  
Observed: 2 passed, exit 0, local Sandbox.

Not run: arbitrary remote agent execution (intentionally disabled), LLM judge, PostgreSQL/RLS, real trace import, external CI check-run, and production deployment. Missing/failed cases cannot become PASS in the comparison policy.
