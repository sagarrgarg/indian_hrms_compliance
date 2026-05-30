# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


EXIT_SETTLEMENT_DEFAULTS = {
	"notice_recovery_basis": "Basic Only",
	"notice_recovery_days_in_month": 30,
	"allow_negotiated_notice_waiver": 1,
	"auto_create_gratuity_on_fnf": 1,
	"auto_create_leave_encashment_on_fnf": 1,
	"compute_tds_on_fnf": 1,
	"auto_generate_exit_letters_on_fnf_submit": 0,
	"form_16_issuance_deadline_alert_days": 15,
	# Letter Head + Signatory Designation left empty by default — HR fills.
}


def execute():
	"""Seed HR Settings 'Exit & Settlement' tab defaults.

	Same rationale as seed_hr_settings_defaults: JSON defaults only fire
	on row insert, but HR Settings is a Single that predates these fields,
	so the columns came in NULL / 0."""
	for field, value in EXIT_SETTLEMENT_DEFAULTS.items():
		frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(EXIT_SETTLEMENT_DEFAULTS)} Exit & Settlement defaults")
