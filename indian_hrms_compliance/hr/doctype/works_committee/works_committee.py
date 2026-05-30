# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WorksCommittee(Document):
	def validate(self):
		self._compute_member_count()
		self._validate_representation()

	def _compute_member_count(self):
		workmen = len(self.workmen_representatives or [])
		employer = len(self.employer_representatives or [])
		self.member_count_total = workmen + employer

	def _validate_representation(self):
		"""Soft warning — IR Code Sec 3 mandates that workmen reps shall not be
		less than employer reps. We msgprint rather than throw so HR can build
		the committee up incrementally."""
		workmen = len(self.workmen_representatives or [])
		employer = len(self.employer_representatives or [])
		if not (workmen or employer):
			return
		warnings = []
		if workmen < employer:
			warnings.append(
				_(
					"Workmen representatives ({0}) must not be less than employer representatives ({1}) — IR Code Sec 3(2)."
				).format(workmen, employer)
			)
		if self.status == "Active" and workmen == 0:
			warnings.append(_("No workmen representatives recorded for an Active committee."))
		if warnings:
			frappe.msgprint(
				_("Works Committee composition warning(s):") + "<br>" + "<br>".join(warnings),
				title=_("Works Committee"),
				indicator="orange",
			)
