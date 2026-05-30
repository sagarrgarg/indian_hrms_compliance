# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class EmployeeNoDuesItem(Document):
	def validate(self):
		# When status flips to Cleared, stamp cleared_on + cleared_by automatically.
		# Lets HR move many rows in one save without ceremony.
		if self.status == "Cleared":
			if not self.cleared_on:
				self.cleared_on = today()
			if not self.cleared_by:
				self.cleared_by = frappe.session.user
		elif self.status != "Cleared":
			# Status moved away from Cleared — clear the stamps so they don't lie.
			self.cleared_on = None
			self.cleared_by = None
