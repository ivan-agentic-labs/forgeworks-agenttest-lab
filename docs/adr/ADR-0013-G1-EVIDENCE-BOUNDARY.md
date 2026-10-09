# ADR-0013: Preserve a partial G1 evidence boundary

**Status:** Accepted for the evidence update  
**Date:** 2026-10-09  
**Audited source:** `1de45357101caa63e7c21c03dbb0876e35cb7755`

## Decision

Record the current local and GitHub Actions results as **`VERIFIED`** only for the named independent OpenAPI, disposable PostgreSQL DDL, and non-owner two-tenant RLS probes. Record contract/event, synthetic authorization, static API/UI, worker, and artifact checks as **`PASS_STATIC_LIMITED`**. Keep real IdP, browser sandbox/egress, external storage, reviewer/signoff, production recovery, and other unavailable evidence as **`NOT_RUN`** or **`BLOCKED`**.

CI success is not owner approval and does not close G1-D or G1-E. The unapproved FK addendum remains review-only and is excluded from the disposable proof.

## Consequence

Future G1 closure must add retained logs and accountable approval for the residual criteria instead of upgrading these labels by inference.
