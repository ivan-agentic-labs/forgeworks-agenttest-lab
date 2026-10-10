# 2026-10-11 staged HTTP request budget

## Exact code and acceptance boundary
- Release source SHA: `1c21e3406eb06e5bfd5864a68b78216fab355d9f`.
- Railway staging deployment: `88feea88-e3a0-467b-ac95-79ed4f00d289`, observed `SUCCESS` with one running, zero crashed replica at checkpoint.
- Request budget: 8 MiB actual/declared body; maximum 16,384 chunks; malformed/oversized Content-Length bounded; invalid requests return 400/413.
- Tests are synthetic TestClient/pure-ASGI, not measured external attack traffic or rate-limiting proof.
- Railway source is explicitly pinned to this SHA; documentation-only commits after it need not be deployed.

## Exact CI receipts
- AgentTest MVP Application CI: **success**, https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/38087982611
- G1 Contract Verification: **success**, https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/38087982604
- AgentTest PostgreSQL Runtime Proof: **success**, https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/38087982601

## Scope and remaining evidence
All listed CI checks were `success` for the pinned source. Staging deployment `SUCCESS` confirms startup/health gates according to Railway, not full product functionality. External `/readyz` and authenticated business workflow tests could not be independently completed from this execution environment; owner/tenant membership provisioning and all G3-G6 acceptance remain OPEN.
