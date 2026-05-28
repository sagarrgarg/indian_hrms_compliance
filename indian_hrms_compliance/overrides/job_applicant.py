# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _


def detect_internal_applicant(doc, method=None):
	"""doc_event Job Applicant.validate: when email_id matches an Active
	Employee (by company_email, personal_email, or user_id), flag the
	applicant as internal and link the source Employee."""
	if not getattr(doc, "email_id", None):
		if getattr(doc, "is_internal_applicant", 0) or getattr(doc, "source_employee", None):
			doc.is_internal_applicant = 0
			doc.source_employee = None
		return

	match = (
		frappe.db.get_value(
			"Employee",
			{"company_email": doc.email_id, "status": "Active"},
			"name",
		)
		or frappe.db.get_value(
			"Employee",
			{"personal_email": doc.email_id, "status": "Active"},
			"name",
		)
		or frappe.db.get_value(
			"Employee",
			{"user_id": doc.email_id, "status": "Active"},
			"name",
		)
	)

	previous_match = doc.get("source_employee")

	if match:
		doc.is_internal_applicant = 1
		doc.source_employee = match
		if not doc.source:
			if frappe.db.exists("Job Applicant Source", "Internal Mobility"):
				doc.source = "Internal Mobility"
	else:
		doc.is_internal_applicant = 0
		doc.source_employee = None

	if match and (doc.is_new() or previous_match != match):
		_notify_source_manager(doc, match)


def _notify_source_manager(doc, source_employee_name):
	source_emp = frappe.db.get_value(
		"Employee",
		source_employee_name,
		["employee_name", "company", "reports_to"],
		as_dict=True,
	)
	if not source_emp or not source_emp.reports_to:
		return
	manager_user = frappe.db.get_value("Employee", source_emp.reports_to, "user_id")
	if not manager_user:
		return

	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": manager_user,
				"from_user": frappe.session.user or "Administrator",
				"message": _(
					"Internal mobility alert: your team member {0} ({1}) has applied "
					"for a role at {2}. Applicant: {3}."
				).format(
					source_emp.employee_name or source_employee_name,
					source_employee_name,
					doc.get("job_title") or "(no opening)",
					doc.applicant_name or doc.email_id,
				),
				"reference_document_type": "Job Applicant",
				"reference_document_name": doc.name or "",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Internal applicant notification failed for {source_employee_name}",
			message=frappe.get_traceback(),
		)
