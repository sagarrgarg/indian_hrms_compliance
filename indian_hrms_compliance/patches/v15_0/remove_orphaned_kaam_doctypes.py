# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Ruthlessly drop the orphaned kaam / hrms_enhanced attendance-reconciliation
doctypes (and their modules) on sites where those apps are NOT installed.

They exist on such sites only because the DB was restored from a source that had
the apps (or the app was uninstalled without dropping its doctypes) — leaving a
DocType row + its table with no code behind it (e.g. 'Attendance Reconciliation
Log' on prod).

GUARD: if kaam or hrms_enhanced is actually installed on this site, do NOTHING —
their doctypes are legitimate there and must not be touched. Idempotent; a no-op
once cleaned or where there was never anything to clean.
"""

import frappe

ORPHAN_APPS = ("kaam", "hrms_enhanced")


def execute():
	installed = set(frappe.get_installed_apps())
	if installed & set(ORPHAN_APPS):
		return  # the owning app is installed here — hands off, these are real.

	modules = frappe.get_all("Module Def", filters={"app_name": ["in", list(ORPHAN_APPS)]}, pluck="name")
	if not modules:
		return

	# Delete parents before child tables so a Table-field link never snags.
	doctypes = frappe.get_all(
		"DocType", filters={"module": ["in", modules]}, fields=["name", "istable"]
	)
	removed = 0
	for dt in sorted(doctypes, key=lambda d: d.get("istable") or 0):
		if _force_delete_doctype(dt.name):
			removed += 1

	for mod in modules:
		if not frappe.get_all("DocType", filters={"module": mod}, limit=1):
			try:
				frappe.delete_doc("Module Def", mod, force=True, ignore_permissions=True)
			except Exception:
				frappe.log_error(title=f"Orphan module cleanup failed: {mod}", message=frappe.get_traceback())

	print(f"  Removed {removed} orphaned doctype(s) + module(s) {modules} (kaam/hrms_enhanced not installed).")


def _force_delete_doctype(name):
	"""Mark the standard doctype custom (to pass the standard-delete guard) then
	delete it — which also drops its table + Custom Fields / Property Setters."""
	try:
		frappe.db.set_value("DocType", name, "custom", 1, update_modified=False)
		frappe.clear_cache(doctype=name)
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
		return True
	except Exception:
		frappe.log_error(title=f"Orphan doctype cleanup failed: {name}", message=frappe.get_traceback())
		return False
