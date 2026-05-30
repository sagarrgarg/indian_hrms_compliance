# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Professional Tax Return Row — Phase 6B-2.

Per-employee row carrying gross wages, actual PT deducted on the
Salary Slip, and the expected PT per the state's slabs. Variance
flags audit cases (mis-mapped slab, missing component, etc.)."""

from frappe.model.document import Document
from frappe.utils import flt


class ProfessionalTaxReturnRow(Document):
	def validate(self):
		self.variance = flt(self.pt_deducted) - flt(self.expected_pt)
