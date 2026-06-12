# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add `aadhaar_number` (full 12-digit) to Employee as a Custom Field.

Aadhaar Onboarding shift (2026-06-04): all forms now capture the full
12-digit Aadhaar with Verhoeff checksum, instead of the previous last-4-only
design. The legacy `aadhaar_last_4` Custom Field stays — it is now an
auto-derived view of `aadhaar_number[-4:]`, kept for:
  - DPDP `data_categories` strings that already reference it
  - the UAN-Aadhaar linkage validator (overrides/labour_code_uan.py)
  - existing report/audit columns

Why Custom Field, not a doctype JSON change: Employee is owned by ERPNext;
we layer fields on via Custom Field to stay merge-clean against upstream.

We CANNOT backfill `aadhaar_number` from `aadhaar_last_4` — the full number
isn't recoverable. Existing rows simply keep their last-4 and re-collect the
full Aadhaar at the next consent-refresh cycle (or on the employee's next
self-service profile update). No data loss.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"Employee": [
			{
				"fieldname": "aadhaar_number",
				"label": "Aadhaar Number",
				"fieldtype": "Data",
				"length": 12,
				"insert_after": "esic_ip_number",
				"print_hide": 1,
				"no_copy": 1,
				"translatable": 0,
				"description": (
					"Full 12-digit Aadhaar — Verhoeff-checksum validated. "
					"Display masked elsewhere; last-4 auto-derived for audit views."
				),
			},
			# aadhaar_last_4 already exists as a Custom Field from an earlier
			# patch; we just flip it to read_only here since it's now a derived
			# view of aadhaar_number. Done idempotently below.
		]
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)

	# Make the existing aadhaar_last_4 Custom Field read-only + relabel it so
	# users understand it's a derived view, not an independent input.
	cf = frappe.db.get_value(
		"Custom Field",
		{"dt": "Employee", "fieldname": "aadhaar_last_4"},
		"name",
	)
	if cf:
		frappe.db.set_value(
			"Custom Field",
			cf,
			{
				"read_only": 1,
				"label": "Aadhaar (last 4)",
				"description": (
					"Auto-derived from the Aadhaar number above — retained for "
					"UAN-Aadhaar linkage and DPDP audit reports."
				),
			},
		)

	# Backfill last_4 from aadhaar_number on rows where someone already set
	# both columns manually (shouldn't be many, but cheap to do).
	if (
		frappe.db.table_exists("Employee")
		and "aadhaar_number" in frappe.db.get_table_columns("Employee")
		and "aadhaar_last_4" in frappe.db.get_table_columns("Employee")
	):
		frappe.db.sql(
			"""UPDATE `tabEmployee`
			   SET aadhaar_last_4 = RIGHT(aadhaar_number, 4)
			 WHERE aadhaar_number IS NOT NULL
			   AND CHAR_LENGTH(aadhaar_number) = 12"""
		)

	frappe.db.commit()
	print("  Aadhaar: added Employee.aadhaar_number Custom Field; aadhaar_last_4 flipped to derived/read-only.")
