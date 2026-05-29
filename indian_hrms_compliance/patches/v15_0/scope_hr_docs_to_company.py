# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


def execute():
	"""Per-Company scoping migration.

	Backfills `company` on existing KRA / HRMS Task / HRMS Policy rows that
	don't have one set (pre-this-change, company was optional or absent on
	some doctypes). Picks the first Company in the DB as the default.

	Also drops the HRMS Policy Company Filter child doctype which is no
	longer used (Policy.applicable_companies table was removed).
	"""
	# Pick a sensible default Company (first by name) for backfill
	default_company = frappe.db.get_value("Company", {}, "name", order_by="name asc")

	if default_company:
		# KRA — assign default to any KRA without a Company
		frappe.db.sql(
			"UPDATE `tabKRA` SET company = %s WHERE company IS NULL OR company = ''",
			default_company,
		)
		# HRMS Task — same
		frappe.db.sql(
			"UPDATE `tabHRMS Task` SET company = %s WHERE company IS NULL OR company = ''",
			default_company,
		)
		# HRMS Policy — same
		frappe.db.sql(
			"UPDATE `tabHRMS Policy` SET company = %s WHERE company IS NULL OR company = ''",
			default_company,
		)
		print(f"  Backfilled missing company values with '{default_company}' on KRA / HRMS Task / HRMS Policy")

	# Drop the obsolete HRMS Policy Company Filter child doctype
	if frappe.db.exists("DocType", "HRMS Policy Company Filter"):
		frappe.delete_doc("DocType", "HRMS Policy Company Filter", force=1, ignore_permissions=True)
		print("  Dropped HRMS Policy Company Filter doctype")

	# Drop the table too if it lingered (sql_ddl avoids ImplicitCommitError)
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabHRMS Policy Company Filter`")

	# Drop the old applicable_to_all column from tabHRMS Policy if it exists
	cols = frappe.db.get_table_columns("HRMS Policy")
	if "applicable_to_all" in cols:
		frappe.db.sql_ddl("ALTER TABLE `tabHRMS Policy` DROP COLUMN `applicable_to_all`")
		print("  Dropped HRMS Policy.applicable_to_all column")
