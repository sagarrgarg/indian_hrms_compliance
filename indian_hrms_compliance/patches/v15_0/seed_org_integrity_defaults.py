"""Seed HR Settings defaults for the Step 2 Org Integrity Check.

A field `default:` does NOT back-fill an existing Single — HR Settings already
has its one row, and once the column exists a Check reads 0 / an Int reads 0
(NOT NULL), so a "blank-only" guard would never fire and the feature would sit
silently disabled. These fields are introduced BY this patch, so a one-shot
unconditional seed IS the correct default (matches seed_hr_settings_defaults);
the patch runs once, so an admin who later tunes a value is never clobbered.
Defensive: a not-yet-synced field is skipped, never aborting the migrate.
"""

import frappe

DEFAULTS = {
	"enable_org_integrity_check": 1,
	"org_integrity_stranded_sla_days": 3,
	"org_integrity_overdue_sla_days": 7,
	"org_integrity_escalation_role": "HR Manager",
}


def execute():
	meta = frappe.get_meta("HR Settings")
	for field, value in DEFAULTS.items():
		if not meta.has_field(field):
			continue
		frappe.db.set_single_value("HR Settings", field, value)
