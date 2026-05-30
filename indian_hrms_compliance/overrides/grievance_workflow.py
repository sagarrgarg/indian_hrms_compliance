# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 5 doc_event additions to Employee Grievance + workflow setup.

The grievance lifecycle is:
  Open → Manager Review → HR Review → Skip-Level Review → Resolved
                                                        ↘ Invalid

SLA breach reminders are driven by sla_due_date — set on validate from
the severity / Grievance Type defaults / HR Settings fallbacks.

Wired in hooks.py under doc_events["Employee Grievance"].
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today


GRIEVANCE_WORKFLOW = "Grievance Resolution"


# ---- doc_events ----


WORKFLOW_TO_STATUS = {
	"Open": "Open",
	"Manager Review": "Investigated",
	"HR Review": "Investigated",
	"Skip-Level Review": "Investigated",
	"Resolved": "Resolved",
	"Invalid": "Invalid",
}


def compute_sla_due_date(doc, method=None):
	"""validate: derive sla_due_date + sync status from workflow_state.

	Frappe Workflow only updates workflow_state; the underlying status
	field is independent. We mirror them so the existing Submit guard
	(status in Resolved/Invalid) is satisfied when the workflow advances
	to a terminal state."""
	# Sync status from workflow_state.
	if doc.workflow_state and doc.workflow_state in WORKFLOW_TO_STATUS:
		doc.status = WORKFLOW_TO_STATUS[doc.workflow_state]

	# Severity fallback chain: doc.severity → Grievance Type default → "Medium"
	if not doc.severity and doc.grievance_type:
		doc.severity = (
			frappe.db.get_value("Grievance Type", doc.grievance_type, "default_severity")
			or "Medium"
		)

	if doc.sla_due_date:
		return  # HR explicitly set it

	# SLA days chain: Grievance Type default → HR Settings severity default → 14
	sla_days = None
	if doc.grievance_type:
		sla_days = frappe.db.get_value("Grievance Type", doc.grievance_type, "default_sla_days")
	if not sla_days:
		sla_days = _severity_sla_days(doc.severity or "Medium")
	if doc.date and sla_days:
		doc.sla_due_date = add_days(doc.date, int(sla_days))


def _severity_sla_days(severity):
	"""HR Settings severity → SLA days lookup with safe defaults."""
	defaults = {"Critical": 7, "High": 14, "Medium": 21, "Low": 30}
	key = f"grievance_sla_days_{severity.lower()}"
	val = _hr_setting(key)
	return int(val) if val else defaults.get(severity, 21)


def route_grievance_todos(doc, method=None):
	"""on_update: when workflow_state advances, route a ToDo to the right
	approver. Idempotent — keyed on (reference, allocated_to, state).

	Open → Manager Review: ToDo to raised_by.reports_to
	Manager Review → HR Review: ToDo to HR User role holders in Company
	HR Review → Skip-Level: ToDo to manager's reports_to
	"""
	state = doc.workflow_state
	if state not in ("Manager Review", "HR Review", "Skip-Level Review"):
		return

	recipients = _resolve_workflow_recipients(doc, state)
	for user in recipients:
		_upsert_grievance_todo(doc, user, state)


def _resolve_workflow_recipients(doc, state):
	recipients = set()
	if state == "Manager Review":
		reports_to = frappe.db.get_value("Employee", doc.raised_by, "reports_to")
		if reports_to:
			u = frappe.db.get_value("Employee", reports_to, "user_id")
			if u:
				recipients.add(u)
	elif state == "HR Review":
		# HR Users + HR Managers
		for role in ("HR User", "HR Manager"):
			for u in frappe.get_all("Has Role", filters={"role": role}, pluck="parent"):
				if u and u not in ("Administrator", "Guest"):
					recipients.add(u)
	elif state == "Skip-Level Review":
		# Skip-level = raised_by → reports_to → reports_to
		mgr = frappe.db.get_value("Employee", doc.raised_by, "reports_to")
		if mgr:
			skip = frappe.db.get_value("Employee", mgr, "reports_to")
			if skip:
				u = frappe.db.get_value("Employee", skip, "user_id")
				if u:
					recipients.add(u)
	return recipients


