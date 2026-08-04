# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-fill the new Additional Salary approval fields for existing installs.

Additional Salary gained an approval gate (grant only feeds payroll once
Approved) plus a grant_type selector that unifies the old Employee Incentive /
Retention Bonus wrappers. Existing SUBMITTED grants were already effective under
the old model, so mark them Approved — otherwise the new payroll filter would
silently stop them feeding slips. Also classify grant_type from the wrapper that
created each row. Runs once; idempotent.
"""

import frappe


def execute():
	meta = frappe.get_meta("Additional Salary")
	if not (meta.has_field("approval_status") and meta.has_field("grant_type")):
		return

	# Submitted grants keep feeding payroll — they were the control under the old
	# (no-approval) model.
	frappe.db.sql(
		"""UPDATE `tabAdditional Salary`
		   SET approval_status = 'Approved'
		   WHERE docstatus = 1 AND (approval_status IS NULL OR approval_status IN ('', 'Draft'))"""
	)

	# Classify by the wrapper that created it; everything else is generic.
	frappe.db.sql(
		"""UPDATE `tabAdditional Salary`
		   SET grant_type = CASE ref_doctype
		       WHEN 'Employee Incentive' THEN 'Incentive'
		       WHEN 'Retention Bonus'    THEN 'Retention Bonus'
		       ELSE 'Additional Salary' END
		   WHERE grant_type IS NULL OR grant_type = ''"""
	)
	print("  Additional Salary: back-filled approval_status + grant_type")
