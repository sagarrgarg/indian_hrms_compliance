# indian_hrms_compliance — Product Vision

**Status**: locked-in as of 2026-05-27.
**Audience**: anyone working on this codebase or evaluating roadmap decisions.

---

## What we're building

A **multi-tenant SaaS HRMS for Indian SMB groups**, built on Frappe, distributed eventually as a hosted product. The defining tagline:

> From Code of Conduct to daily performance tracker, KRA/KPI, offer letter, F&F letter, employment details, all Indian compliance like POSH — everything inside one app.

The system optimises for **systems clarity over technical sophistication**. The goal is something simple, solid, and useful that any Indian SMB group can deploy and operate — not a bespoke tool for one customer.

---

## Architecture: two systems, one human

The defining architectural decision is the **separation of HRMS from operational ERP**:

```
                        HUMAN
                          │
                          │  one identity (SSO)
        ┌─────────────────┼─────────────────┐
        ▼                                   ▼
    ┌─────────┐                  ┌──────────────────┐
    │  HRMS   │                  │ Operational ERPs │
    │  (this) │                  │ (one per Co)     │
    └─────────┘                  └──────────────────┘
   identity, leaves,             manufacturing,
   attendance, payroll           warehouse, accounting,
   execution, performance,       CMS, sales, purchases
   appraisal, grievance,
   daily reporting,
   document tracking,
   compliance returns
   (PF/ESI/TDS/Form 16)
```

### Deployment topology

- **One HRMS instance per customer** (a customer = a group of related and/or unrelated companies under common HR ops).
- Customer's HRMS instance contains **multiple `Company` records** — e.g., RKCW + GGIL + KGOPL + GGSPL.
- **Each operating Company runs its own ERP** on its own bench/site. E.g., `erp.rbcolour.com` for RKCW. Customer chooses the ERP (could be ERPNext, could be Tally, could be anything that accepts a JE via API).
- **Users hold one identity** that grants access to HRMS + their relevant ERPs via SSO.

### Responsibility split

| HRMS owns | Operational ERP owns |
|---|---|
| Human identity, demographic, statutory IDs (PAN/UAN/Aadhaar/NPS PRAN/ESIC IP) | Operational books (GL, P&L, balance sheet) |
| Multi-Company employment records per human | Sales, purchases, inventory, manufacturing |
| Leave, attendance, shift management | Customer/Supplier ledger, accounts receivable/payable |
| Payroll execution (Salary Slips, bulk transfer files) | Bank reconciliation, treasury |
| Performance, KRA/KPI, appraisal cycles | Operational reporting, MIS |
| Code of Conduct acknowledgement, policy distribution | CMS, sales workflow |
| Daily reporting (checkbox-based) | Production planning, BOMs |
| Grievance, POSH, disciplinary | Inter-company accounting |
| Document tracking with expiry | (Operational documents) |
| Compliance returns (PF ECR, ESI Excel, 24Q, Form 16, LWF, PT) | (Tax filings unrelated to payroll) |

### Why this split is structurally sound

1. **HR is person-centric; operations is company-centric.** Each domain matches its natural grain.
2. **Compliance returns are person-scoped** (EPFO sees UAN; IT sees PAN; ESIC sees IP) — consolidating them in HRMS makes returns assemble naturally.
3. **Blast radius is bounded** — ERP bug doesn't break HR; HR bug doesn't stop manufacturing.
4. **Salary data confidentiality** — operational accounting team in the ERP never sees per-Employee comp; they see one consolidated JE per Co per cycle.
5. **Each system upgrades on its own cadence.**

---

## Multi-Company / multi-Employee model

Within an HRMS instance:

- **One User** (auth identity) **→ many Employee records** (one per Company that human works at).
- **Hard lock**: only one Active Employee per `(user_id, company)` pair. Sequential rejoin (previous Left → new Active in same Co) is allowed.
- **Cross-Employee statutory consistency** is enforced: PAN, UAN, ESIC IP, Aadhaar last-4, NPS PRAN, date_of_birth, gender must match across Employees of the same User. Blanks never contradict values; only non-empty mismatches throw.
- **One Primary Employer per User** for TDS / Form 12B consolidation. At most one Active Employee per User may carry `is_primary_employer=1`.

**HRMS Person doctype** is parked in stash. The decision: for this product, multi-Employee per User (with shared `user_id` as the linkage) is enough. Person earns its keep only if we later need to model humans who aren't Users (factory floor workers without app access, contractors, ex-employees long-retained for compliance).

---

## Payroll architecture: separate salary bank, consolidated JE, no HRMS ledger

### Money flow (monthly, per Company)

