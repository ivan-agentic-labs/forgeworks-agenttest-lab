# AgentTest Lab — P0 Product Requirements & Scope

**Target buyer:** AI engineering teams shipping LLM workflows.

**Measurable user promise:** Memeriksa kualitas, kegagalan tools, dan regresi AI agent melalui dataset/trace berversi dan hasil evaluasi yang dapat direproduksi.

## P0 end-to-end workflow
Upload redacted traces + dataset → validate consent/provenance → pin agent/model/prompt/tools/dataset/grader versions → run deterministic grading → optionally calibrated judge → compare paired results → CI verdict + review.

## Included in P0
- Ingestion trace JSONL yang tervalidasi tanpa arbitrary code
- Versioned dataset dan deterministic grading
- Paired regression dan CI evaluation report
- Optional AI judge dipisahkan dari rule deterministik

## Explicitly out of scope
- Menjalankan kode Python pelanggan secara bebas
- Remote action dengan kredensial pengguna
- Menganggap AI judge sebagai ground truth
- Skor total tanpa laporan coverage/error bars

## Roles & permission model
- `org_owner`: billing, org settings, members, quotas; does not automatically grant bypass to data policy.
- `org_admin`: invites within same tenant, configures allowed integrations, reviews impact.
- `editor`: creates runs/imports/draft analyses, cannot approve their own high-impact external write if separation-of-duty policy enables it.
- `reviewer`: approves signed revision/digest within policy and time window.
- `auditor`: read-only access to redacted audit + evidence.
- `service_worker`: machine identity with narrowly scoped effect grants, never unrestricted user impersonation; the BFF carries verified user access claims server-side.

## Product value and validation
Business hypothesis: targeted buyer experiences frequent repeatable failure that is expensive enough to justify adoption. Evidence needed: 3–5 structured buyer interviews, their current workaround, time/expense per incident, willingness to share consented/synthetic fixtures, and pilot pass criteria. These are **future prerequisites**, not interviews already done.

**North-star and guardrail metrics:** paired-case coverage, grader reproducibility on fixed fixtures, agreement with adjudicated gold set, critical policy violation recall, CI verdict stability across reruns.

## P0 completion criteria
1. One authorized end-to-end job reaches its intended output with reproducible fixture and trace.
2. Duplicate requests / partial external timeout / revocation / cross-tenant access fail safely.
3. Every material output cites a source/digest/rule version and has a reviewer action where needed.
4. Evidence of output correctness must come from deterministic assertion and human review of edge cases; AI alone does not sign off.
5. Security, privacy, budget, and recovery gate conditions defined in governance are respected.

## Critical G1 assumptions pending
- Privacy-safe trace canonical format and consent evidence need approval
- Judge agreement thresholds need labeled pilot data
- CI API provider and permission scope need live validation

**Scope owner:** Founder/Product. **Security owner:** assigned reviewer. **Domain validator:** qualified buyer/SME. **Status:** PROVISIONAL, awaiting actual signed reviews.
