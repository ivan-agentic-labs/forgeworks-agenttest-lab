# AgentTest Lab

> **Compare agent behavior with reproducible evaluations and release verdicts.**

Part of **ForgeWorks**, a collection of five complementary API services for software engineering and operations.

## What the product does

AgentTest Lab provides a structured way to assess agent behavior against versioned test datasets and evaluation rules. Teams can compare a candidate with a baseline, inspect the scoring evidence, and use a policy-bound verdict in release review.

**Who uses it:** AI engineers, QA engineers, and teams maintaining agent workflows.

## Capabilities and outputs

| Capability | Input / action | Output |
| --- | --- | --- |
| Evaluation definitions | Versioned datasets and build identities | Repeatable evaluation inputs |
| Trace-based scoring | Redacted synthetic traces and deterministic rules | Per-run evaluation results |
| Regression comparison | Baseline and candidate runs | Comparable score changes and regression indicators |
| Release decision evidence | Policy conditions and evaluation outputs | CI-oriented verdict and offline signature-verification path |

## Example workflow

1. Select the dataset and the baseline/candidate build identifiers.
2. Evaluate supported traces using deterministic scoring rules.
3. Inspect deviations from the baseline.
4. Verify and consume the policy-bound verdict as release-review evidence.

**What a team gets:** explicit inputs, a repeatable processing path, and inspectable outputs for review. The repository documents offline signed-verdict verification and versioned scoring evidence.

## Technical design

- **API:** Python service with versioned REST/OpenAPI contracts and structured error handling.
- **Data:** PostgreSQL domain adapter and tenant-scoped data access controls.
- **Auth:** explicit development authentication for local use; never reuse local keys or sample identities on hosted infrastructure.
- **Verification:** automated code tests, contract checks, and scoped evidence documents. Their meaning is limited to the scenarios they exercised.

## Run locally

Install Python and the runtime/test dependencies from the repository root:

```bash
python -m pip install --require-hashes -r requirements-runtime.lock
python -m pip install -e 'apps/api[test]' -r scripts/requirements-verification.txt
export APP_ENV=development AUTH_MODE=development
export AUTH_ISSUER=https://issuer.synthetic.invalid AUTH_AUDIENCE=forgeworks-api
export DEV_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export ARTIFACT_SIGNING_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python scripts/development_token.py
AGENTTEST_SEED_FIXTURE=1 PYTHONPATH=apps/api/src uvicorn agenttest_lab.main:app --reload
```

The generated token is short-lived and is only for local development with synthetic data. To run the test suite, use `python -W error -m pytest tests` with the same explicit development environment.

## API and technical references

- [Product scope](docs/product/PRODUCT_SCOPE.md)
- [Architecture](docs/architecture/)
- [OpenAPI contract](contracts/openapi.yaml) and [event schemas](contracts/events.schema.json)
- [Verification evidence](docs/verification/CURRENT_GATE_EVIDENCE.md)
- [Release verification runbook](ops/runbooks/RUNTIME_RELEASE_VERIFICATION.md)
- [One-app / five-services design](docs/platform/ONE_APP_FIVE_SERVICES.md)

## ForgeWorks service family

- [APIShield Agent](https://github.com/ivan-agentic-labs/forgeworks-apishield-agent) · API contract-change analysis
- [AccessFix AI](https://github.com/ivan-agentic-labs/forgeworks-accessfix-ai) · accessibility review
- [SpecForge AI](https://github.com/ivan-agentic-labs/forgeworks-specforge-ai) · requirements-to-API contracts
- [AgentTest Lab](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab) · AI agent evaluation
- [DataReconcile AI](https://github.com/ivan-agentic-labs/forgeworks-datareconcile-ai) · reconciliation and exceptions

The services have separate repositories and explicit interfaces. A single customer-facing ForgeWorks portal is an architectural direction, not a claim of independently verified live integration.

## Usage boundary

The evaluator is fixture-first. It does not execute arbitrary remote agents or use an LLM judge, and a passing verdict is not proof of a production agent's real-world reliability. Consult the linked evidence register and runbook before claiming customer-level or production acceptance.
