# Score precision change advisory — 2026-10-13

**Status:** candidate implementation on `agent/agenttest-four-decimal-score-precision`; independent review reports no remaining findings. Code commit `ec3aae36812fdc126d8627dc6dbbecd2affe5855` passed all three GitHub checks, including the disposable PostgreSQL runtime test. This is not G1-E closure or production acceptance.

## Scope and policy boundary

The owner product specification requires four-decimal score precision. Scores in **new runs** are quantized with decimal `ROUND_HALF_EVEN` (ties-to-even); inputs are range-checked in `[0,1]` before quantization, and negative zero becomes `0.0`. Exact JSON grading still yields exactly `0.0` or `1.0`; its implementation bytes and digest are unchanged.

For a **new comparison**, valid scores for paired case keys are normalized to four decimals, then their full-precision decimal mean delta drives the threshold verdict. The persisted, API-visible, and signed/exported `delta` is rounded to four decimals. Thus a negative half-even tie can display `delta: 0.0000` while correctly producing `verdict: FAIL` at a zero threshold; the decision uses the underlying normalized-score mean, not the rounded display value. Unpaired rows never enter the means.

No historical data is backfilled: older case reads may retain their original precision. New comparisons normalize eligible historical case scores when calculating paired means; existing comparison records remain unchanged. `deterministic-v1`, the opt-in `strict-exact-no-regression-v1`, all threshold defaults, per-case policy semantics, and AI/provider behavior are unchanged. `ROUND_HALF_EVEN` is a recorded technical assumption, not an independently approved scoring rubric; maximum per-score quantization error is `0.00005`.

## Verification receipt

- Full local Python suite: **490 passed, 1 skipped**. The single skip is the disposable PostgreSQL integration test because no local disposable database was available.
- GitHub PR #38 on code head `ec3aae36812fdc126d8627dc6dbbecd2affe5855`: **3/3 checks passed**. The PostgreSQL runtime job executed `python -W error -m pytest tests/integration/test_postgres_runtime.py -q` and reported **1 passed in 1.62s** (not skipped).
- New tests cover half-even positive/negative ties, fail-closed threshold behavior, four-decimal persistence, HTTP readback, signed/exported delta, legacy rows without backfill, and exclusion of unpaired historical case rows from means.
- `verify_bootstrap.py`: **PASS**, 193 files scanned. `verify_contracts.py`: **PASS**, 13 operations. Independent OpenAPI validator: **PASS**. Generated SDK strict TypeScript check: **PASS**. Browser-session Node tests: **3 passed**. `git diff --check`: **PASS**.
- A documentation-only receipt commit follows the verified code commit; its new PR head must also finish all checks before any merge.

## Risks and remaining gates

At the half-even boundary, the displayed/exported four-decimal delta can be zero while the verdict is FAIL because the threshold decision correctly uses the unrounded mean. Historical case reads can also expose more than four decimals until those old runs age out; comparisons normalize their paired values without rewriting them. If the owner specifies a different tie convention, it requires compatibility and signed-evidence review. There is no database migration. Human rubric review, owner confirmation of the numeric convention, current-head CI, and all production gates remain open.
