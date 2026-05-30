# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Half Yearly Return — Phase 6B-1.

Aggregator doctype for the ESI (General) Regulations Reg 26 Return of
Contributions (RoC). Two periods:

  * Apr–Sep — due 11 Nov of the same FY
  * Oct–Mar — due 11 May of the following FY

The actual contribution data lives in 6 ESI Monthly Contribution docs;
this doc just bundles them + auto-computes period totals + renders a
human-readable summary HTML block. Aggregation logic lives in
overrides/esi_half_yearly_aggregator.py.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ESIHalfYearlyReturn(Document):
	def validate(self):
		self._compute_due_date()
		self._enforce_unique_filing()

	def _compute_due_date(self):
		"""Apr-Sep → 11 Nov of same FY; Oct-Mar → 11 May of next FY.
		Reads Fiscal Year's year_start_date to anchor the calendar year."""
		if not (self.fiscal_year and self.period):
			return
		fy = frappe.db.get_value(
			"Fiscal Year", self.fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy:
			return
		fy_start = getdate(fy.year_start_date)
		# Indian FY starts Apr 1. Apr-Sep is the first half; its due date is
		# 11 Nov of the same calendar year as fy_start. Oct-Mar is the second
		# half; due 11 May of the following calendar year (= fy_end.year + 1
		# when fy_start is Apr).
		if self.period == "Apr-Sep":
			self.due_date = f"{fy_start.year}-11-11"
		else:
			fy_end = getdate(fy.year_end_date)
			self.due_date = f"{fy_end.year}-05-11"

	def _enforce_unique_filing(self):
		if not (self.company and self.fiscal_year and self.period):
			return
		existing = frappe.db.exists(
			"ESI Half Yearly Return",
			{
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"period": self.period,
				"name": ("!=", self.name or ""),
			},
		)
		if existing:
			frappe.throw(
				_(
					"An ESI Half Yearly Return already exists for {0} / {1} / {2}: {3}."
				).format(self.company, self.fiscal_year, self.period, existing)
			)
