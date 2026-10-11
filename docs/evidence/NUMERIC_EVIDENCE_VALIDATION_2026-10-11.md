# Strict numeric evidence validation — 2026-10-11

Baseline 11fde128de2cb4d103434fa088beb91650de5cdc coerced boolean score true to 1.0 and string threshold "0.5" to 0.5. The valid JSON token 1e400 became infinity; default validation error serialization returned HTTP 500 for grader/run/comparison thresholds.

The API now requires strict finite numeric score and threshold inputs. Integer JSON numbers remain accepted as numeric scores; optional score/run/comparison thresholds remain nullable. Existing score range handling in the store remains unchanged. Validation failures return a stable INVALID_REQUEST problem envelope without echoing raw values or sensitive request input. This applies to HTTP input; direct internal store callers are outside this input-model proof.

26 regressions: 20 rejected-input HTTP cases across score and three threshold surfaces, five valid-number cases, and nullable compatibility. Rejected requests are checked for no new runs, comparisons or case rows. Baseline: 20 fail, 6 pass. Candidate: 26 pass. Full local Python suite: 296 pass, 1 PostgreSQL test skipped; Node session tests: 3 pass. Bootstrap/static contracts and independent OpenAPI validation pass. Required GitHub PostgreSQL, contract and application CI must pass before merge. No staging identity/business-flow or deployment/production acceptance is claimed.
