# Multi-Employee per User — Design

Status: **proposed**. Authored 2026-05-26.
Audited against: `indian_hrms_compliance` v15.60.3, ERPNext v15.108.1, Frappe v15.107.5 on bench `bench1`.

---

## Problem

Today the system assumes **one User ↔ one Employee**. In reality, a single person can be:

- Employed at multiple companies in a group simultaneously (e.g. GGIL + KGOPL + GGSPL — three sister entities sharing payroll/HR ops).
- Sequentially employed across companies (leaves Co A, joins Co B months later — for Form 16 / TDS continuity).
- A consultant on payroll at one entity and Director on payroll at another.
- A former employee whose record we still need years later (Form 16 reprints, gratuity disputes).

The single-Employee assumption is hardcoded in 60+ places. The goal is a model where one User legitimately maps to many Employees, with an unambiguous "current context" so payroll, leave, attendance, and tax flows behave correctly.

---

## What exists today (the constraint surface)

### Hardcoded constraints

| Where | What it does | Behavior under multi-Employee |
|---|---|---|
| `erpnext/.../employee.py:194` `validate_duplicate_user_id` | Rejects any second **Active** Employee with same `user_id` | **Blocks the use case** |
| `erpnext/startup/boot.py:89` (login boot) | Picks first Employee for `user_id` → puts in `frappe.session.data.employee` and `bootinfo.user.employee` | Picks arbitrarily; downstream code thinks that's "your Employee" |
| `indian_hrms_compliance/api/__init__.py:42` `get_current_employee_info()` | Filters by `user_id + status="Active"`, returns dict | Returns first match silently |
| `indian_hrms_compliance/api/__init__.py:81` `get_current_employee()` | Wraps the above; raises if None; returns employee name | Used in 5+ ESS APIs |
| `frontend/src/data/employee.js` | Calls `get_current_employee_info`, caches `indian_hrms_compliance:employee` | Singleton |

### The 62 callsites

- **Forward lookups** (User → Employee): `frappe.db.get_value("Employee", {"user_id": user})`, `frappe.db.exists("Employee", {"user_id": user})`. These need to fan out or pick a context.
- **Reverse lookups** (Employee → User): `frappe.db.get_value("Employee", emp_name, "user_id")` — used for socket pushes, approver mail, notifications. These don't need change; one Employee still has at most one `user_id`.

### Frappe-native primitives we should reuse

- **User Permissions** — already used by ERPNext (Employee creates UP for itself on the user). For multi-Employee, all Employee UPs co-exist; user can read all their Employees.
- **`frappe.session.data`** — arbitrary session dict, persisted per session. Good place for "current Employee context".
- **`bootinfo`** — hook for injecting context at login. Can be overridden per app.
- **Socket channels** keyed by user — fine for fanning out updates to all Employees of a user.

---

## Design options

### Option A — Drop the uniqueness constraint, fan out at lookup

Keep `Employee.user_id` as the linkage. Override `validate_duplicate_user_id` to allow multiple Active Employees per user. Replace `get_current_employee*` with a multi-aware version that picks a context.

**Pros:**
- Minimal data model change. No new doctype.
- All existing reverse lookups (Employee → User) still work.

**Cons:**
- 62 forward-lookup callsites need updating to "multi-aware" semantics. Some need to fan out (e.g., "show all my payslips"). Some need to pick a context (e.g., "submit a leave request").
- The Person concept (a human spanning multiple employments) is implicit, not modelled. Compliance scenarios that need "person-level" data — Aadhaar across companies, KYC dedup, ex-employee Form 16 lookup — have to be inferred.
- No clean place for "person attributes that don't belong to any single Employee" (Aadhaar, PAN, home address, blood group). Today they live on each Employee record, duplicated.

### Option B — HRMS Person as the intermediate (what was sprinted then paused)

```
User (Frappe auth)
   ↓ 0..1:1
HRMS Person (the human)
   ↓ 1:many
Employee (per-Company employment)
```

`Employee.user_id` stays for backwards compatibility but is **derived** from `Employee.hrms_person → HRMS Person.linked_user`. Lookups resolve User → Person → Employees.

**Pros:**
- Clean conceptual separation: User = auth identity, Person = human, Employee = employment contract.
- Person attributes (PAN, Aadhaar, UAN, NPS PRAN, home state, blood group, family/nominees) live in one place — no duplication across Employees in a group.
- Naturally supports ex-employees (Person stays, no Active Employees).
- Naturally supports humans with no User account (factory floor workers without PWA logins) — Person without `linked_user`.
- Future: Form 12B "previous employer income" can be modelled as past Employee records of the same Person.

**Cons:**
- New doctype, new migration step (backfill Person for every existing Employee).
- One more hop in queries. Mitigated by caching the User → Person → Employees mapping.
- Two ways to resolve "my Employee": via user_id directly OR via Person. Risk of drift. Mitigation: deprecate direct user_id lookups in our app code, route everything through a single helper.

