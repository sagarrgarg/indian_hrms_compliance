# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed Compliance Calendar defaults — Phase 6C.

Two things:

1. HR Settings defaults (same pattern as 6B-1 / 6B-2): the JSON
   `default:` field only fires on row insert; HR Settings is a Single,
   so we backfill via set_single_value here without clobbering values
   an HR Manager has tuned.

2. For each existing Company in the system, seed the 6 federal-default
   Compliance Return Definitions (calls
   seed_compliance_return_definitions from the overrides module).
   Idempotent: skips Companies that already have CRDs.
"""

import frappe

from indian_hrms_compliance.overrides.compliance_calendar import (
	seed_compliance_return_definitions,
)


DEFAULTS = {
	"compliance_calendar_upcoming_days": 7,
	"compliance_calendar_escalation_days_after_due": 3,
	"send_compliance_calendar_daily_digest": 1,
	"compliance_calendar_digest_recipients_role": "HR Manager",
	"auto_link_filings_to_calendar": 1,
}


def execute():
	for field, value in DEFAULTS.items():
		exists = frappe.db.exists("Singles", {"doctype": "HR Settings", "field": field})
		if not exists:
			frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(DEFAULTS)} Phase 6C Compliance Calendar defaults")

	# Seed default CRD rows for every existing Company.
	companies = frappe.get_all("Company", pluck="name")
	seeded_companies = 0
	for company in companies:
		try:
			seed_compliance_return_definitions(company_name=company)
			seeded_companies += 1
		except Exception:
			frappe.log_error(
				title=f"Seed CRD failed for {company}",
				message=frappe.get_traceback(),
			)
	print(f"  Seeded Compliance Return Definitions for {seeded_companies} Companies")
