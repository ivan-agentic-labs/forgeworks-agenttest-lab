# AgentTest Lab API runtime

Persist supplied case results, compare immutable bindings, sign Ed25519 verdicts and download actual persisted exports. External uploads remain quarantined; dataset source ingestion and external agent execution are unproven.

Install with `python -m pip install -e 'apps/api[test]'`. Run `uvicorn agenttest_lab.main:app` after configuring authentication and persistence. Required auth configuration is documented in `.env.example`: issuer/audience and either trusted OIDC HTTPS JWKS configuration or explicit development/test authentication. Development auth requires an explicit separate secret; there is no shared-secret fallback.

Set `AGENTTEST_DATABASE_URL` to select PostgreSQL. Apply migrations under `migrations/versions` in order using the separate migration/provisioning role. Runtime login must be a non-owner member of the product tenant role and have no superuser/BYPASSRLS/CREATEROLE/CREATEDB privileges. Runtime cannot own product or tenant/provisioning tables. Identities require provisioned internal UUID mapping. SQLite is restricted to development/test; PostgreSQL runtime refuses fixture identity seeding.

The dedicated `.github/workflows/runtime-postgres.yml` verifies a fresh disposable database, product runtime commands, tenant boundaries/concurrency and logical restore. Candidate SQL under docs/verification/sql-candidates is not auto-applied. No real provider call, production deployment or customer-data use is introduced.

See [current G1/G2 ledger](../../docs/verification/CURRENT_GATE_EVIDENCE.md) for exact source/run evidence and unfinished integrations.
