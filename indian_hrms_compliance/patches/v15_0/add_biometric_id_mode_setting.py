"""Seed HR Settings.biometric_id_mode to 'Manual' on existing sites.

The control itself is a standard field on the HR Settings doctype
(hr_settings.json), so it materialises via doctype sync on migrate. This patch
only seeds the stored value so HR Settings shows an explicit 'Manual' (the
no-surprise default — no auto-generation until HR opts in) instead of an empty
Select. Idempotent: only writes when the value is currently empty.
"""

import frappe


def execute():
	frappe.reload_doctype("HR Settings")
	if not frappe.db.get_single_value("HR Settings", "biometric_id_mode"):
		frappe.db.set_single_value("HR Settings", "biometric_id_mode", "Manual")
