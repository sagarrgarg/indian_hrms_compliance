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

from functools import partial

import frappe
from frappe.model.document import Document

from indian_hrms_compliance import compat


class SalaryStructureValidationLog(Document):
	pass


def record_issue(salary_structure, severity, code, message):
	"""Insert a log row. Used by the validator. Never raises — log
	failures must not block the user's actual save.

	IMPORTANT: log rows must survive even when the calling save throws
	(e.g. HARD wage_code validation fails → frappe.throw rolls back the
	transaction). We use db.commit() after the insert so the audit trail
	persists regardless of what happens to the parent save."""
	try:
		payload = {
			"doctype": "Salary Structure Validation Log",
			"salary_structure": salary_structure,
			"severity": severity,
			"issue_code": code,
			"message": message,
			"triggered_by": frappe.session.user,
		}
		doc = frappe.get_doc(payload)
		doc.insert(ignore_permissions=True)
		if compat.commit_is_ignored():
			# v16 ignores commit() inside doc_events. If the save then rolls back, write the row
			# again from a background job; on success it commits with the request.
			frappe.db.after_rollback.add(partial(_requeue_log, payload))
		else:
			# Persist immediately so a subsequent HARD throw doesn't roll
			# the audit row back along with the user's save.
			frappe.db.commit()
		return doc.name
	except Exception:
		frappe.log_error(
			title=f"Salary Structure Validation Log insert failed for {salary_structure}",
			message=frappe.get_traceback(),
		)
		return None


def _requeue_log(payload):
	frappe.enqueue(
		"indian_hrms_compliance.hr.doctype.salary_structure_validation_log.salary_structure_validation_log.insert_log",
		queue="short",
		payload=payload,
	)


def insert_log(payload):
	frappe.get_doc(payload).insert(ignore_permissions=True)
