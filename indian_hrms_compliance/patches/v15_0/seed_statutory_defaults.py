# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed HR Settings 'Statutory' tab defaults — Phase 6A.

Same rationale as prior seed_*_defaults patches: HR Settings is a Single
that predates these new columns, so JSON default: only fires on row
insert. We backfill via set_single_value here.
"""

import frappe


STATUTORY_DEFAULTS = {
	# Wage Code
	"wage_code_enforcement": "HARD",
	"wage_code_basic_da_min_pct": 50.0,
	# PF
	"pf_wage_ceiling": 15000,
	"pf_employee_rate_pct": 12.0,
	"pf_employer_rate_pct": 12.0,
	"pf_eps_rate_pct": 8.33,
	"pf_edli_rate_pct": 0.50,
	"pf_admin_charges_pct": 0.50,
	"pf_admin_charges_min": 500,
	"pf_minimum_headcount_for_applicability": 20,
	# ESI
	"esi_wage_ceiling": 21000,
	"esi_wage_ceiling_disabled": 25000,
	"esi_employee_rate_pct": 0.75,
	"esi_employer_rate_pct": 3.25,
	"esi_employee_daily_wage_waiver": 176,
	# Minimum Wage
	"enforce_minimum_wage_validation": 1,
	# DPDP
	"dpdp_aadhaar_consent_required": 1,
	"dpdp_data_retention_years": 8,
	# default_pt_state is intentionally left unset — HR picks per their primary
	# operating state. The validator emits INFO when no state can be resolved
	# AND this is unset.
}


def execute():
	for field, value in STATUTORY_DEFAULTS.items():
		frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(STATUTORY_DEFAULTS)} Statutory defaults")
