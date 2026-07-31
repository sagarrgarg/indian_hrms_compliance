# Governance & Execution Spine — Rollout Runbook

Ordered steps to (A) apply the spine to a production site and (B) pilot it on one
real department, per the blueprint's rollout ("Phases 0–1 to prod quickly; pilot
2–3 with one department and a champion; expand company-by-company; flip
Governance Profile only when HR asks").

The design carries the load: **set the master data and the spine assembles
itself.** Almost nothing here is a form to fill for its own sake.

> Prod sites are **not** in this bench. Run every `bench` command below **on the
> prod server**, never from the dev bench. The two prod servers are
> `hrms.rbcolour.com` and `ghlhrms.m.frappe.cloud`.

---

## A. Apply to production

### A0. Pre-flight (5 min)
- [ ] Take a backup: `bench --site <site> backup --with-files`
- [ ] Confirm the app is on the shipped commit: `cd apps/indian_hrms_compliance && git log -1 --oneline` → should be `90704d7` (Phase 5) or later on `version-15`.
- [ ] Note current state so you can spot the seeds' effect:
  - `bench --site <site> execute frappe.client.get_count --args '["Company"]'`

### A1. Migrate
```bash
cd /path/to/bench            # the PROD bench root
git -C apps/indian_hrms_compliance pull upstream version-15
bench --site <site> migrate
bench build --app indian_hrms_compliance
bench --site <site> clear-cache
bench restart                # so the scheduler picks up the new jobs
```

`migrate` runs two **automatic `after_migrate` seeds** (idempotent, blank-only —
safe to re-run):
- `backfill_reports_to_from_heads` — fills any empty `Employee.reports_to` from
  each department's head. On first run it fills **nothing** until you set heads
  (step B2); it converges on every later migrate as heads are set.
- `seed_governance_profile` — gives every existing Company a `governance_profile`
  from its active headcount (`≥250 Regulated`, `≥50 Growth`, else `Startup`).
  HR overrides freely afterwards.

### A2. Post-migrate verification (10 min)
Run in `bench --site <site> console`:

```python
import frappe
# New fields exist
for dt, f in [("HRMS Task","is_statutory"), ("HRMS Task","risk_tier"),
              ("HRMS Task","assign_to_head"), ("HRMS Task","playbook"),
              ("KRA","dri"), ("KRA","acting_dri"),
              ("Department","department_head"), ("Employee","default_task_delegate"),
              ("Designation","seniority_rank"), ("Company","governance_profile"),
              ("Goal","accountable_parent")]:
    assert frappe.get_meta(dt).has_field(f), f"MISSING {dt}.{f}"

# New doctypes + report exist
for dt in ["Playbook","Playbook Step","Org Integrity Finding","KPI Snapshot",
           "Department Default KRA"]:
    assert frappe.db.exists("DocType", dt), f"MISSING {dt}"
assert frappe.db.exists("Report", "Control Register")

# Seeds ran: every company has a profile
blank = frappe.get_all("Company", filters={"governance_profile": ("in", ["", None])})
print("companies without a profile (should be []):", blank)
print("OK — schema + seeds verified")
```

- [ ] Confirm the **scheduler is enabled**: `bench --site <site> scheduler status`
      → if disabled, `bench --site <site> scheduler enable`. Without it, task
      instances, the nightly Org Integrity Check, and the weekly KPI snapshot do
      not run.
- [ ] Nothing else here changes existing behaviour. Companies default to
      **Startup** = lean, so current users see no new ceremony until you opt in.

### A3. Tune HR Settings (optional, HR-only)
HR Settings → **Org Integrity Check** section (seeded on migrate):
- `Enable Nightly Org Integrity Check` — on by default; turn **off** to pause the
  whole nightly scan.
- `Stranded Approval SLA (days)` (default 3), `Critical Overdue SLA (days)`
  (default 7), `Org Integrity Escalation Role` (default HR Manager).

---

## B. Pilot one real department

Do this **on one company, one department** with a champion head. Keep everyone
else on **Startup** — the point is a real, contained proof, not a big-bang.

### B1. Pick the pilot
- A department whose head is a natural champion ("if it's yours, it's yours").
- Their real recurring work + real checklists become the seed content.
- Decide the company's profile for the pilot:
  - **Startup** (default) — tasks + tiers only. Simplest.
  - **Growth** — also unlocks Playbooks + the KPI Scorecard. Recommended if the
    pilot includes measurable KPIs or documented procedures.
  - Set it on the **Company** form → Governance Profile.

### B2. Seed the reporting tree (the highest-leverage step)
- On the **Department** form → Headship, set **Department Head** (and
  `Acting Head` + `Acting Until` if the head is on leave).
- Saving this **auto-fills `reports_to`** for that department's members who have
  none — the tree assembles from one input. Manual reporting lines are never
  overwritten.
