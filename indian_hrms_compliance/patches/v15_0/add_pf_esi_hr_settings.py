# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add Phase 6B-1 PF ECR + ESI scheduler fields to HR Settings.

We DELIBERATELY add via Custom Fields (not via editing
hr/doctype/hr_settings/hr_settings.json) because Phase 6A just touched
that JSON for the Statutory tab — adding more fields directly would
create merge friction with the 6A commit. Custom Fields layered on top
work the same way at runtime.

Fields added (all in the existing Statutory tab):
  pf_ecr_filing_window_days       Int   default 15
  pf_ecr_exclude_employees_with_no_uan  Check default 1
  pf_edli_per_member_cap          Int   default 75
  esi_filing_window_days          Int   default 15

Defaults are seeded by a separate patch (seed_pf_esi_hr_settings_defaults)
because HR Settings is a Single and JSON 'default:' only fires on
first row insert.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	# insert_after points at fields known to exist on HR Settings (from 6A).
	# pf_admin_charges_min was seeded in seed_statutory_defaults so it
	# should be present on the HR Settings doctype meta from the 6A patches.
	return {
		"HR Settings": [
			{
				"fieldname": "pf_ecr_filing_window_days",
				"fieldtype": "Int",
				"label": "PF ECR Filing Window (Days)",
				"insert_after": "pf_admin_charges_min",
				"default": "15",
				"description": (
					"Number of days after wage month end by which PF ECR must be filed. "
					"Daily reminders fire from wage_month_end + 1 to wage_month_end + window."
				),
			},
			{
				"fieldname": "pf_ecr_exclude_employees_with_no_uan",
				"fieldtype": "Check",
				"label": "PF ECR: Skip Employees Missing UAN",
				"insert_after": "pf_ecr_filing_window_days",
				"default": "1",
				"description": (
					"When ON, employees without a UAN are skipped (logged in Exceptions). "
					"When OFF, ECR generation throws — useful in strict environments where "
					"missing UAN must be fixed before filing."
				),
			},
			{
				"fieldname": "pf_edli_per_member_cap",
				"fieldtype": "Int",
				"label": "PF EDLI Per-Member Cap (₹)",
				"insert_after": "pf_ecr_exclude_employees_with_no_uan",
				"default": "75",
				"description": (
					"Per-member EDLI contribution cap. Computed as EDLI wage cap × 0.50% "
					"(15,000 × 0.005 = 75). Set higher only if Notification 2024-XX raises it."
				),
			},
			{
				"fieldname": "esi_filing_window_days",
				"fieldtype": "Int",
				"label": "ESI Filing Window (Days)",
				"insert_after": "esi_employee_daily_wage_waiver",
				"default": "15",
				"description": (
					"Number of days after wage month end by which ESI contribution must be filed."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Phase 6B-1 PF ECR + ESI Custom Fields to HR Settings")
