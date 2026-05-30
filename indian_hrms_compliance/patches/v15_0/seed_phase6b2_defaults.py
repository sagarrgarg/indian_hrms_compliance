# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed Phase 6B-2 HR Settings defaults — TDS 24Q + State PT + LWF
scheduler windows. Same pattern as 6B-1 seed_pf_esi_hr_settings_defaults:
HR Settings is a Single, JSON-level default: only fires on row insert,
so we backfill via set_single_value here.

responsible_person_default_designation is intentionally left unset —
each Company picks a different person."""

import frappe


DEFAULTS = {
	"form_24q_filing_window_days": 30,
	"pt_filing_window_days": 10,
	"lwf_filing_window_days": 15,
}


def execute():
	for field, value in DEFAULTS.items():
		# Mirror 6B-1: only set if no explicit row in tabSingles, so we
		# don't override values an HR Manager has tuned.
		exists = frappe.db.exists(
			"Singles", {"doctype": "HR Settings", "field": field}
		)
		if not exists:
			frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(DEFAULTS)} Phase 6B-2 defaults (where unset)")
