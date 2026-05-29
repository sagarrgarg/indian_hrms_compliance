# Flow 3 v2 — Task-based Daily/Weekly Reporting + KRA→SOP→KPI + Appraisal

**Status**: design locked, ready to build.
**Replaces**: `docs/flows/03_daily_reporting_kpi_appraisal.md` v1 (simpler model — kept for history; this is the deep version per the user request).
**Audited**: 2026-05-29 against `indian_hrms_compliance` v15.60.3 + ERPNext v15.108.1 + Frappe v15.107.5.

This flow defines the **continuous task execution + measurement + approval framework** that drives daily/weekly reporting, rolls up to KPIs and SOPs under KRAs, and feeds the Appraisal at cycle-end.

---

## What already exists (reuse-first survey)

Concrete shapes for things that look like Tasks or Procedures.

### From Frappe core

| Doctype | Pattern worth borrowing | Direct reuse? |
|---|---|---|
| `ToDo` | `allocated_to`, `reference_type`/`reference_name` (dynamic link), `date`, `description`, `status` — exactly the shape for surfacing "needs your attention today" to a user | **YES**, reuse as the per-user surfacing layer for assigned Task Instances |
| `Workflow` + `Workflow Action Master` + `Workflow State` | Approval flow infrastructure | **YES**, define a Workflow for Task Instance same pattern as Job Requisition Approval (already shipped) |

### From ERPNext

| Doctype | Notes | Direct reuse? |
|---|---|---|
| `Quality Procedure` | Tree (parent_quality_procedure / is_group / lft / rgt), has `processes` child table with `process_description`, has `process_owner` | **PATTERN**, copy tree + ownership pattern; data model is procedure-only, no frequency/measurement |
| `Quality Procedure Process` (child) | Just `process_description` + `procedure` (sub-procedure link) | Pattern only — we need richer fields |
| `Quality Action` | "Action taken" record: `goal`, `date`, `procedure`, `status`, `corrective_preventive`, `resolutions` | **PATTERN**, similar shape to our planned Task Instance |
| `Quality Goal` | Goal with measurable target — interesting for KPI inspiration | Pattern only |
| `Task` (projects/) | Has `is_template`, `template_task`, `start`/`duration`/`completed_on`, tree, `task_weight`, `expected_time`, `progress` | Project-scoped, not HR. Borrow `is_template` + `task_weight` field names if useful, but separate doctype |

### From existing HRMS (our app)

| Doctype | Reuse strategy |
|---|---|
| `KRA` | **REUSE** unchanged. Stays as the top-level tagging master ("Quality Assurance", "Production", "Compliance"). Tasks link to a KRA. |
| `Goal` | **KEEP DISTINCT**. Goal is per-Employee SMART goal ("achieve revenue X by date Y"). Task is recurring SOP/KPI execution ("inspect line every shift, target 0 defects"). Different lifetimes, different semantics. They coexist; both contribute to Appraisal. |
| `Appraisal` (submittable) | **REUSE**. Cycle-end auto-fed with KRA achievement % computed from Task Instances. No structural change to Appraisal — we just feed it richer data. |
| `Appraisal Cycle` | **REUSE**. `kra_evaluation_method` + `final_score_formula` (Code field) already support custom scoring; we extend the formula to include Task-derived KPI data. |
| `Appraisal Template` | **REUSE + extend slightly**. Customer can attach default Tasks to a template (per Designation), so new hires auto-pick up the SOPs for their role. |
| `Daily Work Summary` | **LEAVE ALONE**. It's email-reply driven for white-collar teams. Different pattern. Coexists. |
| `HRMS Policy` + `Employee Policy Acknowledgement` (we shipped) | **PATTERN BORROW** for: scheduler-creates-pending-records, overdue digest email, popup-on-startup |
| `Probation Review` (we shipped) | **PATTERN BORROW** for: submittable, validate-on-submit, scheduler reminders |
| `Job Requisition Approval` workflow (we shipped) | **PATTERN BORROW** for the Task Instance approval workflow definition |

### What's missing (genuinely new)

