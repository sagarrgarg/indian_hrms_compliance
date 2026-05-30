# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


MAX_MEMBERS_PER_GRC = 12


class GrievanceRedressalCommittee(Document):
	def validate(self):
		self._compute_women_count()
		self._validate_composition()

	def _compute_women_count(self):
		self.women_member_count = sum(
			1 for m in (self.members or []) if (m.gender or "").lower() == "female" and m.is_active
		)

	def _validate_composition(self):
		members = self.members or []
		warnings = []
		if len(members) > MAX_MEMBERS_PER_GRC:
			frappe.throw(
				_(
					"A Grievance Redressal Committee may have at most {0} members per IR Code Sec 4."
				).format(MAX_MEMBERS_PER_GRC)
			)
		if not members:
			return
		if self.status == "Active" and (self.women_member_count or 0) < 1:
			warnings.append(
				_("At least one member must be a woman — IR Code Sec 4(2) mandate.")
			)
		if warnings:
			frappe.msgprint(
				_("GRC composition warning(s):") + "<br>" + "<br>".join(warnings),
				title=_("Grievance Redressal Committee"),
				indicator="orange",
			)
