# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Monthly Contribution — Phase 6B-1.

Per Company × Wage Month container for the monthly ESIC contribution
upload. Holds the per-Insured-Person rows + the generated CSV file +
audit metadata.

Workflow mirrors PF ECR Filing: Draft → Generate Contribution File →
Generated → Mark as Filed → Filed.

Generator logic lives in overrides/esi_generator.py.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate


class ESIMonthlyContribution(Document):
	def autoname(self):
		self._compute_wage_month_label()

	def validate(self):
		self._compute_wage_month_label()
		self._fetch_esi_code()
		self._enforce_unique_filing()

	def _compute_wage_month_label(self):
		if not self.wage_month:
			return
		try:
			dt = getdate(self.wage_month)
			self.wage_month_label = dt.strftime("%b-%Y")
		except Exception:
			pass

	def _fetch_esi_code(self):
		if self.esi_code:
			return
		if not self.company:
			return
		for fld in ("esi_code", "esic_code", "esi_establishment_code"):
			if frappe.get_meta("Company").get_field(fld):
				val = frappe.db.get_value("Company", self.company, fld)
				if val:
					self.esi_code = val
					return

	def _enforce_unique_filing(self):
		if not (self.company and self.wage_month):
			return
		existing = frappe.db.exists(
			"ESI Monthly Contribution",
			{
				"company": self.company,
				"wage_month": self.wage_month,
				"name": ("!=", self.name or ""),
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			frappe.throw(
				_(
					"An ESI Monthly Contribution already exists for {0} / {1}: {2}. Cancel it first or edit the existing one."
				).format(self.company, formatdate(self.wage_month), existing)
			)


def get_total_contribution(doc):
	"""Pure helper — challan amount = employee + employer share."""
	return flt(doc.total_employee_contribution) + flt(doc.total_employer_contribution)
