"""Drop the legacy back-dated-attendance Custom Fields.

`backdated_attendance_approval_months` and
`role_allowed_to_approve_backdated_attendance` are now standard fields on the
HR Settings doctype (hr_settings.json). On sites where the older
`attendance_backdated_master_approval` patch created them as Custom Fields,
those records now duplicate the standard fields, so remove them. HR Settings is
a Single doctype, so the stored values live in `tabSingles` and survive this
cleanup untouched.

Idempotent: a no-op on sites that never had the Custom Fields (e.g. fresh prod,
which is exactly where the one-shot patch had failed to provision them).
"""

import frappe


def execute():
	frappe.reload_doctype("HR Settings")
	frappe.delete_doc_if_exists(
		"Custom Field", "HR Settings-backdated_attendance_approval_months"
	)
	frappe.delete_doc_if_exists(
		"Custom Field", "HR Settings-role_allowed_to_approve_backdated_attendance"
	)
