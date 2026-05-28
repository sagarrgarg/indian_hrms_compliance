# Flow 3 — Daily/Weekly Reporting + KRA → SOP → KPI + Appraisal

**Status**: research → ready for Phase 3 build.
**Audited**: 2026-05-28, against `indian_hrms_compliance` v15.60.3.
**Context**: see [`docs/design/product_vision.md`](../design/product_vision.md). Builds on Phases 1 + 2.

This flow covers ongoing performance management: how employees report what they did each day/week, how that rolls up against KRAs and the SOPs/KPIs under them, and how it all aggregates into the periodic Appraisal.

---

## Reuse map — what already exists

Strong scaffolding here. Don't reinvent.

| Existing doctype | Where | Submittable? | What it does today |
|---|---|---|---|
| `KRA` | `hr/doctype/kra/` | No | Master with just `title` + `description`. Tag for Goals and Appraisals. |
| `Goal` | `hr/doctype/goal/` | No | **Tree** (parent/child, `is_group`), per Employee, with `kra` Link + `appraisal_cycle` Link + `progress` Percent + `status`. |
| `Appraisal` | `hr/doctype/appraisal/` | **Yes** | Per Employee per Cycle. Has KRAs (child), Goals (child), Self-Ratings (child). Computes total_score, self_score, avg_feedback_score, final_score (formula-driven). |
| `Appraisal Cycle` | `hr/doctype/appraisal_cycle/` | No | Period definition with `kra_evaluation_method` + `final_score_formula` (Code field). |
| `Appraisal KRA` (child) | child of Appraisal | — | KRA weight + per-goal scores |
| `Appraisal Goal` (child) | child of Appraisal | — | Individual goal score within an appraisal |
| `Appraisal Template` | `hr/doctype/appraisal_template/` | No | Reusable template with `template_goals` child for default goal sets per designation |
| `Appraisal Template Goal` (child) | child of Appraisal Template | — | KRA + weight + goal text |
| `Employee Performance Feedback` | `hr/doctype/employee_performance_feedback/` | No | 360-degree feedback record |
| `Employee Feedback Criteria` | `hr/doctype/employee_feedback_criteria/` | No | Master for what to rate (Communication, Teamwork, etc.) |
| `Employee Feedback Rating` (child) | child of Feedback | — | Individual criterion rating |
| `Daily Work Summary` | `hr/doctype/daily_work_summary/` | No | **Email-driven**. System emails users → users reply → system parses replies into a summary. Not checkbox-based. |
| `Daily Work Summary Group` | `hr/doctype/daily_work_summary_group/` | No | Users + scheduling for the email-based flow |

**Takeaway**: KRA + Goal + Appraisal + Cycle + Feedback are a complete system already. The two gaps are (1) structured day/week reporting that's NOT email-reply driven and (2) SOP + KPI as first-class concepts.

---

## What the vision adds on top

From your ask:

| Vision item | What it really means |
|---|---|
| **Daily or weekly reporting** | Structured checkbox-based report — employee opens a screen, sees today's/this week's expected tasks, ticks done/in-progress with optional notes. Not "reply to an email". |
| **KPI based on KRA SOP** | KRA → SOPs (procedures expected to be executed) → KPIs (measurable outcomes). A daily report says "did the employee execute SOP-X? did KPI-Y hit target?" |
| **Appraisal driven by accumulated reports** | At cycle-end, Appraisal pulls the rollup of daily/weekly reports + KPI achievement %, not just one-off manager scoring |

So the flow is:

```
KRA (e.g., Quality Assurance)
 └── SOP (e.g., Daily Line Inspection — 12 checkpoints)
      └── KPI (e.g., % checkpoints completed on time; defect rate)
            ↑
       Daily Report (employee ticks each checkpoint, enters defect count)
            ↓
       KPI roll-up (cycle-to-date achievement %)
            ↓
       Appraisal (uses accumulated KPI achievement as input to total_score)
```

---

## Reuse-first design

Instead of inventing SOP, KPI, and Report as separate doctypes:

### 1. Reuse `Goal` tree for KRA → SOP → KPI hierarchy

`Goal` is already a Frappe **tree** doctype (has `lft/rgt/is_group/parent_goal`). It already links to `kra` and `appraisal_cycle`. Extend it with a discriminator + measurement fields:

