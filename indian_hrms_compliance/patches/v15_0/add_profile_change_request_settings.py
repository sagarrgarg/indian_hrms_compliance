# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add HR Settings field `self_editable_employee_fields` (Long Text) that lists
which Employee fields can be self-edited via the Employee Profile Change Request
flow. One fieldname per line; blank lines and `#` comments are ignored.

If left blank, the controller falls back to DEFAULT_EDITABLE_FIELDS — so this
patch ships the default text seeded in, giving HR an editable starting point.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


HR_SETTINGS_FIELDS = {
	"HR Settings": [
		{
			"fieldname": "self_editable_employee_fields",
			"fieldtype": "Long Text",
			"label": "Self-Editable Employee Fields",
			"insert_after": "onboarding_min_employment_age",
			"description": (
				"One Employee fieldname per line. Employees can request changes "
				"to these fields via the PWA. Blank lines and lines starting with "
				"'#' are ignored. Leave blank to use the built-in defaults."
			),
		},
	]
}


DEFAULT_TEXT = """# Personal
cell_number
personal_email
current_address
permanent_address
marital_status
blood_group

# Emergency contact
person_to_be_contacted
relation
emergency_phone_number

# Statutory IDs — sensitive; current value is masked in the PWA prefill.
pan_number
aadhaar_number
uan_number
esic_ip_number
provident_fund_account
nps_pran

# Bank
bank_name
bank_ac_no
ifsc_code

# Photo
image
"""


def execute():
	create_custom_fields(HR_SETTINGS_FIELDS, ignore_validate=True)
	current = frappe.db.get_single_value("HR Settings", "self_editable_employee_fields")
	if not current:
		frappe.db.set_single_value("HR Settings", "self_editable_employee_fields", DEFAULT_TEXT)
	frappe.db.commit()
	print("  Profile Change Request: HR Settings field added + seeded default editable list")
