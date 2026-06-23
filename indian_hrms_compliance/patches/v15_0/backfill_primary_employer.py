# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Backfill the `is_primary_employer` flag for unambiguous existing employees.

Going forward, auto_set_primary_employer ticks "Primary Employer for TDS /
Form 12B" on a person's first Active employment. Existing rows predate that hook,
so this patch ticks every Active Employee who is provably a person's *only* live
job (single Active record per PAN and per user_id, and a PAN is present). Anyone
with concurrent Active employments is the Form 12B / multi-employer case and is
left for HR to resolve by hand — the backfill never guesses which job is primary.

Fully defensive: a fresh site won't have the `is_primary_employer` column yet
(it's created on after_migrate, which runs after this patch) but also has no
legacy employees to fix, so we simply skip. Any failure is logged, never raised,
so migrate can't be wedged by it.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Employee"):
		return
	if "is_primary_employer" not in frappe.db.get_table_columns("Employee"):
		# Column is added on after_migrate (setup.get_custom_fields). A site
		# without it yet is a fresh install with nothing to backfill.
		return

	try:
		from indian_hrms_compliance.overrides.employee_master import _backfill_primary_employer

		result = _backfill_primary_employer(dry_run=False)
	except Exception:
		frappe.log_error(
			title="Primary Employer backfill failed",
			message=frappe.get_traceback(),
		)
		return

	print(
		"  Primary Employer backfill: ticked {ticked} sole-employment record(s); "
		"left {multi} multi-employment for HR; {conflicts}".format(
			ticked=result.get("eligible_count", 0),
			multi=result.get("skipped_multi_count", 0),
			conflicts=(
				"INTEGRITY CONFLICTS found — run "
				"indian_hrms_compliance.overrides.employee_master.backfill_primary_employer "
				"to review"
				if result.get("has_conflicts")
				else "no integrity conflicts"
			),
		)
	)
