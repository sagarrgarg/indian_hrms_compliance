# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add a 'Documents' child table on Employee, reusing the same child doctype
('Employee Onboarding Document') that the Employee Onboarding Application uses.

This mirrors the candidate's uploaded-documents table onto the Employee so the
structured list (type + file + notes) is visible on the Employee form, and so
mark_converted can copy the rows across as-is on conversion.

Anchored after place_of_issue, the last field of the Personal Details tab, so
the new Section Break starts a fresh section at the tail of that tab and does
not capture any existing fields (see frappe-framework skill §4).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"Employee": [
			{
				"fieldname": "employee_documents_section",
				"fieldtype": "Section Break",
				"label": "Documents",
				"insert_after": "place_of_issue",
				"collapsible": 1,
			},
			{
				"fieldname": "employee_documents",
				"fieldtype": "Table",
				"label": "Documents",
				"options": "Employee Onboarding Document",
				"insert_after": "employee_documents_section",
				"description": (
					"Identity & statutory documents (PAN, Aadhaar, payslips, signed offer "
					"letter). Copied from the Employee Onboarding Application on conversion; "
					"HR can add more here."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Employee.employee_documents table (Documents section)")
