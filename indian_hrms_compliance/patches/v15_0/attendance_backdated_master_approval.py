# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-dated attendance approval.

Creates the `HRMS Master Manager` role and two HR Settings tunables under the
(previously empty) Attendance Settings section:
  * `backdated_attendance_approval_months` (Int, default 2) — how far back an
    attendance date may be before master approval kicks in; 0 disables.
  * `role_allowed_to_approve_backdated_attendance` (Link → Role, default the new
    role) — only this role may submit attendance dated beyond the threshold.

Mirrors the app's existing back-dated *leave* restriction, applied to Attendance
Requests and direct Attendance changes. Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLE = "HRMS Master Manager"

HR_SETTINGS_FIELDS = {
	"HR Settings": [
		{
			"fieldname": "backdated_attendance_approval_months",
			"fieldtype": "Int",
			"label": "Require Master Approval for Attendance Older Than (Months)",
			"insert_after": "attendance_settings_section",
			"default": "2",
			"description": (
				"Attendance Requests and Attendance changes dated more than this "
				"many months in the past can only be submitted by the role below. "
				"Set 0 to disable the restriction."
			),
		},
		{
			"fieldname": "role_allowed_to_approve_backdated_attendance",
			"fieldtype": "Link",
			"options": "Role",
			"label": "Role Allowed to Approve Back-dated Attendance",
			"insert_after": "backdated_attendance_approval_months",
			"default": ROLE,
			"description": (
				"Only users holding this role may submit attendance dated beyond "
				"the months threshold above (Administrator always can)."
			),
		},
	]
}


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	create_custom_fields(HR_SETTINGS_FIELDS, ignore_validate=True)

	if not frappe.db.get_single_value("HR Settings", "backdated_attendance_approval_months"):
		frappe.db.set_single_value("HR Settings", "backdated_attendance_approval_months", 2)
	if not frappe.db.get_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance"):
		frappe.db.set_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance", ROLE)

	frappe.db.commit()
	print(f"  Back-dated attendance: role '{ROLE}' + HR Settings added (default 2 months)")
