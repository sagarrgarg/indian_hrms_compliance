# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OSHAnnualReturnForm26(Document):
	def validate(self):
		self._compute_total_workers()

	def _compute_total_workers(self):
		self.total_workers = (
			(self.total_workers_male or 0)
			+ (self.total_workers_female or 0)
			+ (self.total_workers_others or 0)
		)
