# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""HR Settings: `employee_consent_text_version` (Data, default '1.0').

Both Employee Onboarding Application and Employee Profile Change Request read
this at insert time and snapshot it on the record. Bump the version when the
wording of the consent box meaningfully changes; old consents stay pinned to
their version for audit (DPDP-friendly).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


HR_SETTINGS_FIELDS = {
	"HR Settings": [
		{
			"fieldname": "employee_consent_text_version",
			"fieldtype": "Data",
			"label": "Employee Consent Text Version",
			"insert_after": "self_editable_employee_fields",
			"default": "1.0",
			"description": (
				"Snapshotted on every Onboarding Application and Profile Change "
				"Request at submission time. Bump when the consent wording "
				"materially changes; existing records remain pinned to the "
				"version under which they were captured."
			),
		}
	]
}


def execute():
	create_custom_fields(HR_SETTINGS_FIELDS, ignore_validate=True)
	current = frappe.db.get_single_value("HR Settings", "employee_consent_text_version")
	if not current:
		frappe.db.set_single_value("HR Settings", "employee_consent_text_version", "1.0")
	frappe.db.commit()
	print("  Consent version: HR Settings field added (default '1.0')")
