# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Flag Gratuity as excluded from CTC for existing installs.

The new Salary Component flag ``exclude_from_ctc`` marks a long-term / exit
provision so the CTC preview keeps it out of the CTC figure and shows it as a
separate provision layer. Fresh installs get it via the seeded component data;
existing installs predate the field, so back-fill it once on Gratuity — the
one long-term provision seeded by the app. Current-period employer
contributions (Employer PF / ESI) deliberately stay off, so they count in CTC.
Runs once; a later manual toggle is never overwritten.
"""

import frappe


def execute():
	if frappe.db.exists("Salary Component", "Gratuity"):
		frappe.db.set_value(
			"Salary Component", "Gratuity", "exclude_from_ctc", 1, update_modified=False
		)
		print("  Salary Component: exclude_from_ctc = 1 on Gratuity")