| New Custom Field on Goal | Type | Purpose |
|---|---|---|
| `goal_type` | Select (One-Time Goal / SOP / KPI) | Discriminates what kind of "goal" this is |
| `frequency` | Select (One-time / Daily / Weekly / Monthly / Per Cycle) | How often this should be tracked |
| `measurement_unit` | Data (count, %, hours, ₹, kg, etc.) | For KPIs |
| `target_value` | Float | For KPIs |
| `current_value` | Float (read-only, computed from reports) | For KPIs |
| `parent_kra` | Link to KRA | Already exists as `kra` — keep |

So:
- A KRA stays as a master (just a label like "Quality Assurance")
- An SOP is a `Goal` with `goal_type=SOP`, `frequency=Daily/Weekly`, `is_group=1` (parent for KPIs), `kra=Quality Assurance`
- A KPI is a `Goal` with `goal_type=KPI`, `frequency=Daily`, leaf node under the SOP, with measurement fields populated

No new doctype for SOP or KPI. The tree gives us KRA → SOP → KPI naturally.

### 2. NEW doctype `Work Report` (the only new doctype needed)

Frappe's `Daily Work Summary` is email-driven and doesn't fit. New doctype.

**`Work Report`** (submittable, per Employee per period):
- `employee` (Link Employee, reqd)
- `report_date` (Date, default today)
- `period` (Select: Daily / Weekly, reqd)
- `period_start` / `period_end` (Date)
- `status` (Select: Draft / Submitted)
- `items` (Table → Work Report Item)
- `manager_acknowledged` (Check, by reports_to)
- `notes` (Small Text)

