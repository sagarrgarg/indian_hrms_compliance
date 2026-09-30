# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Allow Salary Slip in Repost Accounting Ledger Settings.

The repost_allowed_doctypes hook routes a Salary Slip repost to its
make_gl_entries; ERPNext still refuses any voucher type not ticked in the
settings, so add the row. Idempotent.
"""

import frappe


def execute():
	settings = frappe.get_single("Repost Accounting Ledger Settings")
	row = next((d for d in settings.allowed_types if d.document_type == "Salary Slip"), None)
	if row and row.allowed:
		return
	if row:
		row.allowed = 1
	else:
		settings.append("allowed_types", {"document_type": "Salary Slip", "allowed": 1})
	settings.flags.ignore_permissions = True
	settings.save()
