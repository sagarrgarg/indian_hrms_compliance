# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Salary Structure Validation Log — Phase 6A.

Append-only audit trail of every issue raised by the validator on a
Salary Structure save. Records are intentionally write-once: HR Users
can create (via the validator) and read, but only HR Manager can
delete (for cleanup of historical noise).

Each row = one issue (not one validation run). A single save can
generate multiple log rows (one per check that fired).
"""

import frappe
from frappe.model.document import Document


class SalaryStructureValidationLog(Document):
	pass


def record_issue(salary_structure, severity, code, message):
	"""Insert a log row. Used by the validator. Never raises — log
	failures must not block the user's actual save."""
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Salary Structure Validation Log",
				"salary_structure": salary_structure,
				"severity": severity,
				"issue_code": code,
				"message": message,
				"triggered_by": frappe.session.user,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(
			title=f"Salary Structure Validation Log insert failed for {salary_structure}",
			message=frappe.get_traceback(),
		)
		return None