- A doctype that defines a **reusable task template** with cadence, measurement, and approval semantics
- A doctype that captures **one occurrence per Employee per period**
- A scheduler that **instantiates** templates → occurrences
- Roll-up logic that turns occurrences into KPI numbers
- The "My Tasks Today" Desk view

---

## Final data model

### `Task` (template/definition — new, master, tree, NOT submittable)

The reusable definition of a thing to do. Authored once by HR / Department Head. Tree (parent_task) so you can model KRA → SOP container Task → leaf Tasks.

```
Task  (autoname: HR-TASK-.YYYY.-.####)
├── identity
│   ├── task_name (Data, reqd)
│   ├── description (Text Editor)
│   └── color (Color — for calendar/kanban)
│
├── tree (mirrors ERPNext Task/Quality Procedure pattern)
│   ├── is_group (Check) — parent (SOP container) vs leaf (actual Task)
│   ├── parent_task (Link Task)
│   ├── lft, rgt, old_parent (Frappe tree)
│
├── classification
│   ├── kra (Link KRA — required, rolls up to)
│   ├── task_kind (Select — discriminator):
│   │     SOP Container / Individual Task / KPI Metric
│   ├── frequency (Select — required):
│   │     One-time / Daily / Weekly / Monthly / Quarterly / Yearly / On-demand
│   ├── expected_count_per_period (Int) — e.g., 5 line inspections/day
│   └── weight (Float, 0-100) — scoring contribution
│
├── completion semantics
│   ├── completion_type (Select):
│   │     Checkbox / Document Upload / Numeric Entry / Form / Approval Only
│   ├── requires_attachment (Check)
│   ├── attachment_label (Data — e.g., "Upload daily defect log PDF")
│   ├── accepted_file_types (Data — comma-sep, e.g., "pdf,jpg,png")
│   └── requires_approval (Check)
│
├── approval routing (visible when requires_approval=1)
│   ├── approver_resolution (Select):
│   │     Reports To / Specific User / Specific Role
│   ├── approver_user (Link User, when approver_resolution = Specific User)
│   └── approver_role (Link Role, when approver_resolution = Specific Role)
│
├── measurement (visible when completion_type = Numeric Entry)
│   ├── measurement_unit (Data — "count", "%", "kg", "₹", "defect rate")
│   ├── target_value (Float)
│   ├── kpi_rollup_method (Select):
│   │     Sum / Average / Latest / Max / Min  — default Sum
│   └── target_period (Select):
│         Per Period / Per Year / Per Quarter / Per Month
│
├── assignment scope (any-of semantics — Employee assigned if matches ANY rule)
│   ├── assigned_to_employees (Table — child: Task Employee Assignment, links Employee)
│   ├── assigned_to_designation (Link Designation)
│   ├── assigned_to_department (Link Department)
│   ├── assigned_to_branch (Link Branch)
│   ├── assigned_to_grade (Link Employee Grade)
│   └── assigned_to_employment_type (Link Employment Type)
│
├── lifecycle
│   ├── status (Select): Draft / Active / Paused / Retired (default Draft)
│   ├── effective_from (Date, mandatory when Active)
│   ├── effective_to (Date, optional — if set, scheduler stops instantiating after this)
│   └── company (Link Company — null = applies across all)
│
└── audit
    └── task_owner (Link User — HR steward who maintains)
```

### `Task Employee Assignment` (child — new)

```
Task Employee Assignment (istable=1)
└── employee (Link Employee, reqd, in_list_view)
```

Standalone child for the Task's explicit-Employee assignment list. Other scope fields (designation/department/branch/grade/employment_type) are direct Link fields on Task because they're singular.

### `Task Instance` (transaction — new, submittable)

One record per Employee per due period. **The scheduler creates these proactively.**

