# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""HR Cockpit — one aggregated payload for the PWA dashboard.

Composes existing signals (Compliance Filing, Goal task instances, Leave
Application, Employee, Policy Acknowledgement, the approvals inbox) into the
five cockpit zones: KPIs, Compliance & Documents, My Actions, People Pulse,
Trends. Every section is independently guarded so one empty/erroring source
never blanks the whole dashboard.

Scope: HR-only, and **company-scoped** to the HR user's own company (resolved
from their Employee record). Administrator / a user with no Employee sees all
companies.
"""

import frappe
from frappe.utils import add_days, add_months, get_first_day, getdate, nowdate

FILED_STATUSES = ("Filed", "Late Filed", "Waived", "Not Applicable")
DUE_SOON_DAYS = 30
COCKPIT_ROLES = ("HR Manager", "HR User", "System Manager")


def _period_range(period):
	today = getdate(nowdate())
	if period == "Daily":
		return today, today
	if period == "Weekly":
		return add_days(today, -6), today
	return get_first_day(today), today  # Monthly (default)


def _scope_company():
	"""The company this HR user's cockpit is limited to. Their primary/active
	Employee's company; None (all companies) for Administrator or a user with
	no Employee record."""
	user = frappe.session.user
	if user == "Administrator":
		return None
	primary = frappe.db.get_value(
		"Employee", {"user_id": user, "status": "Active", "is_primary_employer": 1}, "company"
	)
	if primary:
		return primary
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "company")


def _company_employees(company):
	if not company:
		return None
	emps = frappe.get_all("Employee", filters={"company": company}, pluck="name")
	return emps or ["__none__"]  # match nothing if the company has no employees


@frappe.whitelist()
def can_view_cockpit() -> bool:
	"""Lightweight role check the PWA uses to show/hide the cockpit entry."""
	return bool(set(COCKPIT_ROLES) & set(frappe.get_roles()))


@frappe.whitelist()
def get_hr_cockpit(period: str = "Monthly") -> dict:
	# Org-wide HR aggregates — restrict to HR roles, not every ESS user.
	frappe.only_for(COCKPIT_ROLES)
	period = period if period in ("Daily", "Weekly", "Monthly") else "Monthly"
	today = getdate(nowdate())
	start, end = _period_range(period)
	company = _scope_company()
	emps = _company_employees(company)

	ctx = {"today": today, "start": start, "end": end, "company": company, "emps": emps, "period": period}

	payload = {
		"period": period,
		"as_of": str(today),
		"company": company,
		"kpis": [],
		"compliance": {"overdue": [], "due_soon": [], "done": [], "totals": {}},
		"actions": [],
		"people": [],
		"trends": {},
		"readiness": {},
		"coverage": {},
	}
	_safe(payload, "kpis", _build_kpis, ctx)
	_safe(payload, "compliance", _build_compliance, ctx)
	_safe(payload, "actions", _build_actions, ctx)
	_safe(payload, "people", _build_people, ctx)
	_safe(payload, "trends", _build_trends, ctx)
	_safe(payload, "readiness", _build_readiness, ctx)
	_safe(payload, "coverage", _build_coverage, ctx)
	return payload


def _build_readiness(ctx):
	from indian_hrms_compliance.overrides.employee_master import get_employee_readiness_summary

	return get_employee_readiness_summary(ctx["company"])


def _build_coverage(ctx):
	"""Governance gaps in the task framework, company-scoped:
	- uncovered KRAs: Active KRAs with no Active HRMS Task rolling up to them.
	- unassigned tasks: Active HRMS Tasks whose scope resolves to 0 Active
	  Employees (nobody will ever get an instance).
	Both are things HR must fix, surfaced with a route into the manage view."""
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import resolve_assigned_employees

	kra_filters = {"status": "Active"}
	task_filters = {"status": "Active", "is_group": 0}
	if ctx["company"]:
		kra_filters["company"] = ctx["company"]
		task_filters["company"] = ctx["company"]

	active_kras = frappe.get_all("KRA", filters=kra_filters, fields=["name", "title", "kra_category"])
	tasks = frappe.get_all(
		"HRMS Task",
		filters=task_filters,
		fields=[
			"name", "task_name", "kra", "company", "applicable_to_all_active",
			"assigned_to_department", "assigned_to_designation", "assigned_to_branch",
			"assigned_to_grade", "assigned_to_employment_type", "assigned_to_employee_group",
		],
	)

	kras_with_task = {t.kra for t in tasks if t.kra}
	uncovered = [
		{"name": k.name, "title": k.title or k.name, "category": k.kra_category or ""}
		for k in active_kras
		if k.name not in kras_with_task
	]

	unassigned = []
	for t in tasks:
		if not resolve_assigned_employees(frappe._dict(t)):
			unassigned.append({"name": t.name, "task_name": t.task_name, "kra": t.kra or ""})

	return {
		"uncovered_kras": uncovered,
		"unassigned_tasks": unassigned,
		"totals": {
			"active_kras": len(active_kras),
			"active_tasks": len(tasks),
			"uncovered_kras": len(uncovered),
			"unassigned_tasks": len(unassigned),
		},
	}


def _safe(payload, key, fn, ctx):
	try:
		payload[key] = fn(ctx)
	except Exception:
		frappe.log_error(title=f"HR Cockpit section '{key}' failed", message=frappe.get_traceback())


def _count(doctype, filters):
	try:
		return frappe.db.count(doctype, filters)
	except Exception:
		return 0


def _co(ctx, base=None):
	"""Filter dict with the scoped company merged in (when a doctype has a
	`company` field)."""
	f = dict(base or {})
	if ctx["company"]:
		f["company"] = ctx["company"]
	return f


def _emp_filter(ctx):
	"""For doctypes without a company field (e.g. Goal) — scope by employee."""
	return {"employee": ("in", ctx["emps"])} if ctx["emps"] else {}


# --------------------------------------------------------------------------- KPIs
def _build_kpis(ctx):
	today = ctx["today"]
	headcount = _count("Employee", _co(ctx, {"status": "Active"}))

	on_leave = _count(
		"Leave Application",
		_co(ctx, {"docstatus": 1, "status": "Approved", "from_date": ("<=", today), "to_date": (">=", today)}),
	)
	present_today = _count("Attendance", _co(ctx, {"attendance_date": today, "status": "Present", "docstatus": 1}))

	try:
		pending_approvals = len(frappe.call("indian_hrms_compliance.api.get_pending_approvals"))
	except Exception:
		pending_approvals = 0

	joiners = _count("Employee", _co(ctx, {"date_of_joining": ("between", [ctx["start"], ctx["end"]])}))

	plabel = {"Daily": "Today", "Weekly": "This Week", "Monthly": "This Month"}[ctx["period"]]
	return [
		{"key": "headcount", "label": "Active Employees", "value": headcount, "icon": "users", "tone": "brand"},
		{"key": "present", "label": "Present Today", "value": present_today, "icon": "check-circle", "tone": "green"},
		{"key": "on_leave", "label": "On Leave Today", "value": on_leave, "icon": "sun", "tone": "amber"},
		{"key": "approvals", "label": "My Approvals", "value": pending_approvals, "icon": "inbox", "tone": "violet"},
		{"key": "joiners", "label": f"Joined {plabel}", "value": joiners, "icon": "user-plus", "tone": "blue"},
	]


# --------------------------------------------------------------------- Compliance
def _build_compliance(ctx):
	today = ctx["today"]
	horizon = add_days(today, DUE_SOON_DAYS)
	month_start = get_first_day(today)

	ret_overdue = _count("Compliance Filing", _co(ctx, {"due_date": ("<", today), "filing_status": ("not in", FILED_STATUSES)}))
	ret_due = _count("Compliance Filing", _co(ctx, {"due_date": ("between", [today, horizon]), "filing_status": ("not in", FILED_STATUSES)}))
	ret_done = _count("Compliance Filing", _co(ctx, {"due_date": (">=", month_start), "filing_status": ("in", ("Filed", "Late Filed"))}))

	tf = {"goal_type": "Task Instance", **_emp_filter(ctx)}
	task_overdue = _count("Goal", {**tf, "status": ("in", ("Pending", "In Progress")), "due_date": ("<", today)})
	task_due = _count("Goal", {**tf, "status": ("in", ("Pending", "In Progress")), "due_date": ("between", [today, horizon])})
	task_done = _count("Goal", {**tf, "status": "Completed", "modified": (">=", month_start)})

	def trio(ret, task):
		return [
			{"label": "Statutory returns", "count": ret, "route": "ComplianceFilings"},
			{"label": "Tasks", "count": task, "route": "TasksDashboard"},
		]

	return {
		"overdue": trio(ret_overdue, task_overdue),
		"due_soon": trio(ret_due, task_due),
		"done": trio(ret_done, task_done),
		"totals": {
			"overdue": ret_overdue + task_overdue,
			"due_soon": ret_due + task_due,
			"done": ret_done + task_done,
		},
	}


# ------------------------------------------------------------------------- Actions
def _build_actions(ctx):
	today = ctx["today"]
	try:
		approvals = len(frappe.call("indian_hrms_compliance.api.get_pending_approvals"))
	except Exception:
		approvals = 0

	ack_filter = {"status": "Pending"}
	if ctx["emps"]:
		ack_filter["employee"] = ("in", ctx["emps"])
	acks = _count("Employee Policy Acknowledgement", ack_filter)

	tasks_overdue = _count(
		"Goal",
		{"goal_type": "Task Instance", "status": ("in", ("Pending", "In Progress")), "due_date": ("<", today), **_emp_filter(ctx)},
	)
	return [
		{"label": "Approvals to action", "count": approvals, "route": "ApprovalsInbox", "icon": "inbox",
		 "tone": "amber" if approvals else "grey"},
		{"label": "Policy acknowledgements pending", "count": acks, "route": "PoliciesDashboard", "icon": "file-text",
		 "tone": "red" if acks else "green"},
		{"label": "Overdue tasks", "count": tasks_overdue, "route": "TasksDashboard", "icon": "alert-circle",
		 "tone": "red" if tasks_overdue else "green"},
	]


# -------------------------------------------------------------------------- People
def _build_people(ctx):
	today = ctx["today"]
	joiners = _count("Employee", _co(ctx, {"date_of_joining": ("between", [ctx["start"], ctx["end"]])}))
	exits = _count("Employee", _co(ctx, {"relieving_date": ("between", [ctx["start"], ctx["end"]])}))

	week_end = add_days(today, 7)
	birthdays = 0
	try:
		rows = frappe.get_all(
			"Employee",
			filters=_co(ctx, {"status": "Active", "date_of_birth": ("is", "set")}),
			pluck="date_of_birth",
		)
		md_today = (today.month, today.day)
		md_end = (week_end.month, week_end.day)
		for dob in rows:
			d = getdate(dob)
			md = (d.month, d.day)
			if md_today <= md_end:
				if md_today <= md <= md_end:
					birthdays += 1
			elif md >= md_today or md <= md_end:
				birthdays += 1
	except Exception:
		birthdays = 0

	return [
		{"label": "New Joiners", "count": joiners, "icon": "user-plus", "tone": "green"},
		{"label": "Exits", "count": exits, "icon": "user-minus", "tone": "red"},
		{"label": "Birthdays this week", "count": birthdays, "icon": "gift", "tone": "blue"},
	]


# -------------------------------------------------------------------------- Trends
def _build_trends(ctx):
	today = ctx["today"]
	labels, points = [], []
	for i in range(5, -1, -1):
		m_start = get_first_day(add_months(today, -i))
		m_end = add_days(get_first_day(add_months(today, -i + 1)), -1)
		labels.append(m_start.strftime("%b"))
		points.append(_count("Employee", _co(ctx, {"date_of_joining": ("between", [m_start, m_end])})))

	ll, lp = [], []
	for i in range(6, -1, -1):
		d = add_days(today, -i)
		ll.append(d.strftime("%d"))
		lp.append(_count("Leave Application", _co(ctx, {"docstatus": 1, "status": "Approved", "from_date": ("<=", d), "to_date": (">=", d)})))

	return {
		"joiners": {"label": "New Joiners (6 mo)", "labels": labels, "points": points},
		"on_leave": {"label": "On Leave (7 days)", "labels": ll, "points": lp},
	}
