# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Segregate the monthly Statutory Bonus out of Gross Wages for existing installs.

The monthly Statutory Bonus is paid in take-home but, under the Payment of Bonus
Act, is an advance against annual bonus — not "wages". A new Salary Component
flag ``exclude_from_gross_wages`` keeps such a paid head out of the Gross Wages
figure on payslips and statutory registers (Net Pay / take-home and tax are
unaffected).

This patch:
  1. Ensures the Salary Component flag exists (it is normally created in
     after_migrate, which runs AFTER patches — so create it here too, up front).
  2. Flags the seeded Statutory Bonus component. Runs once; a later manual
     toggle is never overwritten.
  3. Back-fills gross_wages / bonus_advance on every existing Salary Slip, so
     historical slips and reprinted registers show the segregated figures too
     (Net Pay is untouched).

Defensive throughout: no-ops on the parts whose fields/records are absent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt


def execute():
	# 1. Make sure the flag field is present before we use it (after_migrate,
	#    which normally creates it, has not run yet at patch time).
	if not frappe.get_meta("Salary Component").has_field("exclude_from_gross_wages"):
		create_custom_fields(
			{
				"Salary Component": [
					{
						"fieldname": "exclude_from_gross_wages",
						"fieldtype": "Check",
						"label": "Exclude from Gross Wages (paid as advance / bonus)",
						"insert_after": "do_not_include_in_total",
					}
				]
			},
			ignore_validate=True,
		)

	# 2. Flag the seeded Statutory Bonus (advance against annual bonus).
	if frappe.db.exists("Salary Component", "Statutory Bonus"):
		frappe.db.set_value(
			"Salary Component", "Statutory Bonus", "exclude_from_gross_wages", 1, update_modified=False
		)
		print("  Salary Component: exclude_from_gross_wages = 1 on Statutory Bonus")

	# 3. Back-fill the derived split on existing slips (the display fields default
	#    to NULL on already-submitted slips, which would otherwise render as 0).
	if not frappe.get_meta("Salary Slip").has_field("gross_wages"):
		return

	# Default for everyone: Gross Wages == Gross Pay, no bonus advance.
	frappe.db.sql("UPDATE `tabSalary Slip` SET gross_wages = gross_pay, bonus_advance = 0")

	excluded = frappe.get_all("Salary Component", filters={"exclude_from_gross_wages": 1}, pluck="name")
	if not excluded:
		return

	# Slips that actually carry a flagged (advance-bonus) earning row.
	rows = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Slip",
			"parentfield": "earnings",
			"salary_component": ["in", excluded],
			"do_not_include_in_total": 0,
		},
		fields=["parent", "amount"],
	)
	bonus_by_slip = {}
	for r in rows:
		bonus_by_slip[r.parent] = bonus_by_slip.get(r.parent, 0.0) + flt(r.amount)

	for slip, bonus in bonus_by_slip.items():
		gross_pay = flt(frappe.db.get_value("Salary Slip", slip, "gross_pay"))
		frappe.db.set_value(
			"Salary Slip",
			slip,
			{"bonus_advance": bonus, "gross_wages": gross_pay - bonus},
			update_modified=False,
		)
	print(f"  Salary Slip: back-filled gross_wages/bonus_advance on {len(bonus_by_slip)} slip(s)")