```
Main Operating Bank (in ERP)
       │
       │  (1) HR generates Funding Request
       │  (2) Finance approves in ERP
       │  (3) Finance posts the Main → SBA transfer
       ▼
Salary Bank Account (SBA, dedicated per Co)
       │
       │  (4) HRMS generates bulk NEFT file
       │  (5) HRMS posts ONE consolidated JE to ERP via API
       │      (Salary Expense Dr + all statutory Payables Cr + Salary Payable Cr)
       │  (6) Bank executes the bulk transfer
       ▼
Employees' personal bank accounts
```

### Books

| System | Records | Doesn't see |
|---|---|---|
| **Operational ERP** | One aggregated JE per month (Salary Expense + PF Payable + ESI Payable + PT Payable + TDS Payable + LWF Payable + Salary Payable) + the funding transfer (Salary Bank Dr / Main Bank Cr) | Who got paid what. No employee names. No per-Employee breakup. |
| **HRMS** | Per-Employee Salary Slip + the bulk transfer file generated against SBA + per-Employee disbursement status (Pending/Paid/Bounced/Returned) | GL. No double-entry accounting. No balance tracking. |

### Reconciliation chain

```
HRMS: ΣSalary Slips             = ₹X
  =  HRMS: bulk file total       = ₹X
  =  Bank statement: SBA debit   = ₹X
  =  ERP: Salary Payable cleared = ₹X
  =  ERP: Salary Expense booked  = ₹X
```

All five totals must match. Mismatch anywhere is a real audit signal.

### HRMS bank model — virtual, no ledger

HRMS has Bank Account **metadata only** — name, account number, IFSC, label. No balance, no JE. The accounting truth lives in ERP. Three lightweight things HRMS does track:

1. Bank Account metadata per Company (which SBA to disburse from)
2. Bank Remittance record per payroll cycle (file generated, total amount, bank response)
3. Disbursement status per Employee per cycle

### The one critical override

Frappe HRMS's default `Payroll Entry` controller auto-posts a Journal Entry to the local ERPNext GL on submit (`make_accrual_jv_entry`). In our architecture this is wrong — we must override `Payroll Entry` to:

- Build the JE payload without saving it locally
- Push it to the operational ERP via REST API with an idempotency key
- Record the ERP-side JE name on the Payroll Entry for traceability

This override is what makes the "no HRMS ledger" decision real. Without it, HRMS bench accumulates phantom GL entries nobody reads.

### Decisions locked

| | Decision |
|---|---|
| **JE shape** | Aggregated with full statutory lines (Salary Expense + each Payable, one JE per Co per cycle) |
| **Funding flow** | HR triggers funding request → finance approves in ERP → finance posts the transfer |
| **HRMS ledger** | Virtual / metadata only. No HRMS GL. Override Payroll Entry to push to ERP. |

### Decisions outstanding

- **Payroll corrections**: default = roll into next cycle; exceptional = standalone out-of-cycle delta JE pushed to ERP. To be locked when we build payroll.

---

## Cross-system integration surface

Minimal by design. Each integration point is a small, retryable, idempotent API call.

| Direction | Endpoint | When |
|---|---|---|
| HRMS → ERP | `post_payroll_je` | After each Payroll Entry submit. Payload: company, period, statutory line breakdown, idempotency key. |
| HRMS → ERP | `post_payroll_correction` | Out-of-cycle delta JE. Same shape, marked as correction. |
| ERP → HRMS | `get_attendance_summary` | When ERP's manufacturing module needs headcount/attendance for productivity reports. |
| ERP → HRMS | `get_employee_directory` | When ERP needs employee names/designations for op reports. |

Larger decisions still open:
- **SSO mechanism** — Frappe OAuth Server vs Keycloak vs external IdP vs no SSO
- **Tenant model** — multi-tenant single site vs multi-site bench vs self-hosted appliance
- **Minimum deployment profile** — lean down the bench dependencies to just Frappe + ERPNext + indian_hrms_compliance + (optionally) india_compliance for GST

---

## Build order

Frappe-first: build doctypes, controllers, validators, print formats, reports. **Then** design React PWA on top once the underlying behaviour is real.

| # | Phase | Scope | Approx |
|---|---|---|---|
| 1 | Finish Employee Master | Employment classification (Probation / Confirmed / Contract / Consultant / Intern), document tracking with expiry, Code of Conduct acknowledgement log | 1 week |
| 2 | Pre-hire → Confirmation | Job Requisition → Opening → Applicant → Interview → Offer → **Labour Code-compliant Appointment Letter** → Onboarding → Probation tracker → **Confirmation Letter** | 2 weeks |
| 3 | Daily reporting + KRA/KPI | Daily checkbox-style reporting, goal/KRA setting, appraisal cycle | 2 weeks |
| 4 | Exit + F&F | Separation → Exit Interview → F&F with 2-day SLA → Form 16/Form 12B | 1.5 weeks |
| 5 | Compliance modules | POSH (IC, complaints, hearings, annual return), grievance, disciplinary, document expiry alerts | 2 weeks |
| 6 | Statutory returns | PF ECR file, ESI Excel, TDS 24Q, Form 16 PDF, LWF, PT | 3 weeks |
| 7 | React PWA | Replace/supplement current Vue PWA. ESS context-switcher, multi-Employee aware, mobile-first | After 1–6 |

