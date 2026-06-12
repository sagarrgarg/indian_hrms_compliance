# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Back-dated attendance approval gate.

Attendance Requests and direct Attendance changes whose date falls further in
the past than the HR Settings threshold (`backdated_attendance_approval_months`)
can only be SUBMITTED by a user holding the configured approval role
(default 'HRMS Master Manager'). Anyone may still draft them — submission is the
gate, mirroring the existing back-dated *leave* restriction in this app.

Set the months threshold to 0 to switch the restriction off entirely.
Administrator always passes (it implicitly holds every role).
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, format_date, getdate

MASTER_APPROVAL_ROLE = "HRMS Master Manager"


def _threshold_months() -> int:
	return cint(frappe.db.get_single_value("HR Settings", "backdated_attendance_approval_months"))


def _approval_role() -> str:
	return (
		frappe.db.get_single_value("HR Settings", "role_allowed_to_approve_backdated_attendance")
		or MASTER_APPROVAL_ROLE
	)


def is_backdated_beyond_threshold(attendance_date) -> bool:
	"""True when ``attendance_date`` is older than the configured months window.

	A threshold of 0 (or unset) disables the restriction.
	"""
	months = _threshold_months()
	if not months or not attendance_date:
		return False
	return getdate(attendance_date) < add_months(getdate(), -months)


def enforce_master_approval(attendance_date, what: str) -> None:
	"""Throw unless the current user may push through a back-dated attendance."""
	if not is_backdated_beyond_threshold(attendance_date):
		return
	role = _approval_role()
	if role in frappe.get_roles():
		return
	frappe.throw(
		_(
			"This {0} is dated {1}, which is older than the {2}-month back-dating "
			"limit set in HR Settings. Only a user with the {3} role can submit it."
		).format(what, format_date(getdate(attendance_date)), _threshold_months(), frappe.bold(role)),
		title=_("Master Manager Approval Required"),
	)


def guard_attendance_request(doc, method=None) -> None:
	# The earliest requested day is the back-dating depth that matters.
	enforce_master_approval(doc.from_date, _("attendance request"))


def guard_attendance(doc, method=None) -> None:
	enforce_master_approval(doc.attendance_date, _("attendance change"))