```
Task Instance  (autoname: hash)
├── what & who
│   ├── task (Link Task, reqd)
│   ├── task_name (Data, fetch_from task.task_name)
│   ├── employee (Link Employee, reqd)
│   ├── employee_name (Data, fetch_from)
│   ├── company (Link Company, fetch_from employee.company)
│   └── kra (Data, fetch_from task.kra)
│
├── period (when)
│   ├── period_label (Data — "2026-05-29" / "Week 22 2026" / "May 2026" / "Q2 2026" / "2026")
│   ├── period_start (Date)
│   ├── period_end (Date)
│   └── due_date (Date)
│
├── status (workflow_state field — Frappe Workflow on this doctype)
│   ├── workflow_state (Link Workflow State) — Pending / In Progress /
│   │     Submitted / Approved / Rejected / Skipped / Overdue
│
├── completion (depends_on completion_type fetched from task)
│   ├── completion_type (Data, fetch_from task — informational)
│   ├── attachment (Attach, depends_on requires_attachment from task)
│   ├── numeric_value (Float, depends_on completion_type=Numeric Entry)
│   ├── notes (Text)
│   ├── submitted_at (Datetime, read_only)
│   ├── submitted_by (Link User, read_only)
│
├── approval (visible when requires_approval=1 from task)
│   ├── approver (Link User — computed at submit time)
│   ├── approved_at (Datetime, read_only)
│   ├── approved_by (Link User, read_only)
│   └── approval_notes (Text)
│
└── reminders
    └── last_reminder_sent_on (Date, read_only — same pattern as EPA)
```

### `Task Instance Approval` (workflow — new)

Frappe Workflow on Task Instance. Same pattern as the Job Requisition Approval workflow we shipped.

```
States: Pending → In Progress → Submitted → Approved
                                          ↘ Rejected
                                  ↘ Skipped (HR-only)
                                  ↘ Overdue (system-set)

Transitions:
- Pending → In Progress     (Start, allowed: Employee — self)
- Pending/In Progress → Submitted    (Submit for Approval, by Employee — self)
- Submitted → Approved       (Approve, by approver_user OR holders of approver_role)
- Submitted → Rejected       (Reject, by approver_user OR approver_role)
- * → Skipped                (Skip, by HR Manager — last resort)
- (Overdue is set by scheduler, not via workflow action)
```

When `requires_approval = 0` (from Task), Submit transitions directly to Approved.

### Custom Fields on existing doctypes (extending, not creating)

| DocType | New Custom Field | Why |
|---|---|---|
| `Employee` | `default_report_period` (Select: None / Daily / Weekly, default None) | Per-Employee opt-in. Blue-collar Daily, white-collar Weekly, executives None. |
| `Appraisal Template` | `default_tasks` (Table → Appraisal Template Task, child) | Lets a template attach a default Task set; new hires in that Designation auto-assigned. (Optional — defer to v1.5 if time-constrained.) |

---

## Lifecycle flows

### 1. Publish a Task (HR authors a procedure)

```
HR opens Task list → New → fills task_name, kra, frequency, completion_type, target,
                   assignment scope (e.g., assigned_to_designation = "Line Operator")
HR sets status=Active, effective_from=today
  ↓ on_update detects "just activated"
  ↓ scheduler picks it up on next instantiation tick
```

### 2. Instantiate (daily/weekly/etc. scheduler)

```
Scheduler runs (daily at 00:00, plus on-demand for monthly/quarterly/yearly on 1st of period):
  For each Active Task:
    if Task.frequency tick matches today (Daily=every day, Weekly=Monday, Monthly=1st, etc.):
      determine assigned Employee set (via scope resolution)
      for each Employee:
        if Task Instance for (task, employee, period_label) doesn't exist:
          create Task Instance, workflow_state=Pending, due_date computed from frequency
          create ToDo for employee.user_id pointing to the Task Instance
          PWA Notification to employee.user_id
```

### 3. Employee does the work

```
Employee opens "My Tasks Today" (Desk view; PWA later):
  Sees all Task Instances where employee=me AND workflow_state in (Pending, In Progress, Overdue)
  For each:
    Checkbox    → just mark Done (Submit action)
    Doc Upload  → attach file → Submit
    Numeric     → enter value → Submit
    Approval    → Submit
  On Submit:
    if requires_approval: workflow_state=Submitted, approver notified
    else: workflow_state=Approved
```

### 4. Approval (when required)

```
Approver opens their queue:
  Sees Task Instances where workflow_state=Submitted AND (approver_user=me OR I hold approver_role)
  Reviews attachment / value / notes
  Approves or Rejects
  On Approve: workflow_state=Approved, approved_at/by stamped
  On Reject: workflow_state=Rejected, employee notified, can re-submit
```

