# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Indian State — Phase 6A.

Per-state config used by the Salary Structure Validator:

  - PT (Professional Tax): applicability, slabs (gender-aware,
    monthly / half-yearly), special-month (Feb) extra deduction,
    constitutional cap.
  - LWF (Labour Welfare Fund): employee + employer contribution,
    filing frequency.
  - Shops & Establishments: act name + annual return form + due date
    + certificate validity (used for compliance calendar generation).
  - Labour Codes notification status (Wage Code et al.) — informational
    field for HR; the actual Wage Code §2(y) 50% rule check lives in the
    validator and reads HR Settings.wage_code_enforcement.

state_code is the primary key (autoname: field:state_code). Renames are
disallowed because downstream Minimum Wage Notification + Employee
address resolution depend on stable codes.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class IndianState(Document):
	def validate(self):
		self._normalise_state_code()
		self._validate_pt_slabs()

	def _normalise_state_code(self):
		if self.state_code:
			self.state_code = self.state_code.strip().upper()

	def _validate_pt_slabs(self):
		if not self.pt_applicable:
			return
		for i, row in enumerate(self.pt_slabs or [], start=1):
			if flt(row.from_amount) < 0:
				frappe.throw(_("Row {0}: From amount cannot be negative.").format(i))
			# to_amount == 0 means "and above" — allowed
			if flt(row.to_amount) and flt(row.to_amount) < flt(row.from_amount):
				frappe.throw(
					_("Row {0}: To amount must be greater than or equal to From amount (use 0 for 'and above').").format(i)
				)
