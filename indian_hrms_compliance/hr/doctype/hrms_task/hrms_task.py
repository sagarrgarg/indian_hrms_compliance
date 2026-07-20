# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from calendar import monthrange

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, today

SCOPE_FIELDS = (
	"assigned_to_department",
	"assigned_to_designation",
	"assigned_to_branch",
	"assigned_to_grade",
	"assigned_to_employment_type",
	"assigned_to_employee_group",
)

# Maximum reminder lead (days before due) allowed per frequency. Daily / On-demand
# tasks have no meaningful lead (0). A monthly task shouldn't nag more than a
# fortnight out; a quarterly one no more than ~6 weeks.
FREQ_MAX_LEAD_DAYS = {
	"Daily": 0,
	"Weekly": 6,
	"Monthly": 15,
	"Quarterly": 45,
	"Yearly": 180,
	"On-demand": 0,
}


class HRMSTask(Document):
	def validate(self):
		self._validate_weight()
		self._validate_dates()
		self._validate_scope()
		self._validate_approval_routing()
		self._validate_kpi_fields()
		self._validate_reminder_lead()
		self._sync_cadence_schedule()

	def _validate_reminder_lead(self):
		lead = int(self.reminder_lead_days or 0)
		if lead < 0:
			frappe.throw(_("Reminder Lead (days before due) cannot be negative."))
		if lead == 0:
			return
		cap = FREQ_MAX_LEAD_DAYS.get(self.frequency)
		if cap is None:
			return
		if cap == 0:
			frappe.throw(
				_("A reminder lead does not apply to {0} tasks — set it to 0.").format(self.frequency)
			)
		if lead > cap:
			frappe.throw(
				_("Reminder Lead for {0} tasks cannot exceed {1} days (got {2}).").format(
					self.frequency, cap, lead
				)
			)

	def _sync_cadence_schedule(self):
		"""Adding schedule rows auto-enables the explicit schedule; occurrence
		labels must be unique because they seed each Task Instance's period label
		(the idempotency key). Mirrors Compliance Return Definition."""
		rows = self.get("cadence_schedule") or []
		if rows and not self.use_cadence_schedule:
			self.use_cadence_schedule = 1

		seen = set()
		for row in rows:
			label = (row.occurrence_label or "").strip()
			if not label:
				continue
			key = label.lower()
			if key in seen:
				frappe.throw(
					_("Duplicate occurrence '{0}' in the Cadence Schedule — labels must be unique.").format(label)
				)
			seen.add(key)

	def _validate_weight(self):
		if self.weight is not None and (self.weight < 0 or self.weight > 100):
			frappe.throw(_("Weight must be between 0 and 100."))

	def _validate_dates(self):
		if self.effective_from and self.effective_to:
			if getdate(self.effective_to) < getdate(self.effective_from):
				frappe.throw(_("'Effective To' cannot be earlier than 'Effective From'."))
		if self.status == "Active" and not self.effective_from:
			frappe.throw(_("'Effective From' is required when status is Active."))

	def _validate_scope(self):
		"""At least one scope rule must be set, unless 'Applicable to All Active' is ticked."""
		if self.applicable_to_all_active:
			return
		if not any(self.get(f) for f in SCOPE_FIELDS):
			frappe.throw(
				_(
					"Specify at least one assignment scope (Department / Designation / "
					"Branch / Grade / Employment Type / Employee Group), or tick "
					"'Applicable to All Active Employees'."
				)
			)

	def _validate_approval_routing(self):
		if not self.requires_approval:
			return
		if self.approver_resolution == "Specific User" and not self.approver_user:
			frappe.throw(_("Approver User is required when approver resolution is 'Specific User'."))
		if self.approver_resolution == "Specific Role" and not self.approver_role:
			frappe.throw(_("Approver Role is required when approver resolution is 'Specific Role'."))

	@frappe.whitelist()
	def create_test_instance(self, employee=None):
		"""Materialise ONE Task Instance now, for a single assigned employee, so
		you can verify the whole flow (scope resolution, period, due date,
		notification) without waiting for the scheduler. Idempotent — returns the
		existing instance if it's already there."""
		if self.is_new():
			frappe.throw(_("Save the task first."))
		if self.status != "Active":
			frappe.throw(_("Set the task to Active before creating a test instance."))

		assigned = resolve_assigned_employees(self)
		if not assigned:
			frappe.throw(
				_("No active employees match this task's assignment scope, so no instance can be created.")
			)
		employee = employee if employee in assigned else assigned[0]

		period_info = _pick_test_period(self)
		if not period_info:
			frappe.throw(
				_("This task has no computable period (On-demand tasks are triggered manually).")
			)

		emp_name = frappe.db.get_value("Employee", employee, "employee_name")
		existing = frappe.db.exists(
			"Goal",
			{"task_template": self.name, "employee": employee, "period_label": period_info["label"]},
		)
		result = {
			"employee": employee,
			"employee_name": emp_name,
			"period": period_info["label"],
			"due_date": str(period_info["due_date"]),
			"candidate_count": len(assigned),
		}
		if existing:
			result.update(goal=existing, created=False)
			return result

		goal = _create_task_instance(self, employee, period_info)
		frappe.db.commit()
		result.update(goal=goal.name if goal else None, created=True)
		return result

	def _validate_kpi_fields(self):
		if self.completion_type != "Numeric Entry":
			return
		if self.target_value is None:
			frappe.msgprint(
				_("Target Value is empty for this KPI Metric — KPI achievement % won't compute until set."),
				indicator="orange",
				alert=True,
			)


