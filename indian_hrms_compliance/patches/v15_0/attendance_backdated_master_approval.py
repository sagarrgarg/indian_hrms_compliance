# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-dated attendance approval — role + defaults.

The two tunables `backdated_attendance_approval_months` and
`role_allowed_to_approve_backdated_attendance` are standard fields on the
HR Settings doctype (hr_settings.json), so they sync on every migrate — no
custom fields. This patch only ensures the approval Role exists and seeds the
defaults. Idempotent.
"""

import frappe

ROLE = "HRMS Master Manager"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	if not frappe.db.get_single_value("HR Settings", "backdated_attendance_approval_months"):
		frappe.db.set_single_value("HR Settings", "backdated_attendance_approval_months", 2)
	if not frappe.db.get_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance"):
		frappe.db.set_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance", ROLE)
