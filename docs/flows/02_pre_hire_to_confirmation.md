# Flow 2 — Pre-hire → Confirmation

**Status**: research → ready for Phase 2 build.
**Audited**: 2026-05-27, against `indian_hrms_compliance` v15.60.3.
**Context**: see [`docs/design/product_vision.md`](../design/product_vision.md). Builds on top of [Flow 1 — Employee Master](01_employee_master.md).

This flow covers a person's journey from "we need to hire someone" to "they're confirmed past probation": Job Requisition → Opening → Applicant → Interview → Offer → Appointment Letter → Onboarding → Probation → Confirmation.

---

## Where the data lives

All 20 doctypes exist in our app (post-rename `indian_hrms_compliance/hr/doctype/...`):

| Stage | Doctype | Submittable | Status field |
|---|---|---|---|
| Plan | `Job Requisition` | No | `Pending / Open & Approved / Filled / Cancelled / Rejected` |
| Plan | `Job Opening` | No | `Open / Replied / Closed` |
| Source | `Job Applicant` | No | `Open / Replied / Rejected / Hold / Accepted` |
| Source | `Job Applicant Source`, `Job Opening Template` | No (masters) | — |
| Screen | `Interview` | **Yes** | `Pending / Under Review / Cleared / Rejected` |
| Screen | `Interview Feedback`, `Interview Type`, `Interview Detail` (child), `Interviewer` (child) | mixed | — |
| Offer | `Job Offer` | **Yes** | `Awaiting Response / Accepted / Rejected` |
| Offer | `Job Offer Term Template`, `Job Offer Term` (child), `Offer Term` | No (masters) | — |
| Onboard | `Appointment Letter` | No | — |
| Onboard | `Appointment Letter Template`, `Appointment Letter Content` (child) | No (masters) | — |
| Onboard | `Employee Onboarding` | **Yes** | `boarding_status: Pending / In Process / Completed` |
| Onboard | `Employee Onboarding Template`, `Employee Boarding Activity` (child) | No (masters) | — |
| Probation | (no dedicated doctype) | — | `Employee.scheduled_confirmation_date` + `final_confirmation_date` exist but no workflow |
| Confirm | (no dedicated doctype) | — | not implemented |

Print formats: `hr/print_format/{job_offer, standard_appointment_letter}`. The Appointment Letter print is a thin Jinja over the Template — it just renders intro + `terms` child rows + closing notes. **No statutory clauses are seeded by default.**

No workflows defined (`hr/workflow/` is empty). All stage transitions are manual status changes.

---

## Current state, doctype by doctype

### Job Requisition (25 fields)

**Has**: designation, no_of_positions, expected_compensation, requested_by, requested_by_dept/designation, posting_date, expected_by, completed_on, description, reason_for_requesting, time_to_fill, company, status. Not submittable.

**Missing**:
- **Approval workflow** — no manager/finance approval step. `status` is just a Select field; no Frappe Workflow blocks transitions.
- **Budget hold** — no link to headcount budget; cannot block requisition when over budget.
- **Auto-creation of Job Opening on approval** — manual today.

### Job Opening (35 fields)

**Has**: job_title, designation, department, company, status, route (for careers page), description, salary range (lower/upper/currency with publish flag), posted_on, closes_on, vacancies, planned_vacancies, employment_type, link to Job Requisition + Staffing Plan, publish/publish_salary_range flags.

**Missing**:
- **Careers page integration** — `route` field implies a public-facing page exists, but the frontend (`frontend/`) doesn't render it. Today this works only if you use Frappe Web (`www/` templates).
- **Multi-channel posting** — no built-in push to LinkedIn / Naukri / Indeed.

### Job Applicant (25 fields)

**Has**: applicant_name, email_id, status (Open/Replied/Rejected/Hold/Accepted), job_title (Link → Job Opening), source (Link → Job Applicant Source), source_name, cover_letter, resume_attachment, resume_link, applicant_rating, lower_range/upper_range/currency, employee_referral, designation, country, phone_number, notes.

**Missing**:
- **Internal mobility detection** — when `email_id` matches an existing Employee in any Company in the bench, the applicant should be flagged as "Internal", linked to the source Employee, and that Employee's manager notified. Currently manual.
- **Resume parser** — `resume_attachment` is just a file. No auto-extract of name/skills/experience.
- **Self-service application form** — there's a basic web form but it doesn't validate Indian fields (PAN, mobile format).

### Interview + Interview Feedback (23 fields)

**Has**: job_applicant, job_opening, interview_round, status, average_rating, interview_summary, scheduled_on/from_time/to_time, reminded flag, expected_average_rating, feedback_html, interview_details (child), submittable.

