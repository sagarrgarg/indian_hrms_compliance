# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class Form12BCarryIn(Document):
	def validate(self):
		self._validate_dates()
		self._recompute_totals()

	def _validate_dates(self):
		if self.employment_from_date and self.employment_to_date:
			if getdate(self.employment_to_date) < getdate(self.employment_from_date):
				frappe.throw(_("Employment To cannot be earlier than Employment From."))

	def _recompute_totals(self):
		# Derive each row's taxable_salary here (child validate doesn't fire on
		# parent save in Frappe) then sum into the parent totals.
		gross = section_10 = section_16 = taxable = tds = 0
		for row in self.monthly_breakup or []:
			if not flt(row.taxable_salary):
				row.taxable_salary = (
					flt(row.gross_salary)
					- flt(row.section_10_exemptions)
					- flt(row.section_16_deductions)
				)
			gross += flt(row.gross_salary)
			section_10 += flt(row.section_10_exemptions)
			section_16 += flt(row.section_16_deductions)
			taxable += flt(row.taxable_salary)
			tds += flt(row.tds_deducted)
		self.total_gross_salary = gross
		self.total_section_10 = section_10
		self.total_section_16 = section_16
		self.total_taxable_salary = taxable
		self.total_tds_deducted = tds
