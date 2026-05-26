# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Add UAN / ESIC IP / Aadhaar Last 4 / NPS PRAN / Primary Employer flag
	to Employee on existing sites. Mirrors regional/india/setup.py for
	fresh installs.
	"""
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "uan_number",
					"label": "UAN",
					"fieldtype": "Data",
					"length": 12,
					"insert_after": "provident_fund_account",
					"print_hide": 1,
					"translatable": 0,
					"description": "12-digit EPFO Universal Account Number",
				},
				{
					"fieldname": "esic_ip_number",
					"label": "ESIC IP Number",
					"fieldtype": "Data",
					"insert_after": "uan_number",
					"print_hide": 1,
					"translatable": 0,
				},
				{
					"fieldname": "aadhaar_last_4",
					"label": "Aadhaar Last 4 Digits",
					"fieldtype": "Data",
					"length": 4,
					"insert_after": "esic_ip_number",
					"print_hide": 1,
					"translatable": 0,
					"description": "Store only the last 4 digits per DPDP Act / Aadhaar Act guidance.",
				},
				{
					"fieldname": "nps_pran",
					"label": "NPS PRAN",
					"fieldtype": "Data",
					"insert_after": "aadhaar_last_4",
					"translatable": 0,
				},
				{
					"fieldname": "is_primary_employer",
					"label": "Primary Employer for TDS / Form 12B",
					"fieldtype": "Check",
					"insert_after": "nps_pran",
					"default": "0",
					"description": "Only one Active Employee per User may be the Primary Employer.",
				},
			]
		},
		ignore_validate=True,
	)