Interview Feedback is a separate doctype that interviewers submit (linked to Interview).

**Missing**:
- **Calendar integration** — no Google/Outlook free-busy lookup, no auto-scheduling.
- **Candidate self-scheduling** — no public token-based slot picker.
- **Interview kit / scorecard** — `interview_details` child holds free-form ratings; no structured competency-by-competency rubric.

### Job Offer (19 fields)

**Has**: job_applicant, applicant_name, applicant_email, status (Awaiting Response/Accepted/Rejected), offer_date, designation, company, offer_terms (Text Editor), select_terms (Link → Job Offer Term Template), terms (child table), letter_head, select_print_heading, submittable. Has dedicated print format.

**Missing**:
- **Salary breakup / net pay preview** — `offer_terms` is free text. No structured CTC components, no PF/ESI/PT/TDS preview for that state, no net-take-home calculation.
- **E-sign integration** — offer is accepted via manual status change. No DocuSign / eMudhra workflow.
- **Auto-create Onboarding on Accept** — `update_job_applicant_and_offer` hook flips Job Applicant status when Employee is created, but not the reverse (Offer accept → kick off Onboarding) — Onboarding doc is created manually.

### Appointment Letter + Templates

**Has**: applicant_name, appointment_date, job_applicant link, company, links to Appointment Letter Template (which has introduction + closing_notes + terms child table of title/description rows). The standard print format renders Template → Letter → PDF.

**Missing**:
- **Labour Code-compliant template** — this is the big one. Print format renders whatever clauses are in the Template's `terms` child rows. **No template ships seeded**. Customer's HR has to manually create one. Post-Nov-2025 Labour Codes require 14 specific clauses (notice period, F&F within 2 days, gratuity entitlement, PF/ESI declaration, working hours per OSH Code, etc.). Without seeded templates, customers will use generic clauses and be non-compliant.
- **Multiple templates per employment type** — Permanent / Fixed-Term / Contract / Consultant / Intern each need different statutory clauses (e.g., 1-year gratuity eligibility for Fixed-Term post Nov-2025 vs 5 years for Permanent).
- **Auto-fill from Job Offer / Employee** — Letter doesn't auto-pull joining_date, salary, designation from the offer.

### Employee Onboarding (21 fields)

**Has**: job_applicant, job_offer, employee_name, employee, date_of_joining, boarding_status (Pending/In Process/Completed), employee_onboarding_template, company, department, designation, employee_grade, project, activities (child = Employee Boarding Activity), holiday_list, submittable. Activities can be auto-populated from a Template.

**Missing**:
- **Pre-joining task assignment** — Onboarding focuses on post-joining checklist. No "pre-joining" automation: send welcome email, request KYC docs upload, schedule day-1 induction.
- **Asset assignment workflow** — has `Project` linkage but no integration with ERPNext Asset doctype for laptop/phone/badge.
- **Auto-create Employee on Onboarding completion** — Employee is created separately, then linked back. The wizard pattern of "convert Job Offer → Employee" is missing.

### Probation tracker

**Has**: just two date fields on Employee — `scheduled_confirmation_date` (mislabelled "Offer Date") and `final_confirmation_date`. No workflow, no reminder, no Probation Review doctype, no Confirmation Letter.

**Missing**:
- **`confirmation_status` field on Employee** — Probation / Confirmed / Extended / Released. Already scoped in Flow 1 (Phase 1 item C, deferred).
- **Scheduler reminder** — 30 days before `scheduled_confirmation_date`, create ToDo for Employee's manager + HR.
- **Probation Review doctype** — manager fills performance rating + recommendation (Confirm / Extend / Release) before confirmation.
- **Confirmation Letter** — Print Format + auto-generation on Probation Review submission with recommendation=Confirm. Should also handle "Extension" (probation extended by N days) and "Release" (separation initiated).

### Confirmation letter

Does not exist. Not as a doctype, not as a print format, not as a template.

---

## What the vision demands

From `docs/design/product_vision.md` and the Pre-hire scope discussion:

| Vision item | Status |
|---|---|
| End-to-end hire flow from requisition to confirmation | ✅ Doctypes exist; ❌ glue + automation missing |
| **Labour Code-compliant Appointment Letter** | ❌ Critical — no seeded template; current default is non-compliant |
| **Probation → Confirmation workflow** | ❌ Critical — workflow missing entirely |
| **Confirmation Letter** | ❌ Missing |
| Job Requisition approval (manager → finance → HR) | ❌ Missing — no workflow |
| Internal mobility detection (within group of Companies) | ❌ Missing — manual |
| Salary breakup / net pay preview at offer time | 🟡 Free text only |
| Auto-cascade across stages (Offer accept → Onboard → Employee) | 🟡 Partial — some hooks exist (update_job_applicant_and_offer), gaps remain |
| Cross-Company application (same Person applies internally for KGOPL while Employee at GGIL) | 🟡 Works at data level (Job Applicant supports it) but no UX |
| Bulk operations (reject 50 applicants with personalised email) | ❌ Missing |
| Calendar / self-scheduling integration | ❌ Out of scope for this product |
| Resume parsing / OCR | ❌ Out of scope unless explicitly asked |
| E-sign offer acceptance | ❌ Out of scope until eMudhra contract exists |
| Multi-channel job board posting (LinkedIn / Naukri) | ❌ Out of scope |

---

## Phase 2 build scope

Six deliverables. Total ~2 weeks. Ordered by *unblock value* (compliance hard requirements first, then workflow glue, then nice-to-haves):

### A. Labour Code-compliant Appointment Letter templates (1 day)

**Why**: Compliance deadline already passed (Nov 2025). Every new hire after this should land with a legally compliant letter. Low risk, high value.

**Shape**:
- Seed **4 `Appointment Letter Template` records** via fixture (or post-install patch): one per employment_type — Permanent / Fixed-Term / Contract / Intern. Each with 14 statutory clauses pre-populated as `Appointment Letter Content` child rows.
- The 14 clauses (drawn from Code on Wages 2019, IR Code 2020, OSH Code 2020):
  1. Job title, grade, place of employment
  2. Date of joining + probation duration
  3. Compensation (basic, allowances, statutory contributions)
  4. Working hours per OSH Code (max 48/wk, 8/day)
  5. Notice period (different for permanent vs fixed-term)
  6. F&F settlement within 2 working days clause (Code on Wages §17(2))
  7. Leave entitlement per Code on Wages
  8. PF/EPF declaration (if covered)
  9. ESI declaration (if covered)
  10. Gratuity entitlement (5 yrs permanent, 1 yr fixed-term post Nov-2025)
  11. Bonus eligibility (Payment of Bonus Act applicability)
  12. Confidentiality + IP assignment
  13. Conduct + disciplinary reference (Standing Orders if applicable)
  14. Governing law + jurisdiction
- HR can edit any seeded template; no validation that they match Labour Code (we're not auditing customer's overrides).

**Implementation**: fixtures file in `indian_hrms_compliance/fixtures/appointment_letter_template.json` + entry in `hooks.py:fixtures`. Plus a patch to re-create on existing sites (since fixtures only run on install).

### B. `confirmation_status` field on Employee + backfill (2 hours)

**Why**: Foundation for the probation workflow in (C). Originally Phase 1 item C; pulled forward here because (C) needs it.

**Shape**: Single Custom Field on Employee — `confirmation_status` Select (blank / Probation / Confirmed / Extended / Released), inserted after `final_confirmation_date`. Patch to backfill existing Employees from existing date fields.

### C. Probation → Confirmation workflow (3 days)

**Why**: HR's daily pain. Today managers forget probation end dates; confirmation letters are written in Word; status drifts silently. Compliance angle: the Code on Wages requires a written communication of confirmation; we don't generate one today.

**Shape**:
- **New doctype `Probation Review`** (submittable):
  - employee, review_date, reviewer (Link User), period_evaluated_from/to
  - performance_rating (Select: Excellent / Meets Expectations / Needs Improvement / Below Expectations)
  - feedback (Text Editor)
  - recommendation (Select: Confirm / Extend Probation / Release)
  - extension_days (Int, depends on recommendation = Extend)
- **Scheduler hook (daily)**: scan Employees where `confirmation_status = Probation` AND `scheduled_confirmation_date` is within next 30 days AND no submitted Probation Review exists → create ToDo for `reports_to` + HR.
- **On Probation Review submit**:
  - `Confirm`: Employee.confirmation_status = Confirmed; Employee.final_confirmation_date = today; generate Confirmation Letter (next item)
  - `Extend Probation`: Employee.scheduled_confirmation_date = old + extension_days; status stays Probation
  - `Release`: trigger Employee Separation workflow with reason "Probation Released"
- **New print format `confirmation_letter`** — Jinja that renders Employee.confirmation_letter_template (a new Custom Field referencing a Confirmation Letter Template, modelled after Appointment Letter Template pattern — or reuse Appointment Letter Template doctype with `template_type` field).

**Decision needed**: separate Confirmation Letter Template doctype, or reuse Appointment Letter Template with a `letter_type` discriminator? My recommendation: reuse with discriminator. Less doctype proliferation.