**`Work Report Item`** (child):
- `goal` (Link Goal, optional — if blank, it's an ad-hoc item)
- `description` (Data — auto-fetched from goal.goal_name if linked)
- `goal_type` (Data, fetched from goal — Goal/SOP/KPI)
- `status` (Select: Done / In Progress / Skipped / Blocked)
- `value` (Float — for KPI items)
- `notes` (Small Text)

On submit:
- Each item with `goal_type=KPI` and `value` populated → updates `Goal.current_value` (running sum or latest, depending on KPI semantics)
- Each item with `status=Done` for `goal_type=SOP` → increments a counter on the parent SOP Goal (we'll add `completion_count` field)

### 3. Reuse `Appraisal` as the output

Appraisal already pulls Goals via its `appraisal_kra` child. After Phase 3:
- The `Appraisal` cycle-end view will show KPI achievement % per KRA computed from Work Reports
- The `final_score_formula` field (already exists as Code) can incorporate KPI achievement
- No structural change to Appraisal — we just feed it richer data

### 4. Reuse `Appraisal Template` for default SOP/KPI sets per Designation

Today templates list goals per designation. Extend: a template can list SOPs and KPIs (which are just Goals with goal_type=SOP/KPI) and auto-create them for Employees when assigned. No new doctype, just usage.

---

## What about Daily Work Summary?

Leave it. It serves a real use case (email-reply summaries for white-collar teams that don't want a structured form). The new `Work Report` doctype is for structured tracking. They coexist — different teams use different patterns.

---

## Phase 3 build scope

Five items. ~2 weeks per the vision estimate.

### A. Extend `Goal` with goal_type + measurement + frequency (2h)

Custom Fields on Goal:
- `goal_type` (Select: One-Time Goal / SOP / KPI, default One-Time Goal, in_list_view)
- `frequency` (Select: One-time / Daily / Weekly / Monthly / Per Appraisal Cycle, default One-time)
- `measurement_unit` (Data, depends on goal_type=KPI)
- `target_value` (Float, depends on goal_type=KPI)
- `current_value` (Float, read_only, depends on goal_type=KPI — auto-updated by Work Report submits)
- `completion_count` (Int, read_only, depends on goal_type=SOP — auto-incremented)
- `last_reported_on` (Date, read_only — for surfacing "stale" SOPs)

Patch + setup.py update.

### B. New doctype `Work Report` + child `Work Report Item` (2 days)

As designed above. Submittable. Permission roles: HR Manager / HR User full, Employee write own only (via permission_query_conditions, same pattern as Employee Policy Acknowledgement).

Form behaviour:
- When `employee` is selected, an "Auto-fill from Goals" button pre-populates `items` with all the employee's active Goals where `frequency` matches the report's `period` (Daily report → daily-frequency Goals; Weekly report → daily + weekly).
- On submit: cascading update of linked Goals (`current_value`, `completion_count`, `last_reported_on`).

### C. Scheduler — daily/weekly report reminders (4h)

`hr.doctype.work_report.work_report.send_report_reminders`:
- Daily: for each Active Employee with `default_report_period = Daily` (new field on Employee, see below), check if today's Work Report exists. If not, create ToDo + PWA Notification.
- Weekly: same logic for Mondays (configurable cycle start day).

Plus a new Custom Field on Employee: `default_report_period` (Select: None / Daily / Weekly, default None). Set per Employee — blue-collar = Daily, white-collar = Weekly, executives = None.

### D. KPI rollup view + Appraisal integration (3 days)

Two pieces:

**D1. Goal Detail page** — for any Goal with `goal_type=KPI`, show a graph of `current_value` over time (computed from Work Report Item values). For SOPs, show `completion_count` trend. Frappe Dashboard Chart suffices for v1.

**D2. Appraisal auto-feed** — when an Appraisal is created/refreshed for an Employee + Cycle:
- For each KRA in the Cycle, find all Goals (SOPs + KPIs) under that KRA for the Employee
- Compute KPI achievement % = `(current_value / target_value) * 100` per KPI
- Compute SOP execution % = `(completion_count / expected_count_for_period) * 100` per SOP
- Surface in the Appraisal form as a read-only section "KRA Performance (Auto)"
- HR/Manager can override; auto values are the starting input not the final score

### E. Define the SOP/KPI library — fixtures or HR-created? (decision deferred)

Two paths:
- **Seed an Indian HRMS standard library**: 5-10 common KRAs (Quality, Production, Safety, Compliance, etc.) each with sample SOPs and KPIs. Customer can edit.
- **Leave HR to define from scratch**: same logic as Item A (Phase 2) — per-role, customer-authored.

Recommend the latter for consistency with the templates decision. Skip seeding.

---

## What's NOT in Phase 3

| Item | Reason | When |
|---|---|---|
| OKR-style cascading goals (org → dept → individual) | Goal tree supports it; UX wiring deferred | Maybe later |
| Calibration sessions (manager group ratings) | Niche feature | Backlog |
| 9-box grid talent visualisation | Niche; out of scope | Backlog |
| Continuous feedback (Slack-style) | Out of scope for HRMS core | Skip |
| Skill assessment automation from reports | Separate flow | Phase 5 if needed |
| Multi-rater feedback weighting beyond what `Appraisal Cycle.kra_evaluation_method` already supports | Existing system covers basics | Skip |
| Daily-stand-up automation (sync with Slack/Teams) | Integration cost | Skip |

---

## Implementation order

A → B → C → D

1. **A (Goal extensions, 2h)** — foundation. No risk; pure field additions.
2. **B (Work Report doctype, 2d)** — main new build.
3. **C (Scheduler, 4h)** — adds the reminder loop.
4. **D (Rollup + Appraisal feed, 3d)** — the integration piece that makes everything pay off.

Total ~6 days within the 2-week budget.

---

## Open questions

1. **Daily AND weekly, or pick one?** I propose making `period` configurable per Employee via `Employee.default_report_period`. Blue-collar Daily, white-collar Weekly, executives None.
2. **KPI semantics** — for KPIs reported daily, does `current_value` accumulate (sum across days) or hold the latest (overwrite each day)? Different KPIs work differently:
   - Sum: "units produced today" → cycle total = sum
   - Latest: "current inventory level" → not summable
   - Recommend: new field on Goal — `kpi_rollup` (Select: Sum / Average / Latest / Max / Min, default Sum). Default Sum since most operational KPIs sum.
3. **SOP completion vs occurrence** — if an SOP is meant to run daily and the employee skipped 3 days, should those skipped days count against them or be invisible? Recommend: `expected_executions_per_period` field on Goal (only for SOPs) so the rollup can compute "missed N out of expected M".
4. **Manager review of reports** — does the reports_to manager have to acknowledge each Work Report, or just see the rollup? Default: optional acknowledgement (the `manager_acknowledged` field), no hard gate.
5. **Goal template per Designation** — do we extend `Appraisal Template` to also assign default SOPs/KPIs, or build a separate "SOP Library per Designation" doctype? Recommend extending Appraisal Template — fewer doctypes, reuses existing.

Defaults I'd ship if you don't override:
1. Configurable per Employee (Daily/Weekly/None)
2. `kpi_rollup` = Sum default, configurable per KPI
3. Track `expected_executions_per_period` for SOPs
4. Manager acknowledgement optional, no hard gate
5. Extend existing Appraisal Template
