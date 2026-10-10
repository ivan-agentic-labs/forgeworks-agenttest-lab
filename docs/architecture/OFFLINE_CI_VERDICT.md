# Offline CI verdict verification

The API's `/v1/comparisons/{id}/ci-verdict` response can be checked without contacting the API again. Save the response as a JSON envelope. Supply an Ed25519 public key in PEM format from trusted CI configuration. Never obtain the trusted key or expected binding from the envelope being verified.

```bash
python scripts/verify_ci_verdict.py \
  --envelope verdict-envelope.json \
  --public-key trusted-verdict-public.pem \
  --expected-binding expected-ci-binding.json
```

Exit codes: `0` means verified PASS, `2` means verified FAIL, and `1` means invalid input, signature, key, digest or binding. CI must require exit code `0`; it must not use `continue-on-error` or ignore the command's status.

The independently configured expected-binding JSON must contain:

- `dataset_version_id`, `baseline_run_id`, `candidate_run_id`;
- `baseline_build_id`, `candidate_build_id`;
- `baseline_grader_sha256`, `candidate_grader_sha256`;
- `baseline_grader_config_sha256`, `candidate_grader_config_sha256`;
- `policy_version`, `threshold` (finite number between 0 and 1).

Additional expected binding fields are also compared. Pin these values from the CI job's intended evaluation inputs. Copying them from the downloaded envelope would defeat replay protection. A signed verdict from an older run cannot satisfy a newly pinned candidate run/build binding. Key rotation is an explicit change to trusted CI configuration; the verifier performs no network key discovery.

Tests generate synthetic keys at runtime and cover successful PASS/FAIL exits, altered payload/digest/status/algorithm/signature/key ID, wrong trusted key, each binding field, duplicate keys, invalid JSON/Unicode/numbers and inconsistent signed PASS results. The verifier checks signed data and producer identity, not the quality of the evaluation corpus or the truthfulness of externally supplied scores.
