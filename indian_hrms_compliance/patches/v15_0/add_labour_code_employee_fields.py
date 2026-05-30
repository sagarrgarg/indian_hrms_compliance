# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6E — UAN seeding automation fields on Employee (SS Code §142).

Adds:
  uan_aadhaar_linked       Check    default 0
  uan_linking_date         Date
  uan_seeding_status       Select   default 'Not Seeded'
  uan_seeding_attempts     Int      default 0

All anchored after uan_number (which exists from Phase 1 statutory IDs).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	# Anchor: uan_number exists; if not present we still create the section
	# break first and chain after that.
	uan_anchor = "uan_number" if _has_field("Employee", "uan_number") else None
	first_after = uan_anchor or "department"
	return {
		"Employee": [
			{
				"fieldname": "labour_code_uan_section_break",
				"fieldtype": "Section Break",
				"label": "UAN Aadhaar Seeding (SS Code §142)",
				"insert_after": first_after,
				"collapsible": 1,
			},
			{
				"fieldname": "uan_aadhaar_linked",
				"fieldtype": "Check",
				"label": "UAN Aadhaar Linked",
				"insert_after": "labour_code_uan_section_break",
				"default": "0",
				"description": "Per SS Code §142, UAN must be linked with Aadhaar.",
			},
			{
				"fieldname": "uan_linking_date",
				"fieldtype": "Date",
				"label": "UAN Linking Date",
				"insert_after": "uan_aadhaar_linked",
				"depends_on": "eval:doc.uan_aadhaar_linked",
			},
			{
				"fieldname": "uan_seeding_col_break",
				"fieldtype": "Column Break",
				"insert_after": "uan_linking_date",
			},
			{
				"fieldname": "uan_seeding_status",
				"fieldtype": "Select",
				"label": "UAN Seeding Status",
				"options": "Not Seeded\nPending\nSeeded\nMismatched",
				"insert_after": "uan_seeding_col_break",
				"default": "Not Seeded",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "uan_seeding_attempts",
				"fieldtype": "Int",
				"label": "UAN Seeding Attempts",
				"insert_after": "uan_seeding_status",
				"default": "0",
				"non_negative": 1,
			},
		],
	}


def _has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Phase 6E UAN seeding Custom Fields to Employee")
