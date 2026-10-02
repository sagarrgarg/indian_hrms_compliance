# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Family members and nominees of an employee — one table behind PF Form 2
(EPF nomination + EPS family), ESIC Form 1 (family particulars + nominee).
Child of Employee and of Employee Onboarding Application."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

MINOR_AGE = 18
# EPS para 2(vii) family: the people who draw widow / children pension.
EPS_FAMILY_RELATIONS = ("Spouse", "Son", "Daughter")


class EmployeeFamilyMember(Document):
	pass


def age_on(date_of_birth, on_date=None):
	if not date_of_birth:
		return None
	dob, on = getdate(date_of_birth), getdate(on_date)
	return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def validate_family_members(doc, method=None):
	"""Shared by Employee and Employee Onboarding Application.

	- PF nominee shares, when any are given, must total 100%.
	- At most one ESIC nominee.
	- A minor nominee needs a guardian (PF Form 2 asks for one)."""
	rows = doc.get("family_members") or []
	if not rows:
		return

	shares = [flt(r.pf_nominee_share) for r in rows]
	if any(s < 0 for s in shares):
		frappe.throw(_("PF nominee share cannot be negative."), title=_("Family & Nominees"))
	total = sum(shares)
	if total and abs(total - 100) > 0.01:
		frappe.throw(
			_("PF nominee shares must add up to 100% (they add up to {0}%).").format(flt(total, 2)),
			title=_("Family & Nominees"),
		)

	if len([r for r in rows if r.esic_nominee]) > 1:
		frappe.throw(_("Tick only one ESIC nominee."), title=_("Family & Nominees"))

	for r in rows:
		if not (flt(r.pf_nominee_share) or r.esic_nominee):
			continue
		age = age_on(r.date_of_birth)
		if age is not None and age < MINOR_AGE and not r.guardian_name:
			frappe.throw(
				_("Row {0}: {1} is a minor nominee - give the guardian's name and relationship.").format(
					r.idx, frappe.bold(r.member_name)
				),
				title=_("Family & Nominees"),
			)
