# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add Phase 6B-2 (TDS 24Q + State PT + LWF) scheduler-window fields to
HR Settings.

Same rationale as 6B-1 add_pf_esi_hr_settings: add via Custom Fields on
top of the existing Statutory tab to avoid merge friction with prior
patches that touch hr_settings.json.

Fields added:
  form_24q_filing_window_days              Int   default 30
  pt_filing_window_days                    Int   default 10
  lwf_filing_window_days                   Int   default 15
  responsible_person_default_designation   Link  Designation

Defaults are seeded by seed_phase6b2_defaults patch.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	# Anchor each field after a 6B-1 field that is guaranteed to exist
	# (esi_filing_window_days was added in add_pf_esi_hr_settings #2026-05-31).
	return {
		"HR Settings": [
			{
				"fieldname": "form_24q_filing_window_days",
				"fieldtype": "Int",
				"label": "Form 24Q Filing Window (Days)",
				"insert_after": "esi_filing_window_days",
				"default": "30",
				"description": (
					"Days BEFORE the statutory Form 24Q due date by which to start nagging "
					"HR Managers. Reminders continue for this many days AFTER the due date "
					"too. Q1 due 31 Jul, Q2 due 31 Oct, Q3 due 31 Jan, Q4 due 31 May."
				),
			},
			{
				"fieldname": "pt_filing_window_days",
				"fieldtype": "Int",
				"label": "PT Filing Window (Days)",
				"insert_after": "form_24q_filing_window_days",
				"default": "10",
				"description": (
					"Days after the PT filing period closes (monthly / half-yearly per state) "
					"within which to nag for an unfiled PT Return."
				),
			},
			{
				"fieldname": "lwf_filing_window_days",
				"fieldtype": "Int",
				"label": "LWF Filing Window (Days)",
				"insert_after": "pt_filing_window_days",
				"default": "15",
				"description": (
					"Days after the LWF filing period closes within which to nag for an "
					"unfiled LWF Return."
				),
			},
			{
				"fieldname": "responsible_person_default_designation",
				"fieldtype": "Link",
				"options": "Designation",
				"label": "Default Responsible-Person Designation (Form 24Q)",
				"insert_after": "lwf_filing_window_days",
				"description": (
					"Pre-fills the 'Person Responsible for Deduction' designation on new "
					"TDS Return Form 24Q docs (e.g., 'Director - Finance' or 'CFO'). "
					"HR can override per return."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Phase 6B-2 Custom Fields to HR Settings")