### D. Job Requisition approval workflow (1 day)

**Why**: Today Job Requisition is just a record; no enforcement of "manager approves → finance approves → HR posts opening". Customers will paper over this with email, but in a multi-Company group with budget controls, you need a real workflow.

**Shape**:
- Frappe `Workflow` definition for Job Requisition (in `hr/workflow/job_requisition_approval/`). States: Draft → Pending Manager Approval → Pending Finance Approval → Approved → Open & Posted → Cancelled / Rejected.
- Transitions gated by roles: Requestor → Manager → Finance Manager → HR Manager.
- On reaching "Approved": auto-create a Job Opening linked back via `job_requisition` field.

### E. Internal mobility detection (1 day)

**Why**: In a multi-Company group, employees apply internally for roles in sister Companies. Today the applicant is treated as external. We want HR + the source Employee's manager to know.

**Shape**:
- New validator on Job Applicant: when `email_id` matches an existing Active Employee anywhere in the bench, flag `is_internal_applicant = 1` (new Custom Field), set `source_employee` Link to the matching Employee, send notification to `source_employee.reports_to`.
- Source field auto-populated as "Internal Mobility" if blank.

### F. Promote-to-Employee wizard from Job Offer (2 days)

**Why**: Today, when an offer is accepted, HR creates the Employee record by hand — copy-pasting from Job Applicant / Job Offer into the Employee form. 20+ fields. Re-typing surface. Mistakes happen.

**Shape**:
- Button on Job Offer (when status=Accepted): "Create Employee"
- Opens a server-side wizard / dialog: pre-filled with Applicant.first_name/last_name/email + Offer.designation/company/letter_head + Offer.terms[salary fields]. HR fills the 5 missing fields (DOB, PAN, joining date, reports_to, bank).
- On submit:
  - Create Employee with status=Active, confirmation_status=Probation, hrms_person link (if Person flow is later enabled), is_primary_employer flag
  - Optionally trigger Employee Onboarding from a template
  - Optionally generate Appointment Letter from the Labour Code template

**Total: ~9 days = within 2-week budget with slack for testing and iteration.**

---

## What's NOT in Phase 2

| Item | Reason | When |
|---|---|---|
| Resume parser | External API or fragile library; marginal value for factory-floor hiring | Skip unless requested |
| Calendar / self-scheduling | High build cost (OAuth, free-busy, tokens) | Skip unless customer demand |
| E-sign integration | Wait for actual eMudhra/DocuSign contract | Skip |
| Multi-channel job posting (LinkedIn/Naukri) | Per-channel APIs, brittle | Skip |
| Bulk reject/move (50 applicants at once) | Frappe's bulk-edit covers it; personalised email needs templating work | Maybe Phase 5 |
| Careers page on the Vue PWA | Out of scope; Frappe Web works for now | Maybe Phase 7 |
| Interview kit / structured scorecards | Existing Interview Detail child is enough; can revisit if needed | Backlog |
| Salary breakup / net pay preview at offer | Needs payroll engine refactor (Phase 4 area) | Phase 4 |

---

## Open questions for review

1. **Confirmation Letter Template** — separate doctype or reuse Appointment Letter Template with a `letter_type` discriminator? My recommendation: reuse.
2. **Job Requisition approval roles** — exact chain (Requestor → Manager → Finance → HR)? Or simpler (Requestor → HR)? Depends on customer's expected use.
3. **Probation default duration** — 90 days (most common in Indian SMBs) or configurable per Employment Type / Grade? My recommendation: default 90 days, override via Employment Type.
4. **Probation extension limits** — should we cap how many times an Employee's probation can be extended? Some statutory frameworks limit this. My recommendation: warn after 2 extensions, no hard cap.
5. **Internal applicant — auto-create Job Applicant or just flag the email?** Today applicant submits their own Job Applicant record. Auto-creation from "click apply" on an internal opening would need a PWA flow. My recommendation: defer the PWA flow; for now, when HR manually creates a Job Applicant with an email matching an Employee, set the flag.

---

## Suggested order of execution

A → B → C → D → E → F

1. **A (Labour Code template, 1d)** — small, immediate compliance win, no dependencies
2. **B (confirmation_status field, 2h)** — prerequisite for C
3. **C (Probation → Confirmation workflow, 3d)** — biggest single item, sets the pattern for future workflows
4. **D (Job Requisition workflow, 1d)** — independent, can slot in anywhere
5. **E (Internal mobility detection, 1d)** — small, polish
6. **F (Promote-to-Employee wizard, 2d)** — UX-heavy, requires the others done first

If time runs short, **A + B + C are the must-ships**. D / E / F are valuable but can slide.
