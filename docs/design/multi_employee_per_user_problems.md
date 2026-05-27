# Multi-Employee-per-User — Concrete Problem Inventory

**Scope of change being analysed**: Override `Employee.validate_duplicate_user_id` so the same User can have an Active Employee in different Companies, with a hard lock at one Active Employee per (user, company).

This doc catalogues **everything that would silently misbehave** the moment a second Active Employee appears for any User. Each row cites a real file:line so we can decide whether to fix-now, fix-later, or accept.

Authored 2026-05-26 against `indian_hrms_compliance` v15.60.3, ERPNext v15.108.1.

---

## Severity legend

- 🔴 **Breaks** — user-visible failure or silently-wrong behaviour with no workaround.
- 🟡 **Wrong but recoverable** — user can manually correct (e.g., re-select Employee on a form).
- 🟢 **Cosmetic / arbitrary pick** — works but picks a non-deterministic Employee.

---

## A. Login & session pinch points

### A1. 🔴 `erpnext/startup/boot.py:89` — login picks first Employee, period
At login, ERPNext does:
```python
employee = frappe.db.get_value("Employee", {"user_id": user_name}, "name")
bootinfo["user"]["employee"] = employee
frappe.session.data.employee = employee
```
No ordering, no Active filter. Whichever Employee MariaDB returns first becomes "your Employee" for the session. Every downstream feature that reads `frappe.session.data.employee` or `bootinfo.user.employee` is bound to that pick.

**Fix**: Override via `extend_bootinfo` hook in our `hooks.py`. Resolution rule (to decide): primary employer if flagged, else most-recently-joined Active Employee, else first. Store the selected Employee plus the full list (`bootinfo.user.employees: list[dict]`) so frontend can offer a picker.

### A2. 🟡 `frontend/src/main.js:130-135` — match-check could trigger reloads
```js
await employeeResource.promise
if (!employeeResource?.data || employeeResource?.data?.user_id !== userResource.data.name) {
    // forces a reload
}
```
The check passes for any Employee whose `user_id == current user`. With multi-Employee it doesn't *break*, but the singleton it resolved to is arbitrary.

### A3. 🔴 PWA login lands on a single "my dashboard" with no switcher
`frontend/src/data/employee.js` is a singleton resource. Every view that imports it (`leaves.js`, `claims.js`, `attendance.js`, `employees.js`, `session.js`, `salary_slip/*`, `expense_claim/*`, `views/Profile.vue`, ...) sees one Employee. User logged into PWA has no UI affordance to act as Co B Employee.

---

## B. ESS API choke points (our `api/__init__.py`)

### B1. 🔴 `api/__init__.py:42` `get_current_employee_info()` — returns first match
```python
frappe.db.get_value("Employee", {"user_id": current_user, "status": "Active"}, [...])
```
With two Active rows, returns one silently. This function backs the **frontend `employeeResource`**, so the PWA singleton is whatever this returns.

### B2. 🔴 5 ESS endpoints downstream of `get_current_employee()`:

| Line | Endpoint | What user sees with multi-Employee |
|---|---|---|
| 131 | `get_attendance_calendar_events` | Attendance + holidays of only ONE Employee. Co B days missing. |
| 307 | `get_shifts` | Shifts of only ONE Employee. |
| 388 | (leave balance / similar) | Leave balances of only ONE Employee. Other Companies' balances invisible. |
| 542 | `get_expense_claim_summary` | Expense totals of only ONE Employee. |
| 632 | `get_employee_advance_balance` | Advance balances of only ONE Employee. |

**Fix**: Each endpoint needs an `employee` parameter (defaulting to current context) OR returns aggregated multi-Employee data. Most likely we want a `?employee=` query param + a context-default fallback.

### B3. 🟡 JS Desk forms

| File | Line | Behaviour |
|---|---|---|
| `hr/doctype/leave_application/leave_application.js` | 121, 276 | Form autofills "current employee" — arbitrary pick. User must change for Co B leaves. |
| `hr/doctype/expense_claim/expense_claim.js` | 344 | Same — Expense Claim defaults to wrong Employee for Co B claims. |

