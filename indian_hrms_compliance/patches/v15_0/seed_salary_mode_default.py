# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Backfill Employee.salary_mode for rows created before it became mandatory.

salary_mode is now defaulted to "Bank" and required (property setters applied via
setup.apply_property_setters on every migrate). Rows created earlier may hold a
blank/NULL salary_mode; left as-is the new mandatory rule would block the next
save of an otherwise-unchanged Employee. Backfill blanks to "Bank" — the
near-universal Indian salaried default — so existing masters stay editable and
compliant. Only blank/NULL values are touched; an explicit Cash/Cheque is never
overwritten.
"""

import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabEmployee`
		SET salary_mode = 'Bank'
		WHERE salary_mode IS NULL OR salary_mode = ''
		"""
	)
	affected = frappe.db._cursor.rowcount
	if affected:
		print(f"  Employee: backfilled salary_mode = 'Bank' on {affected} row(s)")
