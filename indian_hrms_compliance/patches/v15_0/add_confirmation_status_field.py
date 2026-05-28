# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate, today


def execute():
	"""Add confirmation_status to Employee on existing sites + backfill from date fields."""
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "confirmation_status",
					"fieldtype": "Select",
					"label": "Confirmation Status",
					"options": "\nProbation\nConfirmed\nExtended\nReleased",
					"insert_after": "final_confirmation_date",
					"default": "",
				}
			]
		},
		ignore_validate=True,
	)

	today_d = getdate(today())

	# Backfill: final_confirmation_date set and in past → Confirmed
	frappe.db.sql(
		"""
		UPDATE `tabEmployee`
		SET confirmation_status = 'Confirmed'
		WHERE final_confirmation_date IS NOT NULL
		  AND final_confirmation_date <= %s
		  AND status = 'Active'
		  AND (confirmation_status IS NULL OR confirmation_status = '')
		""",
		today_d,
	)

	# Backfill: scheduled_confirmation_date in future and no final_confirmation_date → Probation
	frappe.db.sql(
		"""
		UPDATE `tabEmployee`
		SET confirmation_status = 'Probation'
		WHERE scheduled_confirmation_date IS NOT NULL
		  AND scheduled_confirmation_date > %s
		  AND final_confirmation_date IS NULL
		  AND status = 'Active'
		  AND (confirmation_status IS NULL OR confirmation_status = '')
		""",
		today_d,
	)
