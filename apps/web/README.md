# Web console

This is a dependency-free static evaluation console for the deterministic MVP. It calls only the dataset, build, evaluation-run, cases, comparison, and CI-verdict APIs. It does **not** execute an agent, accept code, or expose an arbitrary execution endpoint.

## Run locally

Start the API with the seeded fixture and open `http://127.0.0.1:8000/ui/`:

```bash
AGENTTEST_SEED_FIXTURE=1 PYTHONPATH=apps/api/src uvicorn agenttest_lab.main:app --reload
```

Paste a scoped bearer token into the page. The page keeps the token in memory only. The default API base is the current origin; a different base can be entered for a separately hosted static copy.

The **Run evaluation flow** button registers a dataset, immutable version, and build, then creates baseline/candidate runs, compares them, fetches cases, and retrieves the signed verdict. Missing API fields, unavailable requests, `MISSING`, `TIMEOUT`, and `INVALID_RESULT` statuses are rendered as **BLOCKED / FAIL-CLOSED**, never as `PASS`.
