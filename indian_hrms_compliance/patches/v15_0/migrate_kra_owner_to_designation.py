# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


def execute():
	"""Migration: KRA accountability moves from User-based (kra_owner) to
	Designation-based (owner_designation).

	For any existing KRA with kra_owner set, attempt to find the linked
	User's Active Employee and copy that Employee's Designation into
	owner_designation. Then drop the kra_owner column."""

	# Check if kra_owner column still exists in tabKRA (it might not if
	# this is a fresh install or if the column was already dropped).
	cols = frappe.db.get_table_columns("KRA")
	if "kra_owner" not in cols:
		return  # nothing to migrate

	# Migrate values where possible
	rows = frappe.db.sql(
		"SELECT name, kra_owner FROM `tabKRA` WHERE kra_owner IS NOT NULL AND kra_owner != ''",
		as_dict=True,
	)
	migrated = 0
	for r in rows:
		# Find the Active Employee for this user, pick their Designation
		designation = frappe.db.get_value(
			"Employee",
			{"user_id": r.kra_owner, "status": "Active"},
			"designation",
		)
		if designation:
			frappe.db.set_value("KRA", r.name, "owner_designation", designation, update_modified=False)
			migrated += 1

	# Drop the old column (raw SQL — Frappe schema_check would have done this
	# eventually, but explicit drop here keeps things clean).
	frappe.db.sql("ALTER TABLE `tabKRA` DROP COLUMN `kra_owner`")
	print(f"  KRA: migrated {migrated}/{len(rows)} kra_owner values to owner_designation; column dropped")