# ---- module-level: assignment resolution + scheduler ----


@frappe.whitelist()
def get_my_employees():
	"""Whitelisted helper: returns the list of Active Employee names linked
	to the current session user. Used by the Goal list 'My Tasks Today'
	quick-filter."""
	return frappe.get_all(
		"Employee",
		filters={"user_id": frappe.session.user, "status": "Active"},
		pluck="name",
	)


def resolve_assigned_employees(task):
	"""Return list of Employee names matching the Task's scope (any-of semantics).

	Task.company is required — final result is always intersected with that
	Company's Active Employees. Tasks never cross Company boundaries."""
	if not task.company:
		return []

	company_active = set(
		frappe.get_all(
			"Employee",
			filters={"company": task.company, "status": "Active"},
			pluck="name",
		)
	)
	if not company_active:
		return []

	if task.applicable_to_all_active:
		return list(company_active)

	employees = set()
	for fieldname, emp_field in (
		("assigned_to_department", "department"),
		("assigned_to_designation", "designation"),
		("assigned_to_branch", "branch"),
		("assigned_to_grade", "grade"),
		("assigned_to_employment_type", "employment_type"),
	):
		val = task.get(fieldname)
		if val:
			employees |= set(
				frappe.get_all(
					"Employee",
					filters={"status": "Active", emp_field: val},
					pluck="name",
				)
			)

	if task.assigned_to_employee_group:
		group_members = frappe.get_all(
			"Employee Group Table",
			filters={"parent": task.assigned_to_employee_group},
			pluck="employee",
		)
		if group_members:
			employees |= set(
				frappe.get_all(
					"Employee",
					filters={"name": ("in", list(group_members)), "status": "Active"},
					pluck="name",
				)
			)

	# Always intersect with the Task's Company — Tasks never cross Co boundaries.
	return list(employees & company_active)


