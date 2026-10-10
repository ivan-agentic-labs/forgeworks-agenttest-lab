# Exact JSON grading evidence — 2026-10-10

Implemented server-side exact grading against verified dataset bytes, implementation hash enforcement, null/missing distinction, bounded output input, and combined output/trace evidence binding. Updated the HTTP contract and generated TypeScript SDK.

Local validation: 242 passed, 1 skipped with warnings treated as errors. The skipped test requires disposable PostgreSQL and is mandatory in CI. Thirty new tests cover JSON semantics, input budgets, caller-grade override resistance, source requirements, implementation identity, idempotency, comparison regression, null through HTTP, invalid traces, mixed grading modes, and changed implementations. PostgreSQL proof now includes computed PASS and FAIL cases, mixed-mode rejection, and actual regression verdicts; its result is established by the workflow rather than by the local skip.

No real agent execution, external provider usage, production deployment, or production data was involved. See the architecture document for precise boundaries.
