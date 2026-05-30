# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed Phase 6B-1 PF ECR + ESI Custom Field defaults on HR Settings.

Single doctypes need explicit set_single_value because JSON 'default:'
only fires on row insert (and the row already exists). Mirrors the
6A seed_statutory_defaults pattern.
"""

import frappe


DEFAULTS = {
	"pf_ecr_filing_window_days": 15,
	"pf_ecr_exclude_employees_with_no_uan": 1,
	"pf_edli_per_member_cap": 75,
	"esi_filing_window_days": 15,
}


def execute():
	for field, value in DEFAULTS.items():
		# Only set if the field has no explicit row in tabSingles. Note:
		# get_single_value returns 0 for missing Int Single fields, so we
		# must check tabSingles directly — using "in (None, '')" would
		# falsely treat an explicit HR-set 0 as missing.
		exists = frappe.db.exists(
			"Singles", {"doctype": "HR Settings", "field": field}
		)
		if not exists:
			frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(DEFAULTS)} Phase 6B-1 PF/ESI defaults (where unset)")
