# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from calendar import monthrange

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today
from frappe.utils.nestedset import NestedSet

SCOPE_FIELDS = (
	"assigned_to_department",
	"assigned_to_designation",
	"assigned_to_branch",
	"assigned_to_grade",
	"assigned_to_employment_type",
	"assigned_to_employee_group",
)


class HRMSTask(NestedSet):
	nsm_parent_field = "parent_task"

	def validate(self):
		self._validate_weight()
		self._validate_dates()
		self._validate_scope()
		self._validate_approval_routing()
		self._validate_kpi_fields()

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
		"""At least one scope rule must be set, unless 'Applicable to All Active' is ticked.
		SOP Containers (is_group) inherit assignment from their child tasks."""
		if self.applicable_to_all_active:
			return
		if self.is_group:
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
	"""Return dict(label, start, end, due_date) if this frequency 'ticks' today,
	else None. Daily ticks every day; Weekly on Mondays; Monthly on the 1st;
	Quarterly on 1st of Jan/Apr/Jul/Oct; Yearly on 1st Jan. One-time and
	On-demand never auto-tick (instantiated by HR manually)."""
	today_d = getdate(today_d or today())

	if frequency == "Daily":
		return {
			"label": str(today_d),
			"start": today_d,
			"end": today_d,
			"due_date": today_d,
		}
	if frequency == "Weekly":
		if today_d.weekday() != 0:  # Monday=0
			return None
		end = add_days(today_d, 6)
		return {
			"label": f"Week {today_d.isocalendar()[1]} {today_d.year}",
			"start": today_d,
			"end": end,
			"due_date": end,
		}
	if frequency == "Monthly":
		if today_d.day != 1:
			return None
		end = today_d.replace(day=monthrange(today_d.year, today_d.month)[1])
		return {
			"label": today_d.strftime("%B %Y"),
			"start": today_d,
			"end": end,
			"due_date": end,
		}
	if frequency == "Quarterly":
		if today_d.day != 1 or today_d.month not in (1, 4, 7, 10):
			return None
		end_month = today_d.month + 2
		end = today_d.replace(month=end_month, day=monthrange(today_d.year, end_month)[1])
		q = (today_d.month - 1) // 3 + 1
		return {
			"label": f"Q{q} {today_d.year}",
			"start": today_d,
			"end": end,
			"due_date": end,
		}
	if frequency == "Yearly":
		if today_d.day != 1 or today_d.month != 1:
			return None
		end = today_d.replace(month=12, day=31)
		return {
			"label": str(today_d.year),
			"start": today_d,
			"end": end,
			"due_date": end,
		}
	return None  # One-time / On-demand never auto-instantiate


def instantiate_due_tasks(target_date=None):
	"""Scheduler (daily): for each Active leaf HRMS Task whose frequency ticks
	today, create a Goal record (goal_type='Task Instance') per assigned
	Employee. Idempotent — skips (task, employee, period_label) combinations
	that already exist.

	target_date is for testing — defaults to today.
	"""
	today_d = getdate(target_date or today())

	tasks = frappe.get_all(
		"HRMS Task",
		filters={
			"status": "Active",
			"is_group": 0,  # only leaf tasks get instantiated
			"effective_from": ("<=", today_d),
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
			"effective_to",
		],
	)

	created_total = 0
	for task in tasks:
		if task.effective_to and getdate(task.effective_to) < today_d:
			continue

		period_info = compute_period_for_today(task.frequency, today_d)
		if not period_info:
			continue

		assigned = resolve_assigned_employees(task)

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
				created_total += 1
			except Exception:
				frappe.log_error(
					title=f"Task Instance creation failed for {task.name}/{emp_name}",
					message=frappe.get_traceback(),
				)

	if created_total:
		frappe.db.commit()
	return created_total


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
		frappe.db.set_value(
			"Goal", g.name, "last_reminder_sent_on", today_d, update_modified=False
		)

	# (b) HR Manager digest email grouped by Company + KRA
	hr_users = frappe.get_all("Has Role", filters={"role": "HR Manager"}, pluck="parent")
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