**Fix**: `get_current_employee()` server fn should accept a target Company hint OR JS should call a multi-list function and ask user to pick if >1.

---

## C. Frappe defaults & permissions

### C1. 🟡 User Permissions cascade (acceptable, but document it)
`erpnext/.../employee.py:88 update_user_permissions` creates User Permissions for both `Employee → User` and `Company → User`. With multi-Employee:
- User accumulates UPs for Employee A, B, C
- User accumulates UPs for Company A, B, C

**Consequence**: User can see records (Sales Invoices, POs, leads) of *all three Companies* in any company-filtered list. Today this is acceptable for a multi-Employer human (they legitimately work in all 3). It is **NOT** acceptable if we want strict per-session Company scoping.

**Decision needed**: do we want strict "see only current-context Company" or "see all Companies you're employed at"? The latter is Frappe's default behaviour and requires no change.

### C2. 🟢 `frappe.defaults.get_user_default("Company")`
With multiple Company UPs, Frappe returns one (alphabetical-first, typically). Every form that defaults `company` field — Opportunity, Sales Invoice, Lead, Issue, Salary Slip — picks that one. User picks Co B → must override the default on each form.

**Fix later**: tie default Company to current Employee context (when we have one).

### C3. 🔴 Reverse cascade in `erpnext/.../employee.py:251` — wrong Employee gets toggled
```python
# When User doc is saved with "Employee" role
employee = frappe.get_doc("Employee", {"user_id": doc.name})
employee.update_user_permissions()
```
This fetches **arbitrary** Employee and toggles its UPs based on `create_user_permission` flag of THAT Employee. Other Employees of the same user are ignored. Editing the User profile can spuriously add/remove UPs on Co A's Employee while Co B's is untouched.

**Fix**: Override this hook OR fetch ALL employees of the user and run `update_user_permissions` on each.

---

## D. Compliance data duplication (this is where India-specific pain begins)

For a single human:

### D1. 🟡 PAN duplicates per Employee
Each Employee row has its own `pan_number` Custom Field (added by our `regional/india/setup.py:58`). Three Employees = three PAN entries. Typo in one → mismatched TDS returns. No single source of truth.

### D2. 🟡 UAN / ESIC IP / NPS PRAN — not even fields yet
Per the gap matrix and the paused HRMS Person work, these are per-human identifiers (one UAN per person across all employments). Without a Person doctype, when we add UAN as a Custom Field on Employee, it duplicates 3× for a human with 3 Employees. Risk of inconsistency in PF return filings.

### D3. 🟡 Aadhaar — per-Person, would duplicate per-Employee
Same as UAN.

### D4. 🔴 Form 16 / Form 12B (primary employer)
Each Employee at each Company issues its own Form 16. The Indian Income Tax Act requires the **primary employer** to consolidate TDS via Form 12B (the employee declares previous/other employer income to one chosen employer). Without an `is_primary_employer` flag, there's no automation — every TDS computation runs in isolation, and Form 12B is a manual paper process.

### D5. 🟢 Bank account
Could legitimately differ per Employee (different Company pays into a different account). No data integrity issue here.

---

## E. Frontend Vue PWA — pervasive singleton assumption

`frontend/src/data/employee.js` is imported by 6+ files:

| File | Usage |
|---|---|
| `main.js:21,51-52,57,130-135` | App boot + provide as `$employee` globally |
| `session.js:4,19,41` | Reset on logout, reload on session |
| `data/leaves.js:2,26,42,43` | `employee` + `approver_id` on leave forms — wrong approver for Co B leaves |
| `data/claims.js:2,21,37` | `employee` on expense claim forms |
| `data/employees.js:3,28` | Fallback when no specific employee passed |
| `views/Profile.vue` | Profile UI bound to single Employee |

**Fix shape**: split `employee.js` (singular, current context) from a new `employees.js` (list of all my Employees). Add a `currentEmployerContext` resource (writable) backed by `frappe.session.data`. Header pill that opens a picker.

---

## F. Realtime / notifications

### F1. 🟢 `publish_update` (overrides/employee_master.py:48)
Sends socket push keyed by `doc.user_id`. The frontend re-fetches `employeeResource`, which returns the arbitrary pick. Multi-Employee saves push correctly to the right User but the resulting data is just the first one re-resolved.