def compute_period_for_today(frequency, today_d=None):
	"""Return dict(label, start, end, due_date) for the period that CONTAINS the
	given date, so running the scheduler on any day fills in the current period's
	instance (idempotent by period_label) — not only on the period's first day.

	Daily = that day; Weekly = the Mon-Sun week containing it; Monthly = its
	calendar month; Quarterly = its quarter; Yearly = its year. On-demand returns
	None (HR triggers it). One-time is handled by the caller from the task's
	effective dates."""
	today_d = getdate(today_d or today())

	if frequency == "Daily":
		return {"label": str(today_d), "start": today_d, "end": today_d, "due_date": today_d}

	if frequency == "Weekly":
		start = add_days(today_d, -today_d.weekday())  # Monday of this week
		end = add_days(start, 6)
		return {
			"label": f"Week {start.isocalendar()[1]} {start.year}",
			"start": start, "end": end, "due_date": end,
		}

	if frequency == "Monthly":
		start = today_d.replace(day=1)
		end = today_d.replace(day=monthrange(today_d.year, today_d.month)[1])
		return {"label": today_d.strftime("%B %Y"), "start": start, "end": end, "due_date": end}

	if frequency == "Quarterly":
		q_start_month = ((today_d.month - 1) // 3) * 3 + 1  # 1, 4, 7, 10
		end_month = q_start_month + 2
		start = today_d.replace(month=q_start_month, day=1)
		end = today_d.replace(month=end_month, day=monthrange(today_d.year, end_month)[1])
		q = (today_d.month - 1) // 3 + 1
		return {"label": f"Q{q} {today_d.year}", "start": start, "end": end, "due_date": end}

	if frequency == "Yearly":
		start = today_d.replace(month=1, day=1)
		end = today_d.replace(month=12, day=31)
		return {"label": str(today_d.year), "start": start, "end": end, "due_date": end}

	return None  # On-demand (and One-time, handled by the caller)


def _occurrence_months(occ):
	"""Length of an occurrence's period in whole months (Monthly=1, Quarterly=3,
	Half-Yearly=6, Annual=12). Used as the lead time so a future instance is
	created ONE PERIOD ahead — a month before for monthly, a quarter before for
	quarterly, etc."""
	ps, pe = occ["period_start"], occ["period_end"]
	return (pe.year - ps.year) * 12 + (pe.month - ps.month) + 1


def _cadence_periods_active_on(rows, target_d):
	"""For a Task carrying an explicit Cadence Schedule, return the period_info
	dict(s) that should have a live Task Instance on target_d, each with its
	exact due date.

	The activation window is [period_start − one period .. due_date]: opening it
	one whole period early means the NEXT occurrence is surfaced ahead of time —
	a monthly goal appears ~1 month before its period, a quarterly goal ~1
	quarter before — giving the assignee lead time to prepare. The due date is
	unchanged (real statutory date); only when the goal first appears moves
	earlier. Past-due occurrences still drop off once due_date passes.

	We resolve against both the FY containing target_d and the previous one, so
	an occurrence whose period opened last April but is still due (e.g. an annual
	item due in December of the following year) is still caught in Jan–Mar."""
	if not rows:
		return []
	from indian_hrms_compliance.utils import cadence as _cadence

	target_d = getdate(target_d)
	base_fy = _cadence.fy_start_year_for(target_d)
	out, seen = [], set()
	# Look back two FYs as well as the current one: with a lead of up to a full
	# year (annual cadence), an occurrence in the next FY can already be active.
	for fy_start_year in (base_fy + 1, base_fy, base_fy - 1):
		suffix = _cadence.fy_label(fy_start_year)
		for occ in _cadence.resolve_schedule(rows, fy_start_year):
			window_open = getdate(add_months(occ["period_start"], -_occurrence_months(occ)))
			if window_open <= target_d <= occ["due_date"]:
				label = f"{occ['label']} {suffix}"
				if label in seen:
					continue
				seen.add(label)
				out.append(
					{
						"label": label,
						"start": occ["period_start"],
						"end": occ["period_end"],
						"due_date": occ["due_date"],
					}
				)
	return out


def _pick_test_period(task):
	"""Choose one period_info for the 'Create Test Instance' button: the
	occurrence active today (label identical to what the scheduler produces, so
	the test instance is the real one — not a stray duplicate), else the soonest
	upcoming occurrence. Falls back to the frequency-derived current period."""
	today_d = getdate(today())
	if task.get("use_cadence_schedule"):
		rows = task.get("cadence_schedule") or []
		active = _cadence_periods_active_on(rows, today_d)
		if active:
			return sorted(active, key=lambda p: p["due_date"])[0]
		# Nothing active in the lead window — offer the soonest future occurrence.
		from indian_hrms_compliance.utils import cadence as _cadence

		best = None
		for fy in (_cadence.fy_start_year_for(today_d), _cadence.fy_start_year_for(today_d) + 1):
			suffix = _cadence.fy_label(fy)
			for occ in _cadence.resolve_schedule(rows, fy):
				if occ["due_date"] >= today_d and (best is None or occ["due_date"] < best["due_date"]):
					best = {
						"label": f"{occ['label']} {suffix}",
						"start": occ["period_start"],
						"end": occ["period_end"],
						"due_date": occ["due_date"],
					}
		return best
	return compute_period_for_today(task.frequency, today_d)


def instantiate_due_tasks(target_date=None):
	"""Scheduler (daily): for each Active leaf HRMS Task whose frequency ticks
	in the lookahead window, create a Goal record (goal_type='Task Instance')
	per assigned Employee. Idempotent — skips (task, employee, period_label)
	combinations that already exist.

	Lookahead is read from HR Settings.task_scheduler_lookahead_days (default 1):
	the scheduler runs `today` through `today + lookahead` so HR can pre-publish
	tomorrow's checklist tonight, etc.

	target_date is for testing — defaults to today.
	"""
	base_date = getdate(target_date or today())
	lookahead = int(frappe.db.get_single_value("HR Settings", "task_scheduler_lookahead_days") or 1)
	# Clamp — pathological values shouldn't run away
	if lookahead < 0:
		lookahead = 0
	if lookahead > 14:
		lookahead = 14

	created_total = 0
	for offset in range(lookahead + 1):
		created_total += _instantiate_for_date(add_days(base_date, offset))

	if created_total:
		frappe.db.commit()
	return created_total


def _instantiate_for_date(target_d):
	tasks = frappe.get_all(
		"HRMS Task",
		filters={
			"status": "Active",
			"effective_from": ("<=", target_d),
		},
		fields=[
			"name",
			"task_name",
			"kra",
			"frequency",
			"requires_approval",
			"approver_resolution",
			"approver_user",
			"approver_role",
			"applicable_to_all_active",
			"assigned_to_department",
			"assigned_to_designation",
			"assigned_to_branch",
			"assigned_to_grade",
			"assigned_to_employment_type",
			"assigned_to_employee_group",
			"company",
			"effective_from",
			"effective_to",
			"use_cadence_schedule",
		],
	)

	created = 0
	for task in tasks:
		if task.effective_to and getdate(task.effective_to) < target_d:
			continue

		# An explicit Cadence Schedule pins exact due dates; otherwise fall back
		# to the frequency-derived single period (due = period end). One-off work
		# is created directly as a Goal, so the scheduler only handles recurring
		# frequencies / scheduled cadences here.
		if task.get("use_cadence_schedule"):
			rows = frappe.get_all(
				"Cadence Schedule",
				filters={"parent": task.name, "parenttype": "HRMS Task"},
				fields=[
					"occurrence_label",
					"active",
					"period_start_month",
					"period_start_year_index",
					"period_end_month",
					"period_end_year_index",
					"due_month",
					"due_day",
					"due_year_index",
				],
				order_by="idx asc",
			)
			period_infos = _cadence_periods_active_on(rows, target_d)
		else:
			pi = compute_period_for_today(task.frequency, target_d)
			period_infos = [pi] if pi else []

		if not period_infos:
			continue

		assigned = resolve_assigned_employees(task)

		for period_info in period_infos:
			for emp_name in assigned:
				if frappe.db.exists(
					"Goal",
					{
						"task_template": task.name,
						"employee": emp_name,
						"period_label": period_info["label"],
					},
				):
					continue
				try:
					_create_task_instance(task, emp_name, period_info)
					created += 1
				except Exception:
					frappe.log_error(
						title=f"Task Instance creation failed for {task.name}/{emp_name}",
						message=frappe.get_traceback(),
					)
	return created


def _create_task_instance(task, employee, period_info):
	"""Helper: create one Goal (goal_type=Task Instance) for the (task, employee, period)."""
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "company", "reports_to", "user_id"],
		as_dict=True,
	)
	if not emp:
		return

	approver_user = None
	if task.requires_approval:
		if task.approver_resolution == "Reports To" and emp.reports_to:
			approver_user = frappe.db.get_value("Employee", emp.reports_to, "user_id")
		elif task.approver_resolution == "Specific User":
			approver_user = task.approver_user

	goal = frappe.get_doc(
		{
			"doctype": "Goal",
			"goal_name": f"{task.task_name} — {period_info['label']}",
			"employee": employee,
			"employee_name": emp.employee_name,
			"company": emp.company,
			"kra": task.kra,
			"start_date": period_info["start"],
			"end_date": period_info["end"],
			"status": "Pending",
			"goal_type": "Task Instance",
			"task_template": task.name,
			"period_label": period_info["label"],
			"due_date": period_info["due_date"],
			"approver_user": approver_user,
		}
	)
	goal.insert(ignore_permissions=True)

	if emp.user_id:
		_safe_pwa_notification(
			to_user=emp.user_id,
			message=_("Task assigned: {0} for {1}, due {2}.").format(
				task.task_name, period_info["label"], period_info["due_date"]
			),
			ref_type="Goal",
			ref_name=goal.name,
		)

	return goal


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
	"""Insert a PWA Notification, swallowing sibling chain errors."""
	msg_count_before = len(getattr(frappe.local, "message_log", []) or [])
	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": to_user,
				"from_user": frappe.session.user or "Administrator",
				"message": message,
				"reference_document_type": ref_type,
				"reference_document_name": ref_name,
			}
		).insert(ignore_permissions=True)
	except Exception:
		try:
			if hasattr(frappe.local, "message_log") and frappe.local.message_log:
				frappe.local.message_log = frappe.local.message_log[:msg_count_before]
		except Exception:
			pass
		frappe.log_error(title="Task Instance notification failed", message=frappe.get_traceback())