def _upsert_grievance_todo(doc, user, state):
	existing = frappe.db.exists(
		"ToDo",
		{
			"reference_type": "Employee Grievance",
			"reference_name": doc.name,
			"allocated_to": user,
			"status": "Open",
			"description": ("like", f"%[{state}]%"),
		},
	)
	if existing:
		return
	description = _(
		"Grievance [{0}] {1}: <a href='/app/employee-grievance/{2}'>{3}</a> "
		"raised by {4}. SLA due {5}."
	).format(
		state,
		doc.severity or "Medium",
		doc.name,
		doc.subject or doc.name,
		doc.employee_name or doc.raised_by,
		doc.sla_due_date or "—",
	)
	try:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"description": description,
				"reference_type": "Employee Grievance",
				"reference_name": doc.name,
				"date": doc.sla_due_date,
				"priority": "High" if doc.severity in ("High", "Critical") else "Medium",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Grievance ToDo failed: {doc.name}/{user}",
			message=frappe.get_traceback(),
		)


# ---- scheduler ----


def send_overdue_grievance_reminders():
	"""Scheduler (daily): for each Open Grievance past sla_due_date that
	hasn't been reminded today, PWA-notify the assignees + HR digest.

	Same NULL-safe pattern as Phase 3/4 reminders."""
	today_d = getdate(today())

	overdue_names = frappe.db.sql(
		"""
		SELECT name FROM `tabEmployee Grievance`
		WHERE status NOT IN ('Resolved', 'Invalid')
		  AND sla_due_date < %s
		  AND (last_reminder_sent_on IS NULL OR last_reminder_sent_on != %s)
		""",
		(today_d, today_d),
		as_dict=False,
	)
	if not overdue_names:
		return

	overdue = frappe.get_all(
		"Employee Grievance",
		filters={"name": ("in", [r[0] for r in overdue_names])},
		fields=[
			"name",
			"subject",
			"raised_by",
			"employee_name",
			"company",
			"severity",
			"sla_due_date",
			"workflow_state",
			"status",
			"grievance_type",
		],
	)
	if not overdue:
		return

	# (a) PWA Notification to each assignee + stamp reminder.
	for g in overdue:
		# Find Open ToDos for this grievance — assume those are the assignees.
		todo_users = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Employee Grievance",
				"reference_name": g.name,
				"status": "Open",
			},
			pluck="allocated_to",
		)
		for user in set(todo_users):
			_safe_pwa_notification(
				to_user=user,
				message=_(
					"Overdue Grievance [{0}]: {1} — SLA was {2}."
				).format(g.severity, g.subject or g.name, g.sla_due_date),
				ref_type="Employee Grievance",
				ref_name=g.name,
			)
		frappe.db.set_value(
			"Employee Grievance", g.name, "last_reminder_sent_on", today_d, update_modified=False
		)

	# (b) HR digest email (gated by HR Settings — same pattern as Phase 3/4).
	if not int(_hr_setting("send_overdue_grievance_hr_digest", 1) or 0):
		return
	recipients_role = _hr_setting("grievance_overdue_recipients_role", "HR Manager") or "HR Manager"
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
			"<tr><th>Grievance</th><th>Type</th><th>Severity</th><th>Raised By</th>"
			"<th>State</th><th>SLA</th><th>Days Overdue</th></tr>"
		)
		for g in sorted(items, key=lambda a: a.sla_due_date or today_d):
			days_late = (today_d - getdate(g.sla_due_date)).days if g.sla_due_date else 0
			rows_html.append(
				f"<tr>"
				f"<td>{frappe.utils.escape_html(g.subject or g.name)}</td>"
				f"<td>{frappe.utils.escape_html(g.grievance_type or '')}</td>"
				f"<td>{frappe.utils.escape_html(g.severity or '')}</td>"
				f"<td>{frappe.utils.escape_html(g.employee_name or g.raised_by or '')}</td>"
				f"<td>{frappe.utils.escape_html(g.workflow_state or g.status or '')}</td>"
				f"<td>{g.sla_due_date or '—'}</td>"
				f"<td style='color:#c0392b'><strong>{days_late}</strong></td>"
				f"</tr>"
			)
		rows_html.append("</table>")

	body = (
		f"<p>{len(overdue)} grievance(s) past SLA across {len(by_company)} company(ies) as of {today_d}.</p>"
		+ "".join(rows_html)
		+ "<p style='margin-top:16px;font-size:12px;color:#777'>Daily digest from indian_hrms_compliance.</p>"
	)
	try:
		frappe.sendmail(
			recipients=hr_users,
			subject=f"[HRMS] Overdue Grievances — {len(overdue)} past SLA",
			message=body,
			now=False,
		)
	except Exception:
		frappe.log_error(title="Grievance overdue digest email failed", message=frappe.get_traceback())


