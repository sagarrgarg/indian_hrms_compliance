# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Add is_internal_applicant + source_employee Custom Fields to Job Applicant
	on existing sites. Backfill: any existing Job Applicant whose email matches
	an Active Employee gets flagged."""
	create_custom_fields(
		{
			"Job Applicant": [
				{
					"fieldname": "is_internal_applicant",
					"fieldtype": "Check",
					"label": "Internal Applicant",
					"default": "0",
					"read_only": 1,
					"insert_after": "employee_referral",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "source_employee",
					"fieldtype": "Link",
					"label": "Source Employee",
					"options": "Employee",
					"read_only": 1,
					"insert_after": "is_internal_applicant",
				},
			]
		},
		ignore_validate=True,
	)

	applicants = frappe.db.sql(
		"""SELECT name, email_id FROM `tabJob Applicant`
		   WHERE email_id IS NOT NULL AND email_id != ''""",
		as_dict=True,
	)
	for app in applicants:
		match = (
			frappe.db.get_value(
				"Employee", {"company_email": app.email_id, "status": "Active"}, "name"
			)
			or frappe.db.get_value(
				"Employee", {"personal_email": app.email_id, "status": "Active"}, "name"
			)
			or frappe.db.get_value(
				"Employee", {"user_id": app.email_id, "status": "Active"}, "name"
			)
		)
		if match:
			frappe.db.set_value(
				"Job Applicant",
				app.name,
				{"is_internal_applicant": 1, "source_employee": match},
				update_modified=False,
			)
