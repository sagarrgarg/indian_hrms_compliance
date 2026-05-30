# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.model.document import Document
from frappe.utils import flt


class Form12BSalaryDetail(Document):
	def validate(self):
		# Convenience: derive taxable_salary if not set explicitly.
		if not self.taxable_salary:
			self.taxable_salary = (
				flt(self.gross_salary)
				- flt(self.section_10_exemptions)
				- flt(self.section_16_deductions)
			)
