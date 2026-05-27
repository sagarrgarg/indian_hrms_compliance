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

Four deliverables. Keeps Employee Master self-contained; Phase 2 (Pre-hire→Confirmation) builds on top.

### A. Employee Document tracking with expiry

**Why**: KYC docs (PAN card scan, Aadhaar card scan, education certificates, contract scan, work permit, visa) need structured storage + expiry alerts. Only passport has expiry tracking today.

**Shape**:
- New child table doctype `Employee Document` attached to Employee
- Fields: `document_type` (Link → new `Employee Document Type` master, e.g., "PAN Card", "Aadhaar Card", "Education Certificate"), `file` (Attach), `document_number` (Data, optional), `issue_date`, `expiry_date`, `verification_status` (Select: Pending / Verified / Rejected), `notes`
- New doctype `Employee Document Type` (small master, seeded with: PAN Card, Aadhaar Card, Voter ID, Driving License, Passport, Education Certificate, Experience Certificate, Offer Letter, Appointment Letter, Contract, Visa, Work Permit, Medical Certificate, Resignation Letter, Relieving Letter, Form 16)
- Section on Employee form: "Documents" with the child table
- Scheduler (daily): scan all Employee Documents where `expiry_date` between today and today+30 days, create ToDo for the Employee + HR

**Effort**: ~1.5 days

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

### C. Confirmation Status field on Employee

**Why**: `scheduled_confirmation_date` and `final_confirmation_date` exist, but no status workflow. Phase 2 (Probation→Confirmation workflow) builds the review + letter; this just adds the field so Phase 2 has somewhere to land.

**Shape**:
- Custom Field on Employee: `confirmation_status` (Select: ` ` blank / Probation / Confirmed / Extended / Released), default blank
- Position: in Joining tab, after `final_confirmation_date`
- No workflow yet — just the field; Phase 2 wires the workflow
- Initial backfill patch: for existing Employees where `final_confirmation_date` is set and in the past → `Confirmed`; where `scheduled_confirmation_date` is set and in the future → `Probation`; else blank

**Effort**: 2 hours

### D. Structured Family / Dependants

**Why**: `family_background` is a text field today. Statutory returns need structured: ESI Form 1 dependants, Gratuity Form F nominee, PF nominee Form 2 — all need name + relationship + DOB + share %. Without structure, this is manual work each time.

**Shape**:
- New child table doctype `Employee Family Member` attached to Employee (Note: this is the same shape we sprinted-then-paused for HRMS Person — we already have the design)
- Fields: `relationship` (Select: Spouse / Father / Mother / Son / Daughter / Sibling / Other), `full_name` (Data, mandatory), `date_of_birth` (Date), `aadhaar_last_4` (Data, 4), `dependent_for_esi` (Check), `pf_nominee` (Check), `pf_nominee_share_pct` (Float, depends on `pf_nominee`), `gratuity_nominee` (Check), `gratuity_nominee_share_pct` (Float, depends on `gratuity_nominee`)
- Section on Employee form: "Family & Nominees" with the child table
- Validator: sum of `pf_nominee_share_pct` for `pf_nominee=1` rows ≤ 100; same for gratuity
- Keep `family_background` text field for unstructured notes — don't remove

**Effort**: 1 day (we have the design from the paused Sprint 1)

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

## Implementation order within Phase 1

C → A → D → B

1. **C (confirmation_status field, 2h)** — cheapest, unblocks Phase 2 even if other Phase 1 items slip
2. **A (Employee Document, 1.5d)** — self-contained, no dependencies, immediate value (HR can finally track contract expiries)
3. **D (Family / Dependants, 1d)** — direct lift from paused Sprint 1 design, no surprises
4. **B (HR Policy + Acknowledgement, 2d)** — biggest of the four, but builds on the foundation the others lay

Total: ~5 days. Fits comfortably in the 1-week budget.

---

## Open questions before build

1. **Document Types seed list** — happy with the 16 I proposed, or want to start narrower (PAN/Aadhaar/Education/Contract/Offer/Appointment/Resignation/Relieving) and add as needed?
2. **HR Policy content model** — `Text Editor` (HTML body inline) or `Attach` (PDF) or both (text for searchability + PDF for signed canonical)?
3. **Policy acknowledgement enforcement** — block ESS access until pending acks are cleared, or just nag via dashboard tile + email? (First is strict, second is gentle.)
4. **Family Member nominee shares** — enforce "must sum to 100% if anyone is nominated", or just "must not exceed 100%" (allowing partial nomination)?

The defaults I'd ship if you don't override:
1. 16 types as proposed
2. Both — Text Editor for the body + optional Attach for the signed PDF
3. Nag, don't block — strict-mode is a setting we can flip later
4. ≤100% (allow partial), since real-world nomination forms often don't add to 100