### 5. Overdue & escalation

```
Same pattern as HRMS Policy overdue we shipped:
  Daily scheduler scans Task Instances where workflow_state=Pending AND due_date < today
  Sets workflow_state=Overdue (audit visible)
  Sends PWA Notification to employee
  Stamps last_reminder_sent_on
  Digest email to HR Manager users grouped by Company + KRA
```

### 6. KPI rollup

```
On Task Instance approve/submit:
  if task.completion_type == "Numeric Entry":
    aggregate by task.kpi_rollup_method (Sum/Avg/Latest/Max/Min)
    across all Task Instances for this Task in current period_type
    store as a derived metric, surface in KPI report + Task form
  if task.completion_type == "Checkbox":
    increment a counter
    compute completion % = approved / (expected_count_per_period * periods_elapsed)
```

### 7. Appraisal feed

```
When an Appraisal is opened for an Employee + Cycle:
  for each KRA in scope:
    find all Tasks where kra=KRA and employee is assigned (from Task scope)
    for each Task:
      compute:
        - Compliance %: approved Task Instances / total instances in cycle period
        - KPI achievement % (if Numeric): aggregated_value / target_value * 100
    expose as a read-only "KRA Performance (Auto)" section on the Appraisal
    score formula (Appraisal Cycle.final_score_formula) can reference these
```

---

## Reuse summary table

| Concept | Reuse | New |
|---|---|---|
| Task definition (procedure) | — | `Task` doctype |
| Task occurrence | — | `Task Instance` doctype |
| Hierarchy (KRA → SOP container → leaf Task) | Tree pattern (Quality Procedure, ERPNext Task) | Task is a tree via parent_task |
| Assignment to user | `ToDo` doctype (with reference_type=Task Instance) | — |
| Approval flow | `Workflow` + `Workflow State` + `Workflow Action Master` (same pattern as Job Requisition Approval) | New `Task Instance Approval` workflow record |
| Scheduler instantiation | Frappe scheduler_events.daily, plus per-frequency dispatch | New function `instantiate_due_tasks` |
| Overdue digest emails | Pattern from HRMS Policy `send_overdue_policy_ack_reminders` | New function `send_overdue_task_reminders` |
| Startup popup for current user | Pattern from `extend_bootinfo` + `overdue_policy_popup.js` | New JS module |
| KRA tagging | `KRA` doctype | — |
| KPI numeric storage | — | numeric_value on Task Instance + aggregation in report |
| Appraisal | `Appraisal` + `Appraisal Cycle` + `Appraisal Template` | Add read-only "KRA Performance (Auto)" section computed at view time; extend final_score_formula context |
| One-off SMART goals | `Goal` (existing — unchanged, coexists with Task) | — |

---

## Build sub-items (the actual work)

Numbered for tracking. Total ~3 weeks.

### Phase 3.A — Task template doctype (3 days)

- `Task` doctype JSON (tree)
- `Task Employee Assignment` child JSON
- Controller: validate (status transitions, scope sanity, weight 0-100), on_update (no fan-out — scheduler handles that)
- Workspace shortcut

### Phase 3.B — Task Instance doctype + workflow (3 days)

- `Task Instance` doctype JSON (submittable, hash autoname)
- Controller: validate, submit handlers per completion_type
- Workflow definition (`Task Instance Approval`) registered via patch — same approach as Job Requisition workflow
- Permission_query_conditions: Employees see own Task Instances; HR sees all; approver sees ones routed to them

### Phase 3.C — Scheduler & assignment resolution (3 days)

- `default_report_period` Custom Field on Employee
- Scope-resolution helper: `resolve_assigned_employees(task)` returning Employee names matching any of the scope rules
- Scheduler function `instantiate_due_tasks()` — wired daily (handles Daily); plus monthly/quarterly/yearly entry points
- Idempotency: skip if (task, employee, period_label) Task Instance already exists
- ToDo + PWA Notification creation per new Task Instance

### Phase 3.D — Overdue detection & reminders (1.5 days)

