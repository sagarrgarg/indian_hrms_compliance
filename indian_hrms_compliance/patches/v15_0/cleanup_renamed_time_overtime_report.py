# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Delete orphaned Report docs left by renaming the time/overtime report.

The report was 'Overtime Register' -> 'Time & Overtime Register' -> final
'Time and Overtime Register'. The '&' variant scrubs to an invalid module name
(time_&_overtime_register) and 500s on open, and the old 'Overtime Register' doc
no longer has code behind it. Delete both if present; the current standard report
re-syncs from code on this same migrate. Idempotent.
"""

import frappe


def execute():
	for stale in ("Overtime Register", "Time & Overtime Register"):
		if frappe.db.exists("Report", stale):
			frappe.delete_doc("Report", stale, ignore_permissions=True, force=True)
			print(f"  Deleted stale report: {stale}")
