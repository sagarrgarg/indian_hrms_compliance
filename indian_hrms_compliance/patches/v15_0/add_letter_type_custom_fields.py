# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Add letter_type to Appointment Letter and Appointment Letter Template
	so we can discriminate Confirmation / Probation Extension / Release letters
	from regular Appointment letters."""
	create_custom_fields(
		{
			"Appointment Letter": [
				{
					"fieldname": "letter_type",
					"fieldtype": "Select",
					"label": "Letter Type",
					"options": "Appointment\nConfirmation\nProbation Extension\nRelease\nOther",
					"default": "Appointment",
					"insert_after": "appointment_date",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "probation_review",
					"fieldtype": "Link",
					"label": "Probation Review",
					"options": "Probation Review",
					"insert_after": "letter_type",
					"depends_on": "eval:in_list(['Confirmation','Probation Extension','Release'], doc.letter_type)",
					"read_only": 1,
				},
			],
			"Appointment Letter Template": [
				{
					"fieldname": "letter_type",
					"fieldtype": "Select",
					"label": "Letter Type",
					"options": "Appointment\nConfirmation\nProbation Extension\nRelease\nOther",
					"default": "Appointment",
					"insert_after": "template_name",
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
			],
		},
		ignore_validate=True,
	)
