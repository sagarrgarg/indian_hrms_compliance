# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


def execute():
	"""Backfill the new KRA.is_global field on existing rows.

	Frappe column defaults apply to new inserts only — pre-existing KRAs
	get NULL when the column is added. We want all existing KRAs to behave
	the same as before (org-wide / appear in every picker), so set them
	to is_global=1.
	"""
	frappe.db.sql(
		"UPDATE `tabKRA` SET is_global = 1 WHERE is_global IS NULL OR is_global = 0"
	)
