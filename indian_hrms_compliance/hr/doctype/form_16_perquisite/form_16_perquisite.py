# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from frappe.model.document import Document
from frappe.utils import flt


class Form16Perquisite(Document):
	def validate(self):
		# Convenience: taxable_value defaults to value - recovered.
		if not self.taxable_value:
			self.taxable_value = flt(self.value_of_perquisite) - flt(self.amount_recovered)
