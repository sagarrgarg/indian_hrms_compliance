# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Backfill: link orphan onboarding-document Files to their application.

Candidate uploads on the public web form land as PRIVATE files; some arrive
with no attached_to link. A private orphan file is readable only by its owner +
System Manager, so HR User/Manager verifying the application can't open the
PAN/Aadhaar. The controller now anchors these on save going forward; this patch
heals the records created before that fix.

Defensive + idempotent: guards table existence, skips files already attached to
anything, and re-running it is a no-op once every file is linked.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Employee Onboarding Document"):
		return

	rows = frappe.get_all(
		"Employee Onboarding Document",
		filters={"parenttype": "Employee Onboarding Application"},
		fields=["document", "parent"],
	)

	linked = 0
	parent_exists: dict[str, bool] = {}
	for r in rows:
		if not r.document or not r.parent:
			continue
		if r.parent not in parent_exists:
			parent_exists[r.parent] = bool(
				frappe.db.exists("Employee Onboarding Application", r.parent)
			)
		if not parent_exists[r.parent]:
			continue
		for f in frappe.get_all(
			"File",
			filters={"file_url": r.document},
			fields=["name", "attached_to_doctype", "attached_to_name"],
		):
			if f.attached_to_doctype or f.attached_to_name:
				continue  # already linked somewhere — leave it
			frappe.db.set_value(
				"File",
				f.name,
				{
					"attached_to_doctype": "Employee Onboarding Application",
					"attached_to_name": r.parent,
				},
				update_modified=False,
			)
			linked += 1

	if linked:
		print(
			"  Linked %d orphan onboarding document file(s) to their application "
			"(HR can now open them)" % linked
		)
