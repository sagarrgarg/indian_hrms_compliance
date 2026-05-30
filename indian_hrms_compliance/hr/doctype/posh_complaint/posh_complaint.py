# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""POSH Complaint controller.

Confidentiality model: this doctype is strictly access-controlled via
permission_query_conditions (see overrides/posh_access.py). Only the
complainant, the accused, and active IC members of the complainant's
Company can read individual complaints. HR Manager / HR User can see
aggregate stats only — they cannot read complaint detail by default.
This implements the spirit of Sec 16 of POSH Act 2013.

The doctype is not submittable — it's a working record that goes
through workflow states (Filed → Acknowledged → Inquiry → Findings
Recorded → Action Recommended → Closed) with date stamps captured
automatically as each stage is entered.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


POSH_STATUTORY_SLA_DAYS = 90  # Sec 11 of POSH Act 2013


class POSHComplaint(Document):
	def before_insert(self):
		# Auto-link the Active IC for this Company if not set.
		if not self.internal_committee and self.company:
			ic = frappe.db.get_value(
				"POSH Internal Committee",
				{"company": self.company, "status": "Active"},
				"name",
				order_by="constitution_date desc",
			)
			if ic:
				self.internal_committee = ic
		if not self.workflow_state:
			self.workflow_state = "Filed"

	def validate(self):
		self._compute_masked_display()
		self._compute_sla()
		self._stamp_state_dates()
		self._validate_ic_belongs_to_company()

	def _compute_masked_display(self):
		"""Populate complainant_name_masked + complainant_employee_id_masked
		so the form / list show '<Anonymous Complainant>' when anonymous=1
		without losing the underlying Link."""
		if self.anonymous:
			self.complainant_name_masked = _("<Anonymous Complainant>")
			self.complainant_employee_id_masked = "—"
		elif self.complainant:
			self.complainant_name_masked = (
				frappe.db.get_value("Employee", self.complainant, "employee_name") or self.complainant
			)
			self.complainant_employee_id_masked = self.complainant
		else:
			self.complainant_name_masked = ""
			self.complainant_employee_id_masked = ""

	def _compute_sla(self):
		if self.filing_date and not self.sla_due_date:
			self.sla_due_date = add_days(self.filing_date, POSH_STATUTORY_SLA_DAYS)

	def _stamp_state_dates(self):
		"""Capture the date each state was first entered. Once stamped, we
		don't overwrite — gives a clean audit trail."""
		state = self.workflow_state
		if state == "Acknowledged" and not self.filing_acknowledged_on:
			self.filing_acknowledged_on = today()
		elif state == "Inquiry" and not self.inquiry_started_on:
			self.inquiry_started_on = today()
		elif state == "Findings Recorded" and not self.findings_recorded_on:
			self.findings_recorded_on = today()
		elif state == "Action Recommended" and not self.action_recommended_on:
			self.action_recommended_on = today()
		elif state == "Closed" and not self.closed_on:
			self.closed_on = today()

	def _validate_ic_belongs_to_company(self):
		if self.internal_committee and self.company:
			ic_company = frappe.db.get_value(
				"POSH Internal Committee", self.internal_committee, "company"
			)
			if ic_company != self.company:
				frappe.throw(
					_("The selected Internal Committee belongs to {0}, but this complaint is filed in {1}.").format(
						ic_company, self.company
					)
				)

	def on_update(self):
		# Notify IC members on first save (Filed state) — best-effort.
		before = self.get_doc_before_save()
		if not before:
			self._alert_ic_members_new_filing()

	def _alert_ic_members_new_filing(self):
		ic_doc = frappe.get_doc("POSH Internal Committee", self.internal_committee)
		if not int(getattr(ic_doc, "send_complaint_alerts", 1) or 0):
			return
		users = ic_doc.get_active_member_users()
		for user in users:
			_safe_pwa_notification(
				to_user=user,
				message=_("A new POSH complaint has been filed. Please review confidentially."),
				ref_type="POSH Complaint",
				ref_name=self.name,
			)
			# Also a ToDo so it shows in their inbox.
			try:
				frappe.get_doc(
					{
						"doctype": "ToDo",
						"allocated_to": user,
						"description": _(
							"Confidential POSH complaint filed {0}. SLA due {1}."
						).format(self.filing_date, self.sla_due_date),
						"reference_type": "POSH Complaint",
						"reference_name": self.name,
						"priority": "High",
						"date": self.sla_due_date,
					}
				).insert(ignore_permissions=True)
			except Exception:
				pass


# ---- module-level scheduler ----


def send_posh_overdue_reminders():
	"""Scheduler (daily): for each open POSH Complaint past sla_due_date
	that hasn't been reminded today, PWA-notify the IC members.

	No HR digest by default — POSH is confidential. HR can opt-in to
	receive aggregate counts via a future report."""
	today_d = getdate(today())
	overdue_names = frappe.db.sql(
		"""
		SELECT name FROM `tabPOSH Complaint`
		WHERE workflow_state NOT IN ('Closed')
		  AND sla_due_date < %s
		  AND (last_reminder_sent_on IS NULL OR last_reminder_sent_on != %s)
		""",
		(today_d, today_d),
		as_dict=False,
	)
	if not overdue_names:
		return
	for row in overdue_names:
		complaint = frappe.get_doc("POSH Complaint", row[0])
		try:
			ic = frappe.get_doc("POSH Internal Committee", complaint.internal_committee)
		except Exception:
			continue
		for user in ic.get_active_member_users():
			_safe_pwa_notification(
				to_user=user,
				message=_(
					"OVERDUE: POSH complaint {0} is past the statutory 90-day SLA "
					"(due {1}). Inquiry must be expedited."
				).format(complaint.name, complaint.sla_due_date),
				ref_type="POSH Complaint",
				ref_name=complaint.name,
			)
		frappe.db.set_value(
			"POSH Complaint", complaint.name, "last_reminder_sent_on", today_d, update_modified=False
		)


# ---- helpers ----


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
		frappe.log_error(title="POSH notification failed", message=frappe.get_traceback())
