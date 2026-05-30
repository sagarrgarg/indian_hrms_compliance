# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add minimum_wage_category Custom Field to Employee Grade and Designation.

Required by the Salary Structure Validator's
check_minimum_wage_compliance — it reads grade.minimum_wage_category first,
then designation.minimum_wage_category. Either can be set; the structure
just needs *one* of them to participate in min-wage validation.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CATEGORIES = "\nUnskilled\nSemi-Skilled\nSkilled\nHighly Skilled\nClerical\nSupervisory"


def get_fields():
	return {
		"Employee Grade": [
			{
				"fieldname": "minimum_wage_category",
				"fieldtype": "Select",
				"label": "Minimum Wage Category",
				"options": CATEGORIES,
				"insert_after": "default_base_pay",
				"description": (
					"Statutory category for Minimum Wage Notification lookup. "
					"Falls back to Designation.minimum_wage_category if not set."
				),
			},
		],
		"Designation": [
			{
				"fieldname": "minimum_wage_category",
				"fieldtype": "Select",
				"label": "Minimum Wage Category",
				"options": CATEGORIES,
				"insert_after": "description",
				"description": (
					"Statutory category for Minimum Wage Notification lookup. "
					"Used by the Salary Structure Validator when Employee.grade "
					"has no category."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added minimum_wage_category Custom Field to Employee Grade + Designation")
