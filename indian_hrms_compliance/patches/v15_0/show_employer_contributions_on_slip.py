# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Show employer PF/ESI on the salary slip for existing installs.

The new Salary Component flag ``show_on_salary_slip`` makes an employer-side
statistical component appear on the slip as an information row (excluded from
gross / net / accrual). Fresh installs get it via the seeded component data;
existing installs predate the field, so back-fill it once on the two employer
contributions the employee should see. Gratuity is deliberately left off — it
stays a hidden provision. Runs once; a later manual toggle is never overwritten.
"""

import frappe


def execute():
	for component in ("Employer Provident Fund", "Employer ESI"):
		if frappe.db.exists("Salary Component", component):
			frappe.db.set_value(
				"Salary Component", component, "show_on_salary_slip", 1, update_modified=False
			)
			print(f"  Salary Component: show_on_salary_slip = 1 on {component}")
