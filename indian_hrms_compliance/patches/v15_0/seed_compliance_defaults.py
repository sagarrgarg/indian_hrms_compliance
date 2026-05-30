# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


COMPLIANCE_DEFAULTS = {
	# Grievance SLA (by Severity)
	"grievance_sla_days_critical": 7,
	"grievance_sla_days_high": 14,
	"grievance_sla_days_medium": 21,
	"grievance_sla_days_low": 30,
	# Grievance Digest
	"send_overdue_grievance_hr_digest": 1,
	"grievance_overdue_recipients_role": "HR Manager",
	# POSH
	"posh_statutory_sla_days": 90,
	"posh_ic_alert_role": "HR Manager",
	"posh_annual_report_alert_days": 30,
	# Disciplinary
	"default_disciplinary_inquiry_days": 30,
	"auto_trigger_resignation_on_termination_outcome": 1,
	"auto_trigger_warning_letter": 1,
	"auto_trigger_salary_withholding_on_suspension": 1,
}


def execute():
	"""Seed HR Settings 'Compliance' tab defaults — same rationale as the
	earlier seed patches: JSON `default:` only fires on row insert, but
	HR Settings is a Single."""
	for field, value in COMPLIANCE_DEFAULTS.items():
		frappe.db.set_single_value("HR Settings", field, value)
	print(f"  HR Settings: seeded {len(COMPLIANCE_DEFAULTS)} Compliance defaults")
