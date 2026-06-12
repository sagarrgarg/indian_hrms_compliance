# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""POSH: split the accused field.

`accused` was a Link(Employee). Restricted employees (the complainants) cannot
see the Employee directory, which makes a Link autocomplete unusable AND
double-leaks the directory through the autocomplete.

We now split it:
  - accused  (Data, free text — what the complainant typed)
  - accused_employee_link (Link Employee, IC-set during inquiry)

This patch:
  (1) Lets the schema sync (run before patches) re-shape the `accused`
      column from a Link to Data — both are stored as varchar(140), so no
      column type change is actually needed; the doctype JSON declares the
      new type.
  (2) Backfills `accused_employee_link` from the OLD value of `accused`
      where that old value still resolves to a real Employee. This keeps
      existing access grants intact: anyone who could read a complaint
      because they were the accused continues to.
  (3) Backfills `accused_company` (now Data) from the linked Employee's
      company so historical rows still show context.
"""

import frappe


def execute():
	if not frappe.db.table_exists("POSH Complaint"):
		return

	cols = frappe.db.get_table_columns("POSH Complaint")
	if "accused_employee_link" not in cols or "accused" not in cols:
		return

	rows = frappe.db.sql(
		"""
		SELECT name, accused, accused_employee_link, accused_company
		FROM `tabPOSH Complaint`
		WHERE accused IS NOT NULL AND accused != ''
		""",
		as_dict=True,
	)

	patched = 0
	for r in rows:
		updates = {}
		# Backfill the IC-resolved link only where the old value names an Employee.
		if not r.accused_employee_link and frappe.db.exists("Employee", r.accused):
			updates["accused_employee_link"] = r.accused
			emp_company = frappe.db.get_value("Employee", r.accused, "company")
			if emp_company and not r.accused_company:
				updates["accused_company"] = emp_company
		if updates:
			frappe.db.set_value("POSH Complaint", r.name, updates, update_modified=False)
			patched += 1

	frappe.db.commit()
	print(f"  POSH: backfilled accused_employee_link on {patched} historical complaint(s)")