### Option C — User Permissions only (Frappe-native, no schema change)

Just create User Permissions for each Employee → User pair. Frappe's permission system shows the user all their Employees in any list view. No "current context" concept.

**Pros:**
- Zero schema change.
- Already works for record visibility.

**Cons:**
- No notion of "current Employee context", which most ESS flows need ("submit a leave request" — for which Employee?).
- Doesn't address person-level deduplication.
- Doesn't unblock the `validate_duplicate_user_id` constraint.

---

## Recommendation: **Option B (HRMS Person)**

The Person abstraction earns its keep:

1. **Aadhaar / PAN / Aadhaar-last-4 / family / nominees** are person-attributes, not employment-attributes. Today they're duplicated on each Employee record. Person centralises them; each Employee carries only employment-attributes (designation, salary structure, EPF establishment code for that Company, joining date, status).
2. **Form 16 / TDS continuity / Form 12B** become natural queries on Person.employments.
3. **Multi-entity payroll** (GGIL+KGOPL+GGSPL): one Person, three concurrent Employees, three Form 16s, one Primary Employer for consolidated TDS via Form 12B.
4. **Ghost retention**: ex-employees keep Person record for compliance lookups years later, without inflating Active Employee counts.
5. The cost of the extra doctype is ~one-time migration. Once Person exists, every downstream return (PF ECR, ESI Excel, 24Q, Form 16, gratuity nomination) reads from Person + scoped Employee.

We pulled the implementation from Sprint 1 into stash. The doctype + child tables + custom fields are ready to thaw when we commit to this direction.

---

## Proposed model

### Doctypes

