# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Form 24Q Annexure II Row — Phase 6B-2.

One row per Employee aggregated over the full Financial Year. Filed
ONLY with the Q4 statement (Jan-Mar quarter). Drives Form 16 Part B
content downstream."""

from frappe.model.document import Document
from frappe.utils import flt


class Form24QAnnexureIIRow(Document):
	def validate(self):
		# Recompute derived fields defensively — generator sets them, but a
		# human editing the grid should still get sane totals.
		self.income_under_salaries = (
			flt(self.gross_salary)
			- flt(self.section_10_exemptions)
			- flt(self.section_16_deductions)
		)
		self.gross_total_income = flt(self.income_under_salaries) + flt(self.other_income)
		self.taxable_income = flt(self.gross_total_income) - flt(self.chapter_via_deductions)
		self.tax_liability = (
			flt(self.tax_payable) + flt(self.surcharge) + flt(self.health_education_cess)
		)
		self.tds_balance = flt(self.tax_liability) - flt(self.tds_deducted)
