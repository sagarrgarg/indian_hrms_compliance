# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add a 'permanent address same as current' convenience toggle on Employee.

erpnext Employee already ships current_address + permanent_address (Small Text)
but no auto-copy. This adds a single Check custom field anchored under
permanent_address; the copy itself is driven by employee.js (live) and
apply_address_copy_rules (server, on validate) so it stays correct for imports
and API writes too.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"Employee": [
			{
				"fieldname": "permanent_address_same_as_current",
				"fieldtype": "Check",
				"label": "Permanent address same as current address",
				"insert_after": "permanent_address",
				"default": "0",
				"description": "Tick to copy the Current Address into the Permanent Address.",
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Employee.permanent_address_same_as_current toggle")
