# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6D — extend HR Settings with DPDP runtime knobs.

Phase 6A already shipped two DPDP fields directly in hr_settings.json:
  dpdp_aadhaar_consent_required (Check, default 1)
  dpdp_data_retention_years     (Int, default 8)

We DO NOT touch hr_settings.json — we layer Custom Fields on top so that
this patch doesn't merge-collide with the parallel 6E agent. New fields
appear in the existing DPDP section after dpdp_data_retention_years.

Defaults are seeded in patches.v15_0.dpdp_seed_defaults (single docs
ignore JSON 'default:' values after initial insert).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"HR Settings": [
			{
				"fieldname": "dpdp_enable_access_logging",
				"fieldtype": "Check",
				"label": "DPDP: Enable Access Logging",
				"insert_after": "dpdp_data_retention_years",
				"default": "1",
				"description": (
					"Master kill-switch for the DPDP Access Logger. When OFF, "
					"sensitive-field-access logging is bypassed entirely. "
					"Useful for disabling during bulk operations or load tests."
				),
			},
			{
				"fieldname": "dpdp_access_log_throttle_seconds",
				"fieldtype": "Int",
				"label": "DPDP: Access Log Throttle (Seconds)",
				"insert_after": "dpdp_enable_access_logging",
				"default": "3600",
				"description": (
					"Minimum seconds between identical access log entries for "
					"(user × doctype × record × field). Prevents log floods on "
					"repeated form refreshes. Default 3600 (1 hour)."
				),
			},
			{
				"fieldname": "dpdp_purge_max_per_run",
				"fieldtype": "Int",
				"label": "DPDP: Purge Max Records Per Run",
				"insert_after": "dpdp_access_log_throttle_seconds",
				"default": "50",
				"description": (
					"Hard cap on records the weekly retention purge scheduler "
					"processes in one run. Safety bound against runaway purges "
					"from a misconfigured Data Retention Rule. Default 50."
				),
			},
			{
				"fieldname": "dpdp_breach_notification_recipients_role",
				"fieldtype": "Link",
				"options": "Role",
				"label": "DPDP: Breach Notification Role",
				"insert_after": "dpdp_purge_max_per_run",
				"default": "HR Manager",
				"description": (
					"Role whose holders receive PWA breach-notification alerts. "
					"The DPB (Data Protection Board) notification is separate."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Phase 6D: Added 4 DPDP Custom Fields to HR Settings")