### F2. 🟢 PWA Notifications (`mixins/pwa_notifications.py:70`)
Uses *reverse* lookup `Employee → user_id`. One Employee → one user. No multi-Employee issue.

### F3. 🟢 Attendance/Shift Request notifications
Same reverse-lookup pattern. Fine.

---

## G. Email Digest, CRM, miscellaneous user→Employee lookups

### G1. 🟡 `erpnext/.../email_digest/email_digest.py:233,251,262,291`
Uses `frappe.session.user`. Several queries filter by user. With multi-Employee, the digest's "your attendance / leaves / etc." may aggregate or pick one — needs case-by-case audit when we actually enable this.

### G2. 🟢 `erpnext/.../appointment/appointment.py:267`
`employee_docname = frappe.db.get_value("Employee", {"user_id": user})` — used for CRM appointment attribution. Picks arbitrary, but unlikely to cause user-visible damage. Low priority.

### G3. 🟢 `erpnext/.../sales_person/sales_person.py:111`
Reverse lookup `Employee → user_id`. Fine.

---

## H. Approvers, hierarchy, workflows

### H1. 🔴 Wrong approver auto-picked on leave/expense forms
`Employee.leave_approver` / `expense_approver` are User links. When user submits a leave via PWA, the form defaults to the singleton Employee's approver. Submitting a Co B leave with Co A's approver routes the workflow wrongly.

**Mitigation in current code**: User can override `leave_approver` field manually. Risk: silent misrouting if user trusts the default.

### H2. 🟢 `reports_to`
Per-Employee. Multi-Employee with different reporting chains works correctly — each Employee has its own `reports_to`. No issue.

### H3. 🟢 Workflow approvers (Leave Approver / Expense Approver roles)
Roles are user-level, not employee-level. Approvers see a global queue. Fine.

---

## I. Naming, dedup, audit

### I1. 🟢 Employee naming
Default `HR-EMP-` series — doesn't depend on user_id. No collision.

### I2. 🟡 `Employee.create_user` auto-flow
If HR creates Employee with `create_user_permission=1` and no `user_id`, ERPNext auto-creates a User. A second Employee for the same human in another Company — if HR forgets to set `user_id` to the existing User — would create a *duplicate User* in Frappe. **Risk**: orphan auth identities for the same human.

**Fix**: Document this for the HR ops team. Or validate "if same employee_name + dob already has a user, link to it".

### I3. 🟢 Internal Job Applicant flow
Job Applicant has its own `user_id`. When applicant becomes Employee, our `update_job_applicant_and_offer` (overrides/employee_master.py:54) accepts the offer. Doesn't depend on user→Employee resolution. Fine.

---

## J. Salary / payroll / tax

### J1. 🟢 Salary Slip generation
Always keyed by Employee. Multi-Employee = multiple slips per period, correctly per-Company. No issue at generation time.

### J2. 🔴 PWA Salary Slip view
`frontend/src/views/salary_slip/Dashboard.vue` reads `employeeResource.data.name` to filter slips. User sees only ONE Employee's slips. Co B slips invisible.

### J3. 🟡 Income Tax Slab / regime selection
`Employee Tax Exemption Declaration` is per-Employee. Multi-Employee → user declares investments 3 times (once per Co), unless we centralise via Person. Form 12B logic NOT automated — the Primary Employer doesn't know about the other Employee's TDS unless manually declared.

### J4. 🟡 Statutory Bonus, Gratuity, LTA — all per-Employee
Each Employee accrues its own. A 5-year gratuity threshold could be met across multiple Employees of the same group (sister-company transfers) — but Frappe sees them as separate Employees, so service breaks. Workaround today: manual continuity records via Employee Internal Work History.

---

## K. Cross-Company permission leakage (acknowledge & decide)

With multi-Employee → multi-Company UPs, the User can see, in any company-filtered list:
- Salary Slips of all their Companies
- Expense Claims of all their Companies (if approver role)
- Leave Applications, Shift Requests, etc.

For a multi-Employer human, this is correct. For an HR user who happens to have Employees in multi-Companies, this might be over-permissive (mixing approver vs employee roles).

