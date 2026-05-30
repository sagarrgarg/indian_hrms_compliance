# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_phase4_no_dues_fields():
	"""Custom Fields adding the structured No-Dues clearance table to
	Employee Separation, and the per-Company default template to
	Employee Separation Template.

	Kept as a separate function so fresh installs can call it from
	after_install in the future without re-running the patch."""
	return {
		"Employee Separation": [
			{
				"fieldname": "no_dues_section",
				"fieldtype": "Section Break",
				"label": "No-Dues Clearance",
				"insert_after": "activities",
				"description": (
					"Per-function clearance gate. Each row routes a ToDo to the "
					"owner. Blocking rows must be Cleared before the Separation "
					"can be submitted."
				),
			},
			{
				"fieldname": "no_dues_items",
				"fieldtype": "Table",
				"label": "No-Dues Items",
				"options": "Employee No Dues Item",
				"insert_after": "no_dues_section",
			},
		],
		"Employee Separation Template": [
			{
				"fieldname": "default_no_dues_section",
				"fieldtype": "Section Break",
				"label": "Default No-Dues Items",
				"insert_after": "activities",
				"description": (
					"Default clearance owners + areas for this template. Cloned "
					"into the Separation's no_dues_items on insert."
				),
			},
			{
				"fieldname": "default_no_dues_items",
				"fieldtype": "Table",
				"label": "Default No-Dues Items",
				"options": "Employee No Dues Item",
				"insert_after": "default_no_dues_section",
			},
		],
	}


def execute():
	"""Install Phase 4 No-Dues Custom Fields on Employee Separation and
	Employee Separation Template."""
	create_custom_fields(get_phase4_no_dues_fields(), ignore_validate=True)
	print("  Added no_dues_items table to Employee Separation + Template")