def send_upcoming_task_reminders():
	"""Scheduler (daily): a one-time 'due soon' heads-up to the employee once
	today reaches (due_date - reminder_lead_days) for their open Task Instances.

	This is for work that needs a running start — a monthly filing you can't
	leave to the 20th, a quarterly return that takes a week to compile. It fires
	exactly once per instance (idempotent via lead_reminder_sent_on); the
	separate overdue pass takes over after the due date. Ad-hoc tasks have no
	template, hence no lead, so they're naturally skipped."""
	today_d = getdate(today())

	templates = frappe.get_all(
		"HRMS Task",
		filters={"reminder_lead_days": (">", 0)},
		fields=["name", "reminder_lead_days"],
	)
	if not templates:
		return
	lead_by_template = {t.name: int(t.reminder_lead_days or 0) for t in templates}

	goals = frappe.get_all(
		"Goal",
		filters={
			"goal_type": "Task Instance",
			"status": ("in", ["Pending", "In Progress"]),
			"due_date": (">=", today_d),
			"task_template": ("in", list(lead_by_template)),
			"lead_reminder_sent_on": ("is", "not set"),
		},
		fields=["name", "employee", "goal_name", "due_date", "task_template"],
	)

	for g in goals:
		lead = lead_by_template.get(g.task_template, 0)
		if not lead:
			continue
		if add_days(getdate(g.due_date), -lead) > today_d:
			continue  # lead window not open yet

		emp_user = frappe.db.get_value("Employee", g.employee, "user_id")
		if emp_user:
			days_left = (getdate(g.due_date) - today_d).days
			when = _("due today") if days_left <= 0 else _("due {0} (in {1} day(s))").format(
				g.due_date, days_left
			)
			_safe_pwa_notification(
				to_user=emp_user,
				message=_("Upcoming task: {0} — {1}. Best to start now.").format(g.goal_name, when),
				ref_type="Goal",
				ref_name=g.name,
			)
		frappe.db.set_value("Goal", g.name, "lead_reminder_sent_on", today_d, update_modified=False)


