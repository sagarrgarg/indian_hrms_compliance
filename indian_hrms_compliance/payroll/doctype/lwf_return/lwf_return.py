# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""LWF Return — Phase 6B-2.

Per (Company × Indian State × Period) Labour Welfare Fund return.
Filing frequency depends on the state (Monthly / Half-yearly / Annual)."""

import frappe
from frappe import _
from frappe.model.document import Document


class LWFReturn(Document):
	def validate(self):
		self._enforce_unique_period()

	def _enforce_unique_period(self):
		if not (self.company and self.state and self.period_start and self.period_end):
			return
		existing = frappe.db.exists(
			"LWF Return",
			{
				"company": self.company,
				"state": self.state,
				"period_start": self.period_start,
				"period_end": self.period_end,
				"name": ("!=", self.name or ""),
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			frappe.throw(
				_(
					"An LWF Return already exists for {0} / {1} / {2}–{3}: {4}. Cancel it first."
				).format(self.company, self.state, self.period_start, self.period_end, existing)
			)
