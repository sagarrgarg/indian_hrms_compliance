# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class HRMSPolicy(Document):
	def validate(self):
		if self.status == "Active" and not self.effective_date:
			frappe.throw(_("Effective Date is required when publishing the policy (status = Active)."))
		if self.superseded_by and self.superseded_by == self.name:
			frappe.throw(_("A policy cannot supersede itself."))
		if self.acknowledgement_due_days is not None and self.acknowledgement_due_days < 0:
			frappe.throw(_("Acknowledgement Due (days) cannot be negative."))

	def on_update(self):
		if self._just_activated() and self.requires_acknowledgement:
			self.create_acknowledgements()

	def _just_activated(self):
		if self.status != "Active":
			return False
		before = self.get_doc_before_save()
		# Fresh insert with status=Active counts as just-activated.
		if not before:
			return True
		return before.status != "Active"

	def create_acknowledgements(self):
		"""For each applicable Active Employee without an existing acknowledgement
		for this policy version, create a Pending record and notify."""
		employees = self._get_applicable_employees()
		due = add_days(self.effective_date, self.acknowledgement_due_days or 0)
		signed_text = _(
			"I acknowledge that I have read and understood the policy '{0}' version {1} "
			"effective {2}, and agree to abide by it."
		).format(self.policy_name, self.version, self.effective_date)

		created = 0
		for emp in employees:
			if frappe.db.exists(
				"Employee Policy Acknowledgement",
				{"employee": emp.name, "policy": self.name},
			):
				continue
			ack = frappe.get_doc(
				{
					"doctype": "Employee Policy Acknowledgement",
					"employee": emp.name,
					"policy": self.name,
					"due_date": due,
					"signed_text": signed_text,
					"status": "Pending",
				}
			)
			ack.insert(ignore_permissions=True)
			created += 1
			self._notify_employee(emp, ack)

		if created:
			frappe.msgprint(
				_("Created {0} pending acknowledgement(s) for this policy.").format(created)
			)

	def _get_applicable_employees(self):
		"""Active Employees of this Policy's Company. Each Policy is
		Company-scoped — Policies never cross Company boundaries."""
		if not self.company:
			return []
		return frappe.get_all(
			"Employee",
			filters={"status": "Active", "company": self.company},
			fields=["name", "employee_name", "company", "user_id"],
		)

	def _notify_employee(self, employee, ack_doc):
		"""Best-effort PWA Notification to a single Employee on policy publish."""
		if not employee.get("user_id"):
			return
		_safe_pwa_notification(
			to_user=employee.user_id,
			message=_(
				"New HR Policy '{0}' (v{1}): please review and acknowledge by {2}."
			).format(self.policy_name, self.version, ack_doc.due_date),
			ref_type="Employee Policy Acknowledgement",
			ref_name=ack_doc.name,
		)


# ---- module-level functions (scheduler hook + shared notification helper) ----


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
	"""Insert a PWA Notification, suppressing/rolling back any messages
	a sibling chain may emit (e.g., Push Notification decryption errors,
	mail dispatch warnings). The Acknowledgement record itself is the
	source of truth; the notification is best-effort."""
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
		frappe.log_error(title="PWA Notification dispatch failed", message=frappe.get_traceback())


def send_overdue_policy_ack_reminders():
	"""Scheduler (daily): for every Pending Employee Policy Acknowledgement
	whose due_date has passed and that hasn't been reminded today, send:
	  (a) a PWA Notification to the Employee
	  (b) a digest email to HR Manager users covering all overdue acks
	     grouped by company
	"""
	today_d = getdate(today())

	# NULL-safe overdue filter — same pattern as the Task version.
	overdue_names = frappe.db.sql(
		"""
		SELECT name FROM `tabEmployee Policy Acknowledgement`
		WHERE status = 'Pending'
		  AND due_date < %s
		  AND (last_reminder_sent_on IS NULL OR last_reminder_sent_on != %s)
		""",
		(today_d, today_d),
		as_dict=False,
	)
	if not overdue_names:
		return
	overdue = frappe.get_all(
		"Employee Policy Acknowledgement",
		filters={"name": ("in", [r[0] for r in overdue_names])},
		fields=[
			"name",
			"employee",
			"employee_name",
			"company",
			"policy",
			"policy_name_fetched",
			"policy_version",
			"due_date",
		],
	)
	if not overdue:
		return

	# (a) Per-Employee PWA Notification + mark reminded
	for ack in overdue:
		emp_user = frappe.db.get_value("Employee", ack.employee, "user_id")
		if emp_user:
			_safe_pwa_notification(
				to_user=emp_user,
				message=_(
					"Overdue: please acknowledge '{0}' (v{1}) — was due on {2}."
				).format(
					ack.policy_name_fetched or ack.policy,
					ack.policy_version or "",
					ack.due_date,
				),
				ref_type="Employee Policy Acknowledgement",
				ref_name=ack.name,
			)
		frappe.db.set_value(
			"Employee Policy Acknowledgement",
			ack.name,
			"last_reminder_sent_on",
			today_d,
			update_modified=False,
		)

	# (b) Digest email to HR Managers
	hr_users = frappe.get_all("Has Role", filters={"role": "HR Manager"}, pluck="parent")
	hr_users = [u for u in hr_users if u and u not in ("Administrator", "Guest")]

	if not hr_users:
		return

	by_company = defaultdict(list)
	for ack in overdue:
		by_company[ack.company].append(ack)

	rows_html = []
	for company, items in by_company.items():
		rows_html.append(
			f"<h4 style='margin-top:16px'>{frappe.utils.escape_html(company or '(no company)')}</h4>"
		)
		rows_html.append(
			"<table border='1' cellpadding='6' cellspacing='0' "
			"style='border-collapse:collapse;font-size:13px'>"
			"<tr><th>Employee</th><th>Policy</th><th>Version</th>"
			"<th>Due</th><th>Days Overdue</th></tr>"
		)
		for ack in sorted(items, key=lambda a: a.due_date):
			days_late = (today_d - getdate(ack.due_date)).days
			rows_html.append(
				f"<tr>"
				f"<td>{frappe.utils.escape_html(ack.employee_name or ack.employee)}</td>"
				f"<td>{frappe.utils.escape_html(ack.policy_name_fetched or ack.policy)}</td>"
				f"<td>{frappe.utils.escape_html(ack.policy_version or '')}</td>"
				f"<td>{ack.due_date}</td>"
				f"<td style='color:#c0392b'><strong>{days_late}</strong></td>"
				f"</tr>"
			)
		rows_html.append("</table>")

	body = (
		f"<p>{len(overdue)} policy acknowledgement(s) are overdue across "
		f"{len(by_company)} company(ies) as of {today_d}.</p>"
		+ "".join(rows_html)
		+ "<p style='margin-top:16px;font-size:12px;color:#777'>"
		"This is an automated daily digest from indian_hrms_compliance.</p>"
	)

	try:
		frappe.sendmail(
			recipients=hr_users,
			subject=f"[HRMS] Overdue Policy Acknowledgements — {len(overdue)} pending",
			message=body,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title="HRMS overdue-policy digest email failed", message=frappe.get_traceback()
		)