# ---- workflow setup ----


def setup_grievance_workflow():
	"""Idempotent — creates the Workflow, its States and Actions if missing."""
	state_specs = [
		("Open", "Primary"),
		("Manager Review", "Warning"),
		("HR Review", "Warning"),
		("Skip-Level Review", "Warning"),
		("Resolved", "Success"),
		("Invalid", "Danger"),
	]
	for name, style in state_specs:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": style}
			).insert(ignore_permissions=True)

	action_specs = ["Send to Manager", "Escalate to HR", "Escalate to Skip-Level", "Resolve", "Mark Invalid"]
	for action in action_specs:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", GRIEVANCE_WORKFLOW):
		return
	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": GRIEVANCE_WORKFLOW,
			"document_type": "Employee Grievance",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 1,
			"override_status": 0,
			"states": [
				{"state": "Open", "doc_status": "0", "allow_edit": "Employee"},
				{"state": "Manager Review", "doc_status": "0", "allow_edit": "Employee"},
				{"state": "HR Review", "doc_status": "0", "allow_edit": "HR User"},
				{"state": "Skip-Level Review", "doc_status": "0", "allow_edit": "HR Manager"},
				{"state": "Resolved", "doc_status": "1", "allow_edit": "HR Manager"},
				{"state": "Invalid", "doc_status": "1", "allow_edit": "HR Manager"},
			],
			"transitions": [
				{"state": "Open", "action": "Send to Manager", "next_state": "Manager Review", "allowed": "Employee", "allow_self_approval": 1},
				{"state": "Manager Review", "action": "Escalate to HR", "next_state": "HR Review", "allowed": "Employee", "allow_self_approval": 1},
				{"state": "Manager Review", "action": "Resolve", "next_state": "Resolved", "allowed": "Employee", "allow_self_approval": 1},
				{"state": "HR Review", "action": "Escalate to Skip-Level", "next_state": "Skip-Level Review", "allowed": "HR User", "allow_self_approval": 1},
				{"state": "HR Review", "action": "Resolve", "next_state": "Resolved", "allowed": "HR User", "allow_self_approval": 1},
				{"state": "HR Review", "action": "Mark Invalid", "next_state": "Invalid", "allowed": "HR User", "allow_self_approval": 1},
				{"state": "Skip-Level Review", "action": "Resolve", "next_state": "Resolved", "allowed": "HR Manager", "allow_self_approval": 1},
				{"state": "Skip-Level Review", "action": "Mark Invalid", "next_state": "Invalid", "allowed": "HR Manager", "allow_self_approval": 1},
			],
		}
	).insert(ignore_permissions=True)


# ---- helpers (mirrors of Phase 4 _hr_setting / _safe_pwa_notification) ----


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if the field doesn't exist."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
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
		frappe.log_error(title="Grievance PWA notification failed", message=frappe.get_traceback())
