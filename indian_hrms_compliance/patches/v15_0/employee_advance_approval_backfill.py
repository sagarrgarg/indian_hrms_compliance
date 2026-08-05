# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-fill the new Employee Advance approval_status for existing installs.

Employee Advance gained an approval gate (can't submit until Approved). Existing
SUBMITTED advances were already effective, so mark them Approved; drafts start
Draft. Idempotent.
"""

import frappe


def execute():
	if not frappe.get_meta("Employee Advance").has_field("approval_status"):
		return
	frappe.db.sql(
		"""UPDATE `tabEmployee Advance` SET approval_status='Approved'
		   WHERE docstatus=1 AND (approval_status IS NULL OR approval_status IN ('','Draft'))"""
	)
	frappe.db.sql(
		"""UPDATE `tabEmployee Advance` SET approval_status='Draft'
		   WHERE docstatus=0 AND (approval_status IS NULL OR approval_status='')"""
	)
	print("  Employee Advance: back-filled approval_status")
