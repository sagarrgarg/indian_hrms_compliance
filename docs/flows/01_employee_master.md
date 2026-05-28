# Flow 1 — Employee Master

**Status**: research → ready for Phase 1 build.
**Audited**: 2026-05-27, against `indian_hrms_compliance` v15.60.3 (post-rename, post multi-Employee work).
**Context**: see [`docs/design/product_vision.md`](../design/product_vision.md) for the locked-in product vision this flow serves.

---

## Where the data lives

`Employee` doctype is **owned by ERPNext** (`apps/erpnext/erpnext/setup/doctype/employee/`). We never redefine it — we extend via:

- **Class override** in `overrides/employee_master.py` (`EmployeeMaster(Employee)`) — autoname + the 4 validators we shipped
- **doc_events** in `hooks.py:204` — validate (chain of 4), on_update, after_insert, on_trash, after_delete
- **JS form script** at `public/js/erpnext/employee.js` — refresh, date_of_birth → retirement
- **Dashboard** in `overrides/dashboard_overrides.py` — adds Lifecycle / Exit / Shift / Expense / etc. sections
- **Custom Fields** via `setup.py` (foundational) + `regional/india/setup.py` (India statutory)

47 doctypes link to `Employee` (every leave, attendance, payroll, performance, exit, grievance record).

---

## What's already on Employee today

### Native ERPNext (108 fields)

Roughly grouped:

- **Identity**: salutation, first/middle/last, full name, image, employee_number, gender, DOB, status
- **Emergency Contact** (already structured): `emergency_phone_number`, `person_to_be_contacted`, `relation`
- **User Details**: `user_id`, `create_user`, `create_user_permission`
- **Joining tab**: `scheduled_confirmation_date` (mislabeled "Offer Date" — actually probation-end target), `final_confirmation_date`, `contract_end_date`, `notice_number_of_days` ✅ (notice period already exists), `date_of_retirement`, department, designation, reports_to, branch, holiday_list
- **Salary tab**: salary_mode, bank_name, bank_ac_no, salary_currency, ctc
- **Address & Contacts**: cell, prefered_contact_email, company_email, personal_email, permanent_address, current_address, bio
- **Personal Details**: passport_number + date_of_issue + valid_upto + place_of_issue (✅ passport already has expiry tracking), marital_status, blood_group, family_background (unstructured text), health_details
- **Educational Qualification**: `education` child table
- **Previous Work Experience**: `external_work_history` child table
- **History In Company**: `internal_work_history` child table (auto-maintained on transfer/promotion)
- **Exit tab**: resignation_letter_date, relieving_date, reason_for_leaving, leave_encashed, encashment_date, held_on (exit interview), new_workplace, feedback
- **Misc**: `attendance_device_id` (biometric/RF tag), `unsubscribed`

### Our app's additions

**Foundational (`setup.py`)**:
- employment_type (Link → Employment Type), job_applicant (Link), grade (Link → Employee Grade), default_shift, payroll_cost_center
- Health Insurance section: provider, health_insurance_no
- Approvers section: expense_approver, leave_approver, shift_request_approver

**India regional (`regional/india/setup.py`)**:
- IFSC, MICR, PAN, Provident Fund Account
- ✅ Already-shipped Phase 1+2: UAN, ESIC IP, Aadhaar Last 4, NPS PRAN, Primary Employer

### Our validators (post Phase 0–2)

- `validate_duplicate_user_id` (override) — multi-Employee per User, hard-lock per (user, company)
- `validate_statutory_id_formats` — PAN / UAN / IFSC / Aadhaar Last 4 regex
- `validate_person_data_consistency` — cross-Employee match on PAN/UAN/ESIC IP/Aadhaar-last-4/NPS PRAN/DOB/gender
- `validate_single_primary_employer` — at-most-one Active Primary per User

---

## What the vision demands of Employee Master

Mapping from `product_vision.md` and our conversations to concrete data needs:

| Vision item | What Employee needs | Status |
|---|---|---|
| Multi-Company, multi-Employee per User | Multi-Employee support, statutory ID consistency, Primary Employer flag | ✅ Done |
| Statutory IDs (PAN/UAN/ESIC IP/Aadhaar/NPS PRAN) | Custom Fields + format + cross-Employee validators | ✅ Done |
| **Code of Conduct acknowledgement** | Per-Employee proof that they've read+accepted each policy version | 🆕 Missing |
| **Document tracking with expiry** | KYC docs, contracts, certifications — file + issue/expiry dates + alerts | 🟡 Only passport has expiry; rest unstructured |
| **Employment lifecycle classification** (Probation/Confirmed/Contract/Consultant/Intern) | Workflow-aware status, not just a free-form `employment_type` Link | 🟡 Date fields exist (scheduled/final confirmation); workflow status missing |
| **Family/Dependants** (for ESI claims, gratuity nominee Form F, PF nominee) | Structured child table with nominee share % | 🟡 Only unstructured `family_background` text |
| POSH / Safety training acknowledgement | Same pattern as Code of Conduct | 🆕 Missing (deferred to Phase 5) |
| Probation review before confirmation | Separate doctype with rating + recommendation | 🆕 Missing (deferred to Phase 2) |
| Confirmation Letter generation | Print Format triggered on confirmation | 🆕 Missing (deferred to Phase 2) |
| Internal mobility detection (within group) | Flag/derivation when new Employee is created for an existing group-User | 🆕 Missing (deferred to Phase 2) |
| Bank account consistency across same-User Employees | Soft validator (warning, not error — legit Co-specific accounts) | 🆕 Missing (low priority) |
| Skill expiry / re-certification | `expiry_date` on Employee Skill Map | 🆕 Missing (defer to Phase 5) |