- The head can maintain their own team's lines from the **PWA → My Department**
  screen (re-point a member) without any Desk access.
- Set `Employee.default_task_delegate` (a peer/deputy) for anyone who takes
  leave, so cover routes sensibly (falls back to the manager if unset).

### B3. Accountability areas (KRAs) + DRIs
- Create the department's **KRAs** (one company each). Every Active KRA **must
  name a DRI** — the one person answerable. Use `Acting DRI` for dated cover.
- (Growth+) On the Department form, list **Default KRAs** so a new joiner in the
  department is suggested the right tasks.

### B4. Tasks + Risk Tiers (the core dial)
For each KRA, create **HRMS Task** templates:
- **Risk Tier** presets everything — Routine (one tap), Standard (evidence),
  Critical (evidence + approval by someone other than the doer). Pick the tier;
  don't hand-configure controls.
- Tick **Statutory (born Critical)** for PF/ESI/TDS/GST filings, payroll release,
  POSH/grievance SLAs, DPDP obligations. This **locks the tier at Critical** —
  it can never be dialled down, in any profile.
- **Scope**: Applicable to All Active / a department / designation / etc., **or**
  tick **Assign to Head** to materialise one Accountable instance for the head,
  who then **Distributes** it to reports (PWA task detail → Distribute; reports
  can **Bounce back** with a reason; the head's instance auto-completes when the
  children do).
- (Growth+) Link a **Playbook** so the doer sees the steps as a tick-through
  checklist.
- Set **cadence** (frequency or an explicit Cadence Schedule) and, for measured
  work, `Target Value` + `KPI Rollup Method` (drives the Scorecard).
- Tip: use the task form's **"Verify"** action to post one instance now and watch
  the whole flow (scope → instance → due date → notification) before going live.

### B5. Playbooks (Growth+)
- Author **Playbook** docs: 3-bullet checklists to full procedures — same
  doctype. Mark control-point steps and expected evidence. Version bumps
  automatically when steps change. Link them to tasks in B4.

### B6. Let it run, then watch
Once the scheduler is on and the above is set:
- **Task instances** generate per cadence and appear in **PWA → My Tasks**
  (with the Scorecard on Growth+).
- **Nightly Org Integrity Check** starts flagging drift into
  **Org Integrity Finding** (Desk list + the "Open Org Integrity Findings"
  number card) and escalating to the DRI's/employee's manager or HR: inactive
  DRIs, vacant heads, stranded approvals, unroutable/overdue Critical tasks.
- **Weekly KPI Snapshot** feeds the Scorecard mid-quarter.
- **Regulated** companies: run the **Control Register** report (the auto-RCM) and,
  for an audit pull, the evidence export:
  `bench --site <site> execute indian_hrms_compliance.api.governance.export_evidence --kwargs '{"from_date":"2026-04-01","to_date":"2026-06-30","company":"<Co>"}'`

### B7. Success criteria (the pilot is working when…)
- [ ] Instances appear in each pilot member's My Tasks.
- [ ] An approval-gated (Critical) task completes **end-to-end**: doer submits →
      the approver acts from the PWA approvals inbox → it's stamped
      approved-by/at.
- [ ] Making a DRI inactive (or leaving a head vacant) produces an Org Integrity
      Finding that **escalates** the next night.
- [ ] (Growth+) The Scorecard shows target-vs-actual without opening an Appraisal.
- [ ] A leaver can't be relieved while still DRI/head/holding open instances
      (Employee Separation is blocked until handover).

### B8. Training (per the blueprint — keep it tiny)
- **Employees (10 min, in-app):** "Your tasks show up; tap done; some ask for a
  photo/number; Critical ones go to your manager."
- **Heads/Managers (30 min):** DRI meaning; the Distribute flow; approve/bounce
  from the inbox; reading the team Scorecard; My Department re-pointing.
- **HR admins (60 min):** KRA/DRI hygiene; tier philosophy (when Critical is
  mandatory); Playbook authoring; profile switching; the Control Register.

### Expand
When the pilot holds: repeat B2–B5 department-by-department, then company-by-company,
flipping each company's Governance Profile up only when HR asks. The quarterly
30-min hygiene pass (orphaned DRIs, never-completed tasks, a 5-instance Critical
evidence spot-check) is the entire "internal audit" for a Startup company and
scales into real assurance later.

---

## Safety / rollback
- All changes are **additive**; Startup profile keeps the current lean UX.
- To pause the nightly governance scan: HR Settings → **Enable Nightly Org
  Integrity Check** = off.
- The `is_statutory` lock and the leaver accountability gate are the only *hard*
  blocks introduced; both act only on new/edited records and can be reasoned
  about per-record.
- Nothing deletes data. The `after_migrate` seeds are blank-only and never
  overwrite a value a human has set.
