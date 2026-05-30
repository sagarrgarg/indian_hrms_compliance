# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class POSHInternalCommittee(Document):
	def validate(self):
		self._validate_composition()
		self._validate_dates()

	def _validate_composition(self):
		"""Soft warning — the Act mandates minimum 4 members, presiding officer
		as senior female employee, ≥50% women, and at least one external member.
		We msgprint rather than throw so HR can build the IC up incrementally."""
		members = self.members or []
		if not members:
			return  # Empty draft — no warning yet.

		warnings = []
		if len(members) < 4:
			warnings.append(_("Less than 4 members. POSH Act Sec 4(2) recommends a minimum of 4."))

		presiding = [m for m in members if m.role == "Presiding Officer"]
		if not presiding:
			warnings.append(_("No Presiding Officer. Per Sec 4(2)(a), the Presiding Officer must be a senior female employee."))
		elif len(presiding) > 1:
			warnings.append(_("More than one Presiding Officer. Per Sec 4(2)(a), there must be exactly one."))

		external = [m for m in members if m.role == "External Member" or m.is_external]
		if not external:
			warnings.append(_("No External Member. Per Sec 4(2)(c), at least one member must be from an NGO / legal background outside the organisation."))

		if warnings:
			frappe.msgprint(
				_("POSH Composition warning(s):") + "<br>• " + "<br>• ".join(warnings),
				title=_("POSH IC Composition"),
				indicator="orange",
			)

	def _validate_dates(self):
		if self.status == "Dissolved" and not self.dissolution_date:
			frappe.throw(_("Dissolved On is required when status is Dissolved."))
		if self.dissolution_date and self.constitution_date:
			from frappe.utils import getdate

			if getdate(self.dissolution_date) < getdate(self.constitution_date):
				frappe.throw(_("Dissolved On cannot be before Constituted On."))

	def get_active_member_users(self):
		"""Return User IDs of active IC members — used by POSH Complaint for
		alerts and permission gating."""
		from frappe.utils import getdate, today

		today_d = getdate(today())
		user_ids = []
		for m in self.members or []:
			if not m.is_active:
				continue
			if m.tenure_to and getdate(m.tenure_to) < today_d:
				continue
			if m.tenure_from and getdate(m.tenure_from) > today_d:
				continue
			if m.is_external:
				# External members don't have a system User by default — skip.
				continue
			if m.employee:
				user_id = frappe.db.get_value("Employee", m.employee, "user_id")
				if user_id:
					user_ids.append(user_id)
		return user_ids