**Decision**: keep Frappe-default cross-Company UP behaviour, OR add `permission_query_conditions` to scope to "current Employer context". The latter is significant work and adds complexity.

---

## L. Edge cases worth flagging

### L1. Sequential rejoin in same Company
A user leaves Co A (status=Left) then is rehired in Co A 6 months later. Old Employee record kept (status=Left), new Employee created (status=Active) with same `user_id`. **Our override allows this** — only Active records are checked. Old Inactive/Left employee untouched.

### L2. Employee status flip from Active → Inactive
If we mark Co A's Employee Inactive, the (user, company, Active=true) lock releases. Creating another Active Employee in Co A for same user becomes legal. This is correct.

### L3. Two HR users editing Employees of the same human concurrently
HR-A saves Co A's Employee while HR-B saves Co B's Employee. Both succeed. No race condition unless they both touch the User record (update_user). The "first to write wins" on User.first_name/last_name — but only fires when User has no name yet (employee.py:112), so post-onboarding the User is stable.

### L4. User account deactivated
If the User is disabled (`enabled=0`), ERPNext's `validate_for_enabled_user_id` (in `validate_user_details`) auto-marks the linked Employee Inactive. With multi-Employee, **disabling the User would cascade-Inactive ALL Employees** of that user (across all Companies). Is this what we want? Probably yes — if you disable the auth account, the human can't access anything. But worth being explicit.

### L5. PAN/UAN drift across Employees
Three Employees, each independently maintained → typo in one Employee's PAN. No system flags it. The TDS return from that Employee files wrong PAN. Detectable only after IT department rejects the filing.

---

## TL;DR — what actually breaks vs what's just imperfect

**🔴 Breaks (user-facing, no workaround)**:
- A1: Login picks arbitrary Employee
- A3: PWA has no context switcher
- B1, B2: ESS endpoints see only one Employee
- C3: User-edit cascades to wrong Employee
- D4: Form 12B not automated
- H1: Wrong leave/expense approver auto-picked
- J2: Salary slip view shows only one Employee

**🟡 Wrong but recoverable**:
- B3 (Desk form autofills), C1 (UP cross-Co leakage), C2 (default Company), D1-D3 (per-Person ID duplication), G1 (email digest), I2 (orphan User creation), J3-J4 (per-Employee tax/gratuity isolation)

**🟢 Cosmetic / arbitrary picks**:
- A2, F1-F3, G2-G3, H2-H3, I1, J1, L1-L3

---

## Recommended phasing (still no code)

**Phase 0 — Just enable, accept the rough edges**
Override `validate_duplicate_user_id` only. Allow multi-Employee. Document all 🔴 items as known limitations. Single-Employee users (the current state) see *zero* behaviour change.

**Phase 1 — Login + context**
Override `extend_bootinfo` to expose `bootinfo.user.employees` (list). Add session-stored "current Employer context" and PWA picker. Fixes A1, A3.

**Phase 2 — ESS endpoints**
Make the 5 ESS endpoints in `api/__init__.py` context-aware. Fix `get_current_employee()` to use the session context. Fixes B1, B2.

**Phase 3 — Permission scoping decision**
Decide on C1 (cross-Co UP leakage). Implement permission_query_conditions if we want strict scoping.

**Phase 4 — Approver routing**
Fix H1 — Desk forms (leave/expense) consult the form's `company` to find the right approver chain, not the picked Employee's.

**Phase 5 — Compliance dedup**
Revisit HRMS Person (in stash) for D1–D3. Once Person exists, statutory IDs centralise; Employee carries only employment-scoped data. Form 12B logic becomes natural.

---

## Open questions for Sagar

1. **C1 (cross-Co UP leakage)**: Acceptable, or do we want strict per-context scoping?
2. **L4 (disable User cascade)**: When auth is disabled, should all 3 Employees auto-Inactivate, or should we keep them and just block login?
3. **Phase 0 acceptable as a first cut?** Or do we want Phase 1 (login override + picker) in the same change?
4. **D4 / Form 12B**: this is the strongest argument for HRMS Person sooner. Do we keep Person in stash, or thaw and apply now so we don't paint into a corner?