- Scheduler `mark_overdue_task_instances()` — sets workflow_state=Overdue
- Scheduler `send_overdue_task_reminders()` — mirrors policy pattern, idempotent via `last_reminder_sent_on`
- Extend `extend_bootinfo` to include overdue Task Instances for current user (cap 50)
- New JS module `overdue_task_popup.js` — same shape as policy popup

### Phase 3.E — "My Tasks Today" Desk view (1.5 days)

- Frappe `List View` customization on Task Instance: filtered to employee=me, status in (Pending, In Progress, Overdue), due_date <= today+7
- Bulk Submit action for Checkbox-type Task Instances
- Sidebar / shortcut from HRMS Overview workspace

### Phase 3.F — KPI rollup reports + Task detail view (3 days)

- Frappe Report `Task Compliance by Employee` — per-Employee, per-KRA, % approved over period
- Frappe Report `KPI Trend` — per-Task numeric value time-series
- On Task form: dashboard chart of Task Instances over time
- Dashboard Chart on HRMS Overview workspace: "Task Compliance Rate"

### Phase 3.G — Appraisal auto-feed (2 days)

- Hook on Appraisal open: compute KRA Performance section
- Display in a new HTML section on Appraisal form (`kra_performance_auto`)
- Extend `Appraisal Cycle.final_score_formula` evaluation context to expose KRA achievement variables (e.g., `kra_quality_compliance_pct`)

### Phase 3.H — Documentation & manager dashboards (1 day)

- Update `docs/flows/03_*.md`
- Add 2 number cards + 1 chart to HRMS Overview workspace
- Update memory entries

**Total: ~18 days = ~3.5 calendar weeks with buffer**

---

## Implementation order

A → B → C → D → E → F → G → H

A and B are the foundation; nothing else builds without them. C is the engine that makes the system live. D is the safety net. E gives employees a place to act. F is HR's view. G connects everything back to Appraisal. H ties off documentation.

Pause-point checkpoints:
- After A+B+C: a working but un-rolled-up system. Customers can use it for compliance evidence even before D-G ship.
- After D+E: a usable daily/weekly tracking system end-to-end.
- After F+G: integrated with appraisal.

---

## Open questions

Same as in v1 (most still apply):

1. **Daily vs weekly per Employee** — recommend: configurable per Employee via `default_report_period`. **Locked: Yes, configurable.**
2. **KPI rollup semantics** — recommend: per-Task `kpi_rollup_method` (Sum/Avg/Latest/Max/Min), default Sum. **Locked unless user objects.**
3. **SOP completion vs occurrence** — recommend: `expected_count_per_period` on Task; rollup computes "missed N of M". **Locked.**
4. **Manager review of reports** — recommend: optional, via `requires_approval=1` on each Task — manager can review-and-approve individual high-stakes Task Instances, doesn't need to see every checkbox. **Locked.**
5. **Default Task library** — same as Phase 2 Item A: HR authors per-role, we don't seed. **Locked: no seeding, consistent with vision.**
6. **Approval cycle** — single approver per Task, or chain (e.g., supervisor → QA head)? Recommend single approver per Task for v1; if customer wants multi-stage, they use Frappe Workflow custom per-instance later. **Decision: single for v1.**

---

## What's NOT in Phase 3

| Item | Reason | When |
|---|---|---|
| OKR-style cascading org→dept→individual goals | Goal tree already supports it; just UX wiring | Maybe later |
| Calibration sessions (manager group ratings) | Niche | Backlog |
| 9-box grid | Niche; UX-heavy | Backlog |
| Continuous Slack-style feedback | Out of scope | Skip |
| Multi-stage approval per Task Instance | Customer can configure their own Workflow later | Backlog |
| Mobile-first Task submission UX | Deferred to Phase 7 React PWA | Phase 7 |
| Photo geo-fenced check-in for SOP tasks | Niche; doable later | Backlog |
| ML-based KPI forecasting | Way out of scope | Skip |

---

## Where to start

Item A. Just the Task doctype, with the tree + assignment scope + lifecycle + classification fields. No instantiation yet, no scheduler yet. Once HR can author a Task and click Active, we move to B.
