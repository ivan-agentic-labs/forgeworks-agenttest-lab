# ADR 0003 — Bounded trace input and independently verified CI verdicts

Status: implemented engineering policy, 2026-10-11. External security/domain signoff remains open.

Unbounded traces and ambiguous JSON can consume excessive memory or attach evidence from another case. Add explicit 1 MiB per-trace, 4 MiB aggregate evaluation and 8 MiB actual request limits. Oversized HTTP requests return 413 before JSON decoding. Invalid trace records cannot yield passing evaluation cases. The OpenAPI `maxLength` documents the character limit; the parser also enforces the stricter UTF-8 encoded-byte limit.

Compatibility impact: callers sending larger inputs, duplicate JSON keys, non-finite values, wrong-case traces or a mismatched redacted digest must correct their input. Split large traces before submitting. This is an intentional rejection of unsupported input, not an assertion of full hostile-input resilience or gateway-level rate/time controls.

CI consumers verify exact signed bytes using an externally trusted Ed25519 public key and expected evaluation binding. No key from the verdict is trusted. Invalid verification exits 1; verified FAIL exits 2; only verified PASS exits 0. These signatures authenticate exports without claiming independent evaluation quality.

Rollback: revert the engineering commit and regenerate the SDK. Do not weaken trace provenance checks while relying on the CI gate; existing stored comparisons retain their original signed bytes. No database migration is needed.