Total Frappe-side build: ~12 weeks before PWA.

### UX patterns owned by Phase 7 (deferred from earlier phases)

Some user-facing flows have their backend shipped already but the surfacing UX is deliberately deferred to the React PWA phase, so we don't build throwaway Vue/Desk UI:

- **Policy acknowledgement banner / modal** (HRMS Policy, commit `95f93d8`) — when an Employee has Pending policy acks, PWA should show: dismissible banner before `due_date`, escalating to a navigation-blocking modal once due_date passes. Triggered off `Employee Policy Acknowledgement` status=Pending + due_date comparison. `acknowledgement_due_days` on each HRMS Policy controls the cutover. Until Phase 7, employees see acks only via Desk list view + PWA Notification bell — no proactive surfacing.
- **ESS multi-Employee context switcher** — already noted under multi-Employee work. Header pill with active Company; picker if user has >1 Active Employee.
- (Future items in later phases will be flagged here as we ship their backend.)

---

## Already shipped (foundation)

| Commit | What |
|---|---|
| `4da2619` | Rename inner package `hrms` → `indian_hrms_compliance` |
| `c891e21` | Multi-Employee per User across Companies, hard-lock per (user, company) when Active |
| `76f287a` | Statutory IDs (UAN/ESIC IP/Aadhaar last-4/NPS PRAN) + Primary Employer flag + format validators + cross-Employee consistency + at-most-one Primary rule |
| `fb06461` | Validator message format: relative URLs (no `host_name` dependency) + `str()` instead of `repr()` |
| `95f93d8` | HRMS Policy + Employee Policy Acknowledgement — generic policy distribution & acknowledgement framework (Code of Conduct, POSH, IT, Anti-Bribery, etc. all share the same shape). Backend complete; PWA surfacing deferred to Phase 7. |
| `1fdc219` | Phase 2-B: `confirmation_status` Custom Field on Employee (Probation/Confirmed/Extended/Released) + backfill from existing date fields. |
| `a8b1e1f` | Phase 2-C: Probation Review submittable doctype + Confirmation/Extension/Release letters via Appointment Letter with letter_type discriminator + scheduler reminders 30 days before confirmation due. Templates per-role left to HR (no seeded content). |
| `6ea9c9b` | Phase 2-D: Job Requisition 3-stage approval workflow (Draft → Pending HR Review → Pending Final Approval → Approved) + auto-creates Job Opening on Approval. |
| `2fa0725` | Phase 2-E: Internal mobility detection — Job Applicant auto-flagged + source Employee linked when email matches an Active Employee; PWA notification to source manager. |
| `824405c` | Phase 2-F: Promote-to-Employee wizard — whitelisted endpoint + Desk dialog to create Employee from Accepted Job Offer with pre-fill, computes scheduled_confirmation_date from probation days. |
| Phase 3 series | **Task framework** — Phase 3 v2 reuse-first build, ~10 commits: HRMS Task template doctype (tree, scope, schedule, completion semantics, approval routing); Goal extended with 15 Custom Fields to serve as Task Instance (per-Employee per-period occurrence); scheduler instantiates Daily/Weekly/Monthly/Quarterly/Yearly; overdue detection + HR digest email + Desk popup; My Tasks Today list view; Task Compliance Script Report + dashboard cards; Appraisal auto-fed KRA Performance section. The defining product feature — measurable accountability flows into appraisal via accumulated execution. |

---

## Principles

- **Systems > tech.** Simple, solid, useful. Skip clever solutions to non-problems.
- **Generic, not bespoke.** Anyone with this architecture (SMB group, common HR, multiple operating cos) should be able to deploy. Avoid features that only solve one customer's problem.
- **Frappe-native.** Use Frappe primitives (doctypes, hooks, override_doctype_class, custom fields). Don't introduce parallel infra.
- **Compliance current.** Post-Nov-2025 Labour Codes and Income Tax Act 2025 are the baseline.
- **Single source of truth per fact.** Human identity in HRMS; operational GL in ERP. Never both.
- **Small, retryable cross-system APIs.** Idempotency keys on every write. Easy to audit, easy to retry.
- **Confidentiality by design.** Per-Employee salary never leaves HRMS.
