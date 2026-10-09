# G1 evidence index

Evidence is recorded in [`docs/evidence/G1_RUNTIME_EVIDENCE.md`](../evidence/G1_RUNTIME_EVIDENCE.md) for audited SHA `1de45357101caa63e7c21c03dbb0876e35cb7755`. Checked items are narrow evidence claims, not a full G1-D or G1-E approval.

- [x] Third-party OpenAPI validation completed in CI with a preserved run link — **VERIFIED**, [run 37877966196](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877966196)
- [x] Event schema and contract shape static checks — **PASS_STATIC_LIMITED**, local and contract CI checks
- [x] PostgreSQL DDL runs from an empty disposable instance — **VERIFIED**, [run 37877994536](https://github.com/ivan-agentic-labs/forgeworks-agenttest-lab/actions/runs/37877994536)
- [x] Two-tenant RLS SELECT/INSERT/UPDATE/DELETE negative tests — **VERIFIED**, same disposable run and SHA
- [ ] Transaction-pool context reset and role-bypass checks — **NOT_RUN** beyond the scoped disposable proof
- [x] Synthetic auth/tenant negative tests — **PASS_STATIC_LIMITED**, local pytest only
- [x] Static FastAPI API/UI E2E flow — **PASS_STATIC_LIMITED**, not a real browser run
- [x] Worker reliability and artifact/integrity tests — **PASS_STATIC_LIMITED**, local in-process tests
- [ ] Generated TypeScript client compilation — **NOT_RUN**
- [ ] Real IdP session/CSRF/access-control tests — **NOT_RUN**
- [ ] Product-specific unsafe-tool/browser isolation and egress evidence — **BLOCKED**
- [ ] External storage provider integrity — **NOT_RUN**
- [ ] Owner/independent reviewer signoffs and retained logs — **NOT_RUN**
- [ ] Legal/domain/operations/cost signoff and production backup/restore — **BLOCKED / NOT_RUN**

The PostgreSQL workflow now executes both the empty disposable DDL probe and the separate non-owner RLS negative test; neither is production-database evidence. Residual blockers remain open.
