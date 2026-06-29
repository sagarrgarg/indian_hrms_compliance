# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed HR Settings.pan_mandatory_annual_income for existing sites.

The Salary Structure Validator now treats a missing Employee PAN as a
non-blocking WARN below this annual income (no TDS / Form 16 arises) and a
HARD block at or above it. The JSON default only fires on Single insert, so
existing HR Settings rows need a backfill. Defensive: only set when unset so
an HR-chosen value is never clobbered.
"""

import frappe


def execute():
	if frappe.db.get_single_value("HR Settings", "pan_mandatory_annual_income") in (None, "", 0):
		frappe.db.set_single_value("HR Settings", "pan_mandatory_annual_income", 700000)
		print("  HR Settings: seeded pan_mandatory_annual_income = 700000")
