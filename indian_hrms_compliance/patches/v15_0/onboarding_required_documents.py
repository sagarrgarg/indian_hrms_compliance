# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Onboarding intake: required-document enforcement support.

  (1) Backfills `is_fresher = 0` on existing Employee Onboarding Application
      rows (the schema sync adds the column NULL-default).

  (2) Migrates the legacy Employee Onboarding Document type label
      'Aadhaar (masked)' → 'Aadhaar Card' so existing rows match the new
      option set + the required-document validator.

The required-document validation itself is enforced in the controller
(_validate_required_documents); no data migration is needed for that.
"""

import frappe


def execute():
	if frappe.db.table_exists("Employee Onboarding Application") and "is_fresher" in frappe.db.get_table_columns(
		"Employee Onboarding Application"
	):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Application`
			   SET is_fresher = 0
			 WHERE is_fresher IS NULL"""
		)

	# Relabel legacy Aadhaar document rows to the new option value.
	if frappe.db.table_exists("Employee Onboarding Document"):
		frappe.db.sql(
			"""UPDATE `tabEmployee Onboarding Document`
			   SET document_type = 'Aadhaar Card'
			 WHERE document_type = 'Aadhaar (masked)'"""
		)

	frappe.db.commit()
	print("  Onboarding: is_fresher backfilled + Aadhaar document type relabelled")
