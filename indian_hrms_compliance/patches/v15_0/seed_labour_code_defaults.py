# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6E — seed defaults for HR Settings Labour Code fields.

JSON `default:` only fires on row insert, but HR Settings is a Single
so its row is pre-existing. We must explicitly set values here.
"""

import frappe


LABOUR_CODE_DEFAULTS = {
	"standing_orders_threshold_workers": 300,
	"works_committee_threshold_workers": 100,
	"grc_threshold_workers": 20,
	"safety_committee_threshold_workers": 250,
	"posh_ic_threshold_workers": 10,
	"enable_uan_aadhaar_validation": 1,
	"enable_monthly_labour_code_compliance_check": 1,
}


def execute():
	for field, value in LABOUR_CODE_DEFAULTS.items():
		frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(LABOUR_CODE_DEFAULTS)} Labour Code defaults")
