# Deterministic JSON grader

Set `grader_config.mode` to `exact-json-v1` and supply `observed_output` on each case result. The server derives PASS/1.0 or FAIL/0.0 from the immutable, SHA-verified dataset's `expected` value. Caller `status` and `score` are ignored in this mode. Omitted output is MISSING with no score; explicit JSON null is a real output. Missing cases keep the run PARTIAL. Invalid trace evidence still invalidates the result.

Use the installed `agenttest_lab.domain.exact_grader.GRADER_SHA256` as `grader_sha256`. This is SHA-256 of the executable grader module's exact source bytes. An arbitrary declared grader identity is rejected before a run is written. The mode is included in the stored configuration hash; configuration and implementation hashes remain in comparison bindings.

Object key order is ignored, array order is significant, JSON numbers compare numerically (1 equals 1.0), and booleans are distinct from numbers. Strings compare exactly without normalization. No fuzzy scoring, LLM judge, code evaluation, or external tool execution occurs. Each observed output is limited to 1 MiB, 20,000 nodes and depth 32; combined outputs are limited to 4 MiB. Nonfinite numbers, invalid Unicode, and non-JSON values are rejected.

Persisted result evidence hashes bind the case, immutable dataset hash, actual output hash, calculated grade, and validated trace hash if present. Raw output is not newly stored. A hash is not encryption; low-entropy values can still be guessed. The trace_digest field contains this combined grading evidence hash in exact mode, rather than only the trace hash. A supplied trace_digest is verified against trace_jsonl before combination; a caller digest without trace bytes is not used as evidence in this mode.

Comparisons require the same grading mode. Exact JSON comparisons also require the same grader implementation hash; changing the implementation requires a freshly graded baseline. This prevents caller-supplied scores from passing against a server-graded baseline.

The default `external-scores` mode preserves existing integrations that submit externally calculated grades. This mode does not validate their grader computation. Metadata-only fixture versions and synthetic result fallback are never accepted for exact grading.

Scores in newly created runs use four decimal places with deterministic decimal `ROUND_HALF_EVEN`; exact-json outputs remain exactly `0.0` or `1.0`. Historical case rows are not backfilled, so case reads for those runs may retain greater precision. New comparisons normalize paired historical and new case scores to four decimal places, evaluate the threshold using the unrounded mean of those normalized paired scores, and store/sign the mean delta rounded to four decimal places. Existing comparison records remain unchanged. This precision rule does not select a regression policy or change any policy threshold.

This feature grades caller-recorded outputs. It does not prove an agent actually generated them, connect to an agent provider, or establish that the reference dataset is objectively correct. Build and dataset provenance still need independent ownership controls. Live isolated agent execution remains a separate unfinished integration.
