# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Disciplinary Action — Phase 5 Stage 3.

The closer of the compliance arc. Receives input from Grievance / POSH
Complaint / direct HR initiation, runs the show-cause → inquiry →
outcome workflow, and fires downstream documents based on outcome:

  Termination / Dismissal → auto-create Phase 4 Resignation Request
                           (request_type=Termination, reason=Misconduct)
                           → triggers the full Phase 4 exit chain.
  Written / Final Warning → auto-create Appointment Letter with
                           letter_type='Warning Letter' (requires
                           Phase 5 Stage 4 to seed the type).
  Suspension              → auto-create Salary Withholding for the
                           suspension period.
  PIP                     → currently informational; future hook can
                           create a Probation Review re-trigger.

All triggers are idempotent — re-saving the doc doesn't re-create.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


STATE_DATE_FIELD_MAP = {
	"Show-Cause Issued": "show_cause_issued_on",
	"Response Received": "response_received_on",
	"Under Inquiry": "inquiry_completed_on",
	"Outcome Decided": "outcome_decided_on",
	"Closed": "closed_on",
}


class DisciplinaryAction(Document):
	def before_insert(self):
		if not self.workflow_state:
			self.workflow_state = "Initiated"

	def validate(self):
		self._stamp_state_dates()
		self._validate_suspension_dates()

	def _stamp_state_dates(self):
		field = STATE_DATE_FIELD_MAP.get(self.workflow_state)
		if field and not self.get(field):
			self.set(field, today())

	def _validate_suspension_dates(self):
		if self.outcome != "Suspension":
			return
		if self.suspension_from and self.suspension_to:
			if getdate(self.suspension_to) < getdate(self.suspension_from):
				frappe.throw(_("Suspension To cannot be before Suspension From."))

	def on_update(self):
		# Fire outcome triggers once workflow lands at Outcome Decided (or Closed
		# if HR went straight there). Idempotent — each trigger checks its own
		# linkage field before creating.
		if self.workflow_state not in ("Outcome Decided", "Closed"):
			return
		if not self.outcome:
			return
		self._trigger_termination()
		self._trigger_warning_letter()
		self._trigger_salary_withholding()
		self._back_link_source()

	def _trigger_termination(self):
		if self.outcome not in ("Termination", "Dismissal"):
			return
		if self.linked_resignation_request:
			return  # already triggered
		rr = frappe.get_doc(
			{
				"doctype": "Resignation Request",
				"request_type": "Termination",
				"employee": self.employee,
				"submission_date": self.outcome_decided_on or today(),
				"reason_category": "Misconduct (Termination)",
				"reason_details": (
					f"Auto-created from Disciplinary Action {self.name}: "
					f"{self.outcome}. {self.outcome_narrative or ''}"
				).strip(),
				"notice_required_days": 0,
				"notice_offered_days": 0,
				"notice_disposition": "Pay in Lieu of Notice",
			}
		)
		rr.insert(ignore_permissions=True)
		# Walk the workflow legally from Draft → Pending HR Approval using the
		# "Forward to HR" transition (intended for HR-initiated termination).
		try:
			from frappe.model.workflow import apply_workflow

			apply_workflow(rr, "Forward to HR")
		except Exception:
			# Workflow transition may fail if user lacks HR User role at the
			# time the trigger fires (e.g., scheduler context). The RR is
			# still created in Draft — HR can move it manually.
			pass
		self.db_set("linked_resignation_request", rr.name, update_modified=False)
		frappe.msgprint(
			_("Created Resignation Request {0} (Termination) for this outcome.").format(
				frappe.utils.get_link_to_form("Resignation Request", rr.name)
			)
		)

	def _trigger_warning_letter(self):
		if self.outcome not in ("Written Warning", "Final Warning"):
			return
		if self.linked_warning_letter:
			return  # already triggered
		# Use the Warning Letter Template if seeded (Phase 5 Stage 4).
		template = frappe.db.get_value(
			"Appointment Letter Template", {"letter_type": "Warning Letter"}, "name"
		)
		if not template:
			# Stage 4 hasn't shipped yet — skip silently. HR can issue manually.
			return
		employee_name = (
			frappe.db.get_value("Employee", self.employee, "employee_name") or self.employee
		)
		try:
			letter = frappe.get_doc(
				{
					"doctype": "Appointment Letter",
					"job_applicant": "",
					"applicant_name": employee_name,
					"appointment_date": self.outcome_decided_on or today(),
					"company": self.company,
					"appointment_letter_template": template,
					"letter_type": "Warning Letter",
					"employee": self.employee,
				}
			)
			letter.insert(ignore_permissions=True, ignore_mandatory=True)
			self.db_set("linked_warning_letter", letter.name, update_modified=False)
			frappe.msgprint(
				_("Created Warning Letter {0} for this outcome.").format(
					frappe.utils.get_link_to_form("Appointment Letter", letter.name)
				)
			)
		except Exception:
			frappe.log_error(
				title=f"Warning Letter auto-create failed: {self.name}",
				message=frappe.get_traceback(),
			)

	def _trigger_salary_withholding(self):
		if self.outcome != "Suspension":
			return
		if self.linked_salary_withholding:
			return
		if not (self.suspension_from and self.suspension_to):
			return
		try:
			# Salary Withholding requires payroll_frequency + cycles. We'll
			# create a single-cycle hold covering the suspension period; HR
			# can extend it manually if needed.
			from frappe.utils import date_diff

			days = max(date_diff(self.suspension_to, self.suspension_from) + 1, 1)
			# Approximate cycles by treating one month per cycle.
			cycles = max(round(days / 30), 1)

			sw = frappe.get_doc(
				{
					"doctype": "Salary Withholding",
					"employee": self.employee,
					"posting_date": self.suspension_from,
					"from_date": self.suspension_from,
					"to_date": self.suspension_to,
					"number_of_withholding_cycles": cycles,
					"reason_for_withholding_salary": (
						f"Suspension per Disciplinary Action {self.name}. "
						f"{self.outcome_narrative or ''}"
					).strip(),
				}
			)
			sw.insert(ignore_permissions=True, ignore_mandatory=True)
			self.db_set("linked_salary_withholding", sw.name, update_modified=False)
			frappe.msgprint(
				_("Created Salary Withholding {0} for the suspension period.").format(
					frappe.utils.get_link_to_form("Salary Withholding", sw.name)
				)
			)
		except Exception:
			frappe.log_error(
				title=f"Salary Withholding auto-create failed: {self.name}",
				message=frappe.get_traceback(),
			)

	def _back_link_source(self):
		"""Update linked Grievance / POSH Complaint with this Disciplinary
		Action — closes the loop visually."""
		if self.linked_grievance:
			frappe.db.set_value(
				"Employee Grievance",
				self.linked_grievance,
				"linked_disciplinary_action",
				self.name,
				update_modified=False,
			)
		if self.linked_posh_complaint:
			frappe.db.set_value(
				"POSH Complaint",
				self.linked_posh_complaint,
				"linked_disciplinary_action",
				self.name,
				update_modified=False,
			)
