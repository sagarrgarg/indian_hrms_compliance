"""Drop the legacy `auto_assign_leave_policy_on_activation` Custom Field.

The opt-in toggle is now a standard field on the HR Settings doctype
(hr_settings.json). On sites where the older `add_employee_onboarding_defaults`
patch had already created it as a Custom Field, that record now duplicates the
standard field, so remove it. HR Settings is a Single doctype, so the stored
value lives in `tabSingles` and survives this cleanup untouched.

Idempotent: a no-op on sites that never had the Custom Field (e.g. fresh prod).
"""

import frappe


def execute():
	frappe.reload_doctype("HR Settings")
	frappe.delete_doc_if_exists(
		"Custom Field", "HR Settings-auto_assign_leave_policy_on_activation"
	)