---

## Phase 1 build scope (this flow)

Originally four deliverables (A/B/C/D). **A and D dropped by user; C pulled into Phase 2 where it was actually needed.** Phase 1 effectively shipped as just B.

| # | Original scope | Status |
|---|---|---|
| ~~A~~ | Employee Document tracking with expiry | **Dropped** — not relevant |
| **B** | HR Policy + Code of Conduct acknowledgement | ✅ Shipped (commit `95f93d8`) |
| **C** | `confirmation_status` Custom Field on Employee | ✅ Shipped as Phase 2-B (commit `1fdc219`) |
| ~~D~~ | Structured Family / Dependants | **Dropped** — not relevant |

The dropped items remain available in design history below for future reference, but are not on any active roadmap.

### ~~A. Employee Document tracking with expiry~~ — DROPPED

**Was**: KYC docs (PAN/Aadhaar/Education/Contract/Visa) tracked with structured `Employee Document` child table + `Employee Document Type` master + expiry scheduler. Only passport currently has expiry tracking in ERPNext.

**Status**: dropped by user as not relevant for the current scope. If revisited later, see Phase 1 design history above for the proposed shape.

### B. HR Policy + Code of Conduct acknowledgement

**Why**: Code of Conduct is a specific case of "HR Policy that requires acknowledgement". Generalising to all policies (CoC, leave policy, IT policy, POSH policy, anti-bribery, etc.) avoids building separate workflows later.

**Shape**:
- New doctype `HR Policy` (single per policy): `policy_name`, `policy_category` (Select: Code of Conduct / Leave / IT & Acceptable Use / POSH / Anti-Bribery / Data Privacy / Safety / Other), `version`, `effective_date`, `superseded_by` (Link to next version), `requires_acknowledgement` (Check), `content` (Text Editor) OR `file` (Attach), `applicable_to_all` (Check), `applicable_employees` (Table of Employee Filter — by company/department/grade)
- New doctype `Employee Policy Acknowledgement` (one per Employee per Policy version): `employee`, `policy`, `policy_version`, `acknowledged_at` (Datetime, default now), `acknowledged_via` (Select: PWA / Email Link / In-Person), `ip_address` (Data), `signed_text` (Data — "I acknowledge...", to capture intent)
- Hook: when an HR Policy is published with `requires_acknowledgement`, system creates pending Acknowledgement records for all applicable Employees, sends notification
- Report: "Policy Acknowledgement Status" — per-policy compliance %, list of who hasn't acknowledged
- Dashboard tile on Employee form: pending policy acknowledgements
- PWA route (later): "Pending Acknowledgements" — employee clicks accept → record created

**Effort**: ~2 days

### C. Confirmation Status field on Employee — ✅ shipped as Phase 2-B

Custom Field `confirmation_status` (Probation / Confirmed / Extended / Released) on Employee, inserted after `final_confirmation_date`. Backfilled from existing date fields. Lives in `setup.py` for fresh installs and `patches/v15_0/add_confirmation_status_field.py` for existing sites. See commit `1fdc219`.

### ~~D. Structured Family / Dependants~~ — DROPPED

**Was**: replace `family_background` text field with structured `Employee Family Member` child table for ESI Form 1 dependants, Gratuity Form F nominees, PF Form 2 nominees, with share % validation. Same shape as the paused HRMS Person family member child.

**Status**: dropped by user as not relevant for the current scope. If revisited later (e.g., when statutory returns need it), reuse the design from the stashed HRMS Person sprint.

---

## What's NOT in Phase 1 (intentionally)

| Item | Reason | When |
|---|---|---|
| Probation Review doctype | Belongs with the workflow that uses it | Phase 2 |
| Confirmation Letter generation | Print Format + trigger logic | Phase 2 |
| Internal mobility detection | Belongs with hiring flow | Phase 2 |
| Promote-to-Employee wizard (Applicant→Employee) | UX, belongs with Pre-hire | Phase 2 |
| POSH/Safety training acknowledgement | Reuses HR Policy doctype from (B); just configured as a special policy category | Phase 5 free with (B) |
| Skill expiry / re-certification | Touches Employee Skill Map, not Employee | Phase 5 |
| Bank account consistency cross-Employee | Soft validator, low priority — accounts can legitimately differ per Co | Optional later |
| Form 12B / TDS consolidation logic | Needs Primary Employer flag (done) + payroll engine | Phase 4 |
| HRMS Person doctype | Parked in stash — not needed unless humans-without-Users use case becomes real | Optional far-future |
| Aadhaar OCR | External API dependency, marginal value | Skip unless requested |
| Background check integration | Out of scope | Skip |

---

## Phase 1 status

Effectively complete. B was the only item that survived from the original 4-item plan; C was pulled into Phase 2 where it had a real consumer (the Probation Review workflow). A and D were dropped as not relevant to current scope.

No open questions remain for Phase 1 — what shipped is in production-ready state on hrms.local.
