# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""UAN / Aadhaar seeding validator — SS Code Sec 142.

Wired into Employee.validate (additive) in hooks.py.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def _hr_setting(field, default=None):
	"""Safe HR Settings reader — tolerant of missing fields."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


def validate_uan_aadhaar_linking(doc, method=None):
	"""SS Code Sec 142 — UAN must be linked to Aadhaar for active employees.

	Soft warning (msgprint) rather than throw — we don't want to block
	Employee saves over a documentation requirement.
	"""
	if not int(_hr_setting("enable_uan_aadhaar_validation", 1)):
		return

	# UAN custom field is set up in Phase 1; if not present, exit cleanly.
	uan = getattr(doc, "uan_number", None)
	if not uan:
		return

	status = getattr(doc, "uan_seeding_status", None) or "Not Seeded"
	if status != "Not Seeded":
		return

	if (doc.status or "Active") != "Active":
		return

	# Only warn after the employee has been on the rolls for >30 days
	doj = doc.date_of_joining
	if not doj:
		return
	try:
		tenure_days = date_diff(today(), getdate(doj))
	except Exception:
		return
	if tenure_days < 30:
		return

	frappe.msgprint(
		_(
			"UAN {0} is set but not yet seeded with Aadhaar — required under SS Code Sec 142. "
			"Please update <b>UAN Aadhaar Seeding Status</b> once the seeding is confirmed."
		).format(uan),
		title=_("UAN Aadhaar Linking"),
		indicator="orange",
	)