- **`HRMS Person`** (back from `stash@{0}`):
  - Identity: `person_code` (auto P###), `person_name`, photo, gender, dob, marital_status, blood_group
  - Statutory IDs: PAN, UAN, Aadhaar last-4 + hash, NPS PRAN
  - Contact: personal_email, mobile, home_address, home_state, home_pincode
  - Banking: default bank/account/IFSC
  - System: `linked_user` (unique Link to User), `active_employment_count` (Int, computed)
  - Tables: `family_members` (with PF/Gratuity nominee shares, ESI dependants), `employments_summary` (auto-maintained read-only)

- **`HRMS Person Family Member`** (child) — already designed.
- **`HRMS Person Employment Summary`** (child, auto-maintained from Employee hooks).

### Custom fields on Employee

- `hrms_person` — Link to HRMS Person, **required after migration**, inserted after `user_id`.
- `is_primary_employer` — Check, "Primary Employer for TDS / Form 12B". Default 0.
- `Employee.user_id` stays. Convention after migration: set `user_id` only on the Primary Employer Employee per Person. The other Employees in the group leave `user_id` blank but inherit access via `HRMS Person.linked_user`.

### Validation rules

1. `Employee.hrms_person` is required when not migrating (gate via setting in HR Settings: `enforce_hrms_person_link`).
2. **Override `validate_duplicate_user_id`**: instead of "no two Active Employees with same user_id", become "no two Active Employees with same user_id where they don't share an `hrms_person`". In practice, with `user_id` set only on Primary Employer, the rule is "exactly one Active Employee per Person has user_id set".
3. `HRMS Person.linked_user` stays unique (one user = one person).
4. On Employee insert with `hrms_person` and `is_primary_employer=1`: if another Active Employee of the same Person has `is_primary_employer=1`, throw.

### Resolution helpers (single source of truth)

All new code uses these. Add to `indian_hrms_compliance/utils/identity.py`:

```python
def get_person_for_user(user: str) -> str | None:
    """User → HRMS Person name. Cached per session."""

def get_employees_for_user(user: str, only_active: bool = True) -> list[dict]:
    """User → all Employee records via Person (fallback to user_id direct)."""

def get_current_employee_context(user: str | None = None) -> str | None:
    """The active Employee for this user/session. Uses:
       1. session preference if set and valid
       2. Primary Employer if exactly one
       3. Single Employee if only one
       4. None otherwise (caller must prompt UI)
    """

def set_current_employee_context(employee: str, user: str | None = None) -> None:
    """User picks active Employee for the session. Persists in frappe.session.data."""
```

### Login boot override

In our `hooks.py`:

```python
extend_bootinfo = "indian_hrms_compliance.boot.extend_bootinfo"
```

`extend_bootinfo` resolves the User → Person → Employees, picks the context per the rules above, and overrides `bootinfo.user.employee` + `frappe.session.data.employee`. Single-Employee users see no behaviour change.

### Frontend changes (minimal first cut)

- `frontend/src/data/employee.js` stays — backed by `get_current_employee_info` which now respects context.
- New `frontend/src/data/employees.js` (already exists) — list of all my Employees.
- New `frontend/src/data/employer_context.js` — current Employee, ability to switch.
- PWA header: if `employees.length > 1`, show a company-name pill that opens a picker. Picker calls `set_current_employee_context` and triggers a re-fetch.
- Single-Employee users: pill hidden, behaviour unchanged.

### Backend swap strategy

1. **Read-only helpers first** (no behavioural change): introduce `get_employees_for_user` and `get_current_employee_context` returning the same single-Employee result for single-Employee users.
2. **Update `api/__init__.py`**: `get_current_employee_info` and `get_current_employee` route through the helpers.
3. **Update the 5 internal callers** in our `api/__init__.py` (lines 131, 307, 388, 542, 632) — they already use `get_current_employee()` so they get the new behaviour for free.
4. **Bulk-audit the 62 callsites** in erpnext + our app:
   - Reverse lookups (Employee → user_id): unchanged.
   - Forward lookups in **our app**: route through the helper.
   - Forward lookups in **erpnext** (`startup/boot.py`, `appointment.py`, `email_digest.py`, etc.): override only where it actually breaks ESS. Most are admin-side and a single-employee pick is acceptable. Document them in this file as known-arbitrary.
5. **Override `validate_duplicate_user_id`** via `override_doctype_class` (already wired in our hooks for Employee — we override autoname; we can extend the override to relax this validator).

---

## Migration plan (zero-downtime, reversible)

### Phase 0 — Foundation

1. Restore `stash@{0}` (HRMS Person doctype + custom fields + patch).
2. Run patch on existing site (creates fields on Employee).
3. Add `extend_bootinfo` and resolution helpers (no behaviour change for single-Employee users).
4. Write `backfill_persons` patch: for every existing Employee with `user_id` set:
   - Create HRMS Person (copy name, gender, dob, PAN, mobile, personal_email, bank fields, marital_status, blood_group)
   - Set `linked_user` = Employee.user_id
   - Set `Employee.hrms_person` = new Person
   - Set `Employee.is_primary_employer` = 1 (since pre-migration there's only one Employee per user)

### Phase 1 — Validation switch

5. Override `validate_duplicate_user_id` to allow multi-Employee per Person.
6. Add validation: only one Active Employee per Person has `is_primary_employer=1`.
7. Add validation: `is_primary_employer=1 → user_id must be set`.

### Phase 2 — Frontend context

8. Add PWA company picker.
9. Add `set_current_employee_context` and session persistence.

### Phase 3 — Audit & cleanup

10. Bulk audit the 62 callsites; convert our-app ones to use the helper.
11. Document which erpnext callsites stay as-is (acceptable for admin scope).

### Rollback

- Each phase is its own commit. Revert is `git revert <commit>`.
- The `backfill_persons` patch is idempotent (skips Employees already linked).
- Removing the Person doctype later: drop Custom Fields (Employee.hrms_person, Employee.is_primary_employer), then `delete_doc("DocType", "HRMS Person")` (cascades to child tables).

---

## Edge cases & decisions deferred to implementation

| Question | Default | Notes |
|---|---|---|
| Person with no Active Employees | Allowed | Compliance retention; PWA login blocked (no employee context) |
| Person with multi Active Employees but no Primary | Throw on save | Force at least one Primary if any Active |
| User changes `Employee.user_id` post-link | Re-validate that user matches `Person.linked_user` | Or throw — direct user_id edits should be rare |
| Form 12B (mid-year join) | Query Person.employments_summary for prior-FY entries in current FY | Future sprint |
| Salary slip "My Payslips" view | Show all my Employees, grouped by Company | Default; user can filter |
| Approvers (leave_approver, expense_approver) | Stay as User links on Employee | Unaffected — they say "who approves my X" not "who is X" |
| Socket channel keying | Keep `indian_hrms_compliance:employee` keyed by user | Frontend re-fetches Employee list on push |
| Permissions for "see my Employee" | User Permission per Employee | Already created by ERPNext on user_id link; create explicitly for non-Primary Employees too |

---

## What this design does NOT solve

- **Cross-Company payroll consolidation**: each Employee still has its own Salary Structure, payroll run, payslip. We do not introduce a "consolidated payroll". Multi-employer just means multiple parallel Employee records with shared Person identity.
- **Single Sign-On to different companies**: Frappe sessions are per-User, not per-Employee. The active context is a session preference, not a separate session. If user wants to "switch identity" entirely, they log out and log in as a different User.
- **Person merge**: if we accidentally create two Persons for the same human, merging is manual (run a script). No UI for merge in this design.

---

## Open questions for Sagar

1. Do you actually expect the same `User` (login account) to act across companies, or will each company have its own User account for that person? If the latter, multi-Employee-per-User is rare; we mostly need Person to **dedupe across User accounts**.
2. Are ex-employees expected to retain PWA login post-relieving? (Affects `linked_user` retention rule.)
3. For Primary Employer — is this a per-FY decision (changes annually) or a permanent attribute? (Affects whether we need a date-bound history.)
4. Group payroll: is there exactly one Person → one User mapping (one auth identity per human across all companies), or could the same human have separate logins per company?