def send_overdue_task_reminders():
	"""Scheduler (daily): for each Task Instance (Goal where goal_type='Task
	Instance') whose status is Pending and due_date is past and that hasn't
	been reminded today: PWA Notification to the Employee + HR Manager digest
	email grouped by Company.

	Mirrors the HRMS Policy overdue pattern. Idempotent via last_reminder_sent_on.
	"""
	from collections import defaultdict

	today_d = getdate(today())

	# NULL-safe overdue filter: rows where last_reminder_sent_on is NULL OR != today.
	# get_all's filters dict ANDs items; equality vs NULL needs explicit OR via raw SQL.
	overdue_names = frappe.db.sql(
		"""
		SELECT name FROM `tabGoal`
		WHERE goal_type = 'Task Instance'
		  AND status IN ('Pending', 'In Progress')
		  AND due_date < %s
		  AND (last_reminder_sent_on IS NULL OR last_reminder_sent_on != %s)
		""",
		(today_d, today_d),
		as_dict=False,
	)
	if not overdue_names:
		return
	overdue = frappe.get_all(
		"Goal",
		filters={"name": ("in", [r[0] for r in overdue_names])},
		fields=[
			"name",
			"employee",
			"employee_name",
			"company",
			"task_template",
			"goal_name",
			"period_label",
			"due_date",
			"kra",
			# `owner` = the User who created the Goal row (Frappe built-in).
			# For ad-hoc tasks, this is the assigning manager — we ping them
			# separately so they know their team-mate's task slipped.
			"owner",
		],
	)
	if not overdue:
		return

	# (a) Per-Employee PWA Notification + stamp reminder
	for g in overdue:
		emp_user = frappe.db.get_value("Employee", g.employee, "user_id")
		if emp_user:
			_safe_pwa_notification(
				to_user=emp_user,
				message=_("Overdue task: {0} — was due on {1}.").format(
					g.goal_name, g.due_date
				),
				ref_type="Goal",
				ref_name=g.name,
			)

		# Ad-hoc tasks (no template) also notify the creator. Skip if the
		# creator IS the assignee (self-assigned tasks shouldn't double-ping).
		is_adhoc = not g.get("task_template")
		creator = g.get("owner")
		if (
			is_adhoc
			and creator
			and creator not in ("Administrator", "Guest")
			and creator != emp_user
		):
			_safe_pwa_notification(
				to_user=creator,
				message=_("Ad-hoc task you assigned is overdue: {0} → {1} (was due {2}).").format(
					g.goal_name, g.employee_name or g.employee, g.due_date
				),
				ref_type="Goal",
				ref_name=g.name,
			)

		frappe.db.set_value(
			"Goal", g.name, "last_reminder_sent_on", today_d, update_modified=False
		)

	# (b) HR digest email grouped by Company + KRA — gated by HR Settings
	if not int(frappe.db.get_single_value("HR Settings", "send_overdue_task_hr_digest") or 0):
		return
	recipients_role = (
		frappe.db.get_single_value("HR Settings", "task_overdue_recipients_role") or "HR Manager"
	)
	hr_users = frappe.get_all("Has Role", filters={"role": recipients_role}, pluck="parent")
	hr_users = [u for u in hr_users if u and u not in ("Administrator", "Guest")]
	if not hr_users:
		return

	by_company = defaultdict(list)
	for g in overdue:
		by_company[g.company].append(g)

	rows_html = []
	for company, items in by_company.items():
		rows_html.append(
			f"<h4 style='margin-top:16px'>{frappe.utils.escape_html(company or '(no company)')}</h4>"
		)
		rows_html.append(
			"<table border='1' cellpadding='6' cellspacing='0' "
			"style='border-collapse:collapse;font-size:13px'>"
			"<tr><th>Employee</th><th>Task</th><th>KRA</th><th>Period</th>"
			"<th>Due</th><th>Days Overdue</th></tr>"
		)
		for g in sorted(items, key=lambda a: a.due_date):
			days_late = (today_d - getdate(g.due_date)).days
			rows_html.append(
				f"<tr>"
				f"<td>{frappe.utils.escape_html(g.employee_name or g.employee)}</td>"
				f"<td>{frappe.utils.escape_html(g.goal_name or '')}</td>"
				f"<td>{frappe.utils.escape_html(g.kra or '')}</td>"
				f"<td>{frappe.utils.escape_html(g.period_label or '')}</td>"
				f"<td>{g.due_date}</td>"
				f"<td style='color:#c0392b'><strong>{days_late}</strong></td>"
				f"</tr>"
			)
		rows_html.append("</table>")

	body = (
		f"<p>{len(overdue)} task instance(s) are overdue across "
		f"{len(by_company)} company(ies) as of {today_d}.</p>"
		+ "".join(rows_html)
		+ "<p style='margin-top:16px;font-size:12px;color:#777'>"
		"Automated daily digest from indian_hrms_compliance.</p>"
	)

	try:
		frappe.sendmail(
			recipients=hr_users,
			subject=f"[HRMS] Overdue Task Instances — {len(overdue)} pending",
			message=body,
			now=False,
		)
	except Exception:
		frappe.log_error(title="Task Instance overdue digest email failed", message=frappe.get_traceback())


def archive_old_completed_task_instances():
	"""Scheduler (daily): flip Task Instances (Goals with goal_type='Task Instance')
	that have been in status='Completed' longer than
	HR Settings.auto_archive_completed_task_instances_after_days to 'Archived'.

	Keeps the active working set small without losing audit history. Setting the
	threshold to 0 disables archival.
	"""
	days = int(
		frappe.db.get_single_value("HR Settings", "auto_archive_completed_task_instances_after_days") or 0
	)
	if days <= 0:
		return 0
	cutoff = add_days(getdate(today()), -days)
	# Use raw UPDATE — much cheaper than loading docs; we don't need on_update hooks.
	res = frappe.db.sql(
		"""
		UPDATE `tabGoal`
		SET status = 'Archived', modified = %s, modified_by = %s
		WHERE goal_type = 'Task Instance'
		  AND status = 'Completed'
		  AND modified < %s
		""",
		(today(), "Administrator", cutoff),
	)
	frappe.db.commit()
	# rowcount isn't reliably exposed across all drivers; recompute via SELECT for the return value.
	return frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabGoal`
		WHERE goal_type = 'Task Instance' AND status = 'Archived' AND modified >= %s
		""",
		(today(),),
	)[0][0]
