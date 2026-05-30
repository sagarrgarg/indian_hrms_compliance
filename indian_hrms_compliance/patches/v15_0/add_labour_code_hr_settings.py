# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6E — Labour Code threshold + toggle Custom Fields on HR Settings.

Same Custom-Field-on-top-of-Statutory-tab approach as 6B-1 / 6B-2 / 6C
to avoid merge friction with parallel patches.

Fields added:
  standing_orders_threshold_workers              Int   default 300
  works_committee_threshold_workers              Int   default 100
  grc_threshold_workers                          Int   default 20
  safety_committee_threshold_workers             Int   default 250
  posh_ic_threshold_workers                      Int   default 10
  enable_uan_aadhaar_validation                  Check default 1
  enable_monthly_labour_code_compliance_check    Check default 1
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	# Anchor after the last 6C field that's guaranteed to exist.
	anchor = (
		"auto_link_filings_to_calendar"
		if _has_field("HR Settings", "auto_link_filings_to_calendar")
		else "compliance_calendar_digest_recipients_role"
	)
	return {
		"HR Settings": [
			{
				"fieldname": "labour_code_section_break",
				"fieldtype": "Section Break",
				"label": "Labour Code 2025",
				"insert_after": anchor,
				"collapsible": 1,
			},
			{
				"fieldname": "standing_orders_threshold_workers",
				"fieldtype": "Int",
				"label": "Standing Orders Threshold (Workers)",
				"insert_after": "labour_code_section_break",
				"default": "300",
				"description": "IR Code §28 — Standing Orders mandatory at this worker count.",
			},
			{
				"fieldname": "works_committee_threshold_workers",
				"fieldtype": "Int",
				"label": "Works Committee Threshold (Workers)",
				"insert_after": "standing_orders_threshold_workers",
				"default": "100",
				"description": "IR Code §3 — Works Committee mandatory at this worker count.",
			},
			{
				"fieldname": "grc_threshold_workers",
				"fieldtype": "Int",
				"label": "GRC Threshold (Workers)",
				"insert_after": "works_committee_threshold_workers",
				"default": "20",
				"description": "IR Code §4 — Grievance Redressal Committee mandatory at this worker count.",
			},
			{
				"fieldname": "labour_code_col_break",
				"fieldtype": "Column Break",
				"insert_after": "grc_threshold_workers",
			},
			{
				"fieldname": "safety_committee_threshold_workers",
				"fieldtype": "Int",
				"label": "Safety Committee Threshold (Workers)",
				"insert_after": "labour_code_col_break",
				"default": "250",
				"description": "OSH&WC §96 — Safety Committee mandatory at this worker count.",
			},
			{
				"fieldname": "posh_ic_threshold_workers",
				"fieldtype": "Int",
				"label": "POSH IC Threshold (Workers)",
				"insert_after": "safety_committee_threshold_workers",
				"default": "10",
				"description": "POSH Act §4 — Internal Committee mandatory at this worker count.",
			},
			{
				"fieldname": "enable_uan_aadhaar_validation",
				"fieldtype": "Check",
				"label": "Enable UAN Aadhaar Validation",
				"insert_after": "posh_ic_threshold_workers",
				"default": "1",
				"description": "Warn on Employee.validate when UAN is set but not seeded with Aadhaar (SS Code §142).",
			},
			{
				"fieldname": "enable_monthly_labour_code_compliance_check",
				"fieldtype": "Check",
				"label": "Enable Monthly Labour Code Compliance Check",
				"insert_after": "enable_uan_aadhaar_validation",
				"default": "1",
				"description": "Monthly scheduler — compare worker count vs thresholds; notify HR Manager on gaps.",
			},
		],
	}


def _has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Phase 6E Labour Code Custom Fields to HR Settings")
