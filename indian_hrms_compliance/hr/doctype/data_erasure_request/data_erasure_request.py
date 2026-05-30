# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Data Erasure Request — DPDP Sec 12 right-to-erasure workflow.

Phase 6D. The state machine is:

  Filed → Under Legal Review → Decision Made → Executed
                            ↘ Rejected

Legal review is mandatory because some employee data (PF/ESI, payroll
ledgers, statutory tax records) has hard retention obligations and
cannot legally be erased on demand. The reviewer documents what can be
erased and what cannot.

The actual erasure is NOT auto-executed — HR clicks 'Execute Erasure' on
the form after Decision Made, which calls execute_erasure() to anonymise
the agreed-upon fields/records and log them.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class DataErasureRequest(Document):
	def before_insert(self):
		if not self.workflow_state:
			self.workflow_state = "Filed"
		if not self.requested_by:
			# Default to the employee's own user if not set
			emp_user = frappe.db.get_value("Employee", self.employee, "user_id")
			if emp_user:
				self.requested_by = emp_user

	def validate(self):
		# When advancing to Decision Made, decision + rationale required.
		if self.workflow_state == "Decision Made":
			if not self.decision:
				frappe.throw(_("Decision is required before moving to 'Decision Made'."))
			if not self.legal_reviewed_by:
				frappe.throw(
					_("Legal Reviewed By is required before moving to 'Decision Made'.")
				)
			if not self.legal_reviewed_on:
				self.legal_reviewed_on = today()
		if self.workflow_state == "Rejected" and not self.decision_rationale:
			frappe.throw(_("Decision Rationale is required to Reject."))


@frappe.whitelist()
def execute_erasure(name):
	"""Whitelisted — performs the erasure for an approved Data Erasure
	Request. Marks records as [Anonymized] in scope; logs each touched
	doctype/record into erasure_log + Data Access Log.

	v1 SAFETY: This is conservative. It ONLY anonymises fields on the
	Employee record itself (the personal_email, current_address,
	emergency_phone_number, etc.). It does NOT delete payroll or
	statutory records (Salary Slip, PF, Form 16) — those have hard
	retention obligations that the legal reviewer must have honoured.
	"""
	doc = frappe.get_doc("Data Erasure Request", name)
	if doc.workflow_state != "Decision Made":
		frappe.throw(_("Erasure can only be executed from 'Decision Made' state."))
	if doc.decision not in ("Approved Full", "Approved Partial"):
		frappe.throw(_("Decision must be Approved Full or Approved Partial."))
	if not frappe.has_permission("Data Erasure Request", "write", doc=doc):
		frappe.throw(_("You are not permitted to execute this erasure."))

	touched = []
	# Conservative v1 — only Employee-level non-statutory fields.
	ERASABLE_EMP_FIELDS = [
		"personal_email",
		"emergency_phone_number",
		"current_address",
		"permanent_address",
		"bio",
		"person_of_contact",
		"emergency_contact_name",
	]
	emp_meta = frappe.get_meta("Employee")
	emp_fields_present = {f.fieldname for f in emp_meta.fields}
	target_fields = [f for f in ERASABLE_EMP_FIELDS if f in emp_fields_present]

	for fn in target_fields:
		try:
			current_val = frappe.db.get_value("Employee", doc.employee, fn)
			if current_val:
				frappe.db.set_value(
					"Employee", doc.employee, fn, "[Anonymized]", update_modified=False
				)
				touched.append({"doctype": "Employee", "name": doc.employee, "field": fn})
		except Exception:
			frappe.log_error(
				title=f"DPDP erasure: failed on Employee.{fn} for {doc.employee}",
				message=frappe.get_traceback(),
			)

	# Stamp + log
	doc.db_set("erasure_executed_on", today(), update_modified=False)
	doc.db_set("erasure_log", json.dumps(touched, indent=2), update_modified=False)
	doc.db_set("workflow_state", "Executed", update_modified=False)

	# Write a Data Access Log entry per touched field (access_type=Email
	# is reserved; we tag access_type=Read with request_context noting the
	# erasure for now — extending Select to add 'Erase' would need a patch).
	try:
		from indian_hrms_compliance.overrides.dpdp_access_logger import (
			log_field_access,
		)

		for t in touched:
			log_field_access(
				subject_doctype=t["doctype"],
				subject_record=t["name"],
				subject_employee=doc.employee,
				field_accessed=t["field"],
				access_type="Read",
				request_context=f"DPDP Erasure: {doc.name}",
			)
	except Exception:
		frappe.log_error(
			title=f"DPDP erasure: log write failed for {doc.name}",
			message=frappe.get_traceback(),
		)

	frappe.msgprint(_("Erasure executed: {0} field(s) anonymised.").format(len(touched)))
	return {"touched_count": len(touched), "touched": touched}
