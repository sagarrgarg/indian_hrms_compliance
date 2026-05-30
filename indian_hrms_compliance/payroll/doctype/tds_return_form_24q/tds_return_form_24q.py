# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""TDS Return Form 24Q — Phase 6B-2.

Per (Company × Fiscal Year × Quarter) container for the quarterly TDS
on salary statement filed with CPC TDS via the NSDL TIN RPU.

Workflow:
  1. HR creates the draft with company + FY + quarter.
  2. ``act`` is auto-derived in validate() — IT Act 2025 (Form 138) for
     Q1 of FY 2026-27 onwards; legacy Form 24Q otherwise.
  3. HR clicks "Generate" → overrides.form_24q_generator.generate_form_24q
     populates challans + Annexure I (+ Annexure II for Q4), builds the
     RPU .txt and attaches it.
  4. HR runs the .txt through the offline RPU utility, validates with
     FVU, uploads the .fvu to the e-filing portal, then captures the
     acknowledgement number via "Mark Filed".

Per-quarter window is enforced by ``_enforce_unique_filing`` — at most
one non-cancelled return per (Company, FY, Quarter).
"""

import frappe
from frappe import _
from frappe.model.document import Document


# Fiscal Year boundary at which the IT Act 2025 renames Form 24Q to
# Form 138. We compare Fiscal Year by its `year_start_date` to be robust
# against differing FY naming conventions ('2026-2027', 'FY2026-27', etc.).
# Specifically: any FY whose year_start_date is on or after 2026-04-01 is
# governed by IT Act 2025.
IT_ACT_2025_FY_START = "2026-04-01"


class TDSReturnForm24Q(Document):
	def validate(self):
		self._derive_act_and_form_name()
		self._fetch_employer_tan()
		self._enforce_unique_filing()

	def _derive_act_and_form_name(self):
		"""Determine which Act governs this return based on the Fiscal Year
		start date. Renames Form 24Q → Form 138 effective FY 2026-27 Q1."""
		governed_by_2025 = self._is_governed_by_it_act_2025()
		if governed_by_2025:
			self.act = "Income Tax Act 2025 (Form 138)"
			self.form_name = "Form 138"
		else:
			self.act = "Income Tax Act 1961 (Form 24Q)"
			self.form_name = "Form 24Q"

	def _is_governed_by_it_act_2025(self):
		"""True if the Fiscal Year starts on/after 2026-04-01."""
		if not self.fiscal_year:
			return False
		start = frappe.db.get_value("Fiscal Year", self.fiscal_year, "year_start_date")
		if not start:
			return False
		from frappe.utils import getdate
		return getdate(start) >= getdate(IT_ACT_2025_FY_START)

	def _fetch_employer_tan(self):
		"""Pull TAN from Company.tax_id if user hasn't overridden. tax_id is
		the canonical Company-level TAN field in ERPNext (used for TDS/GST
		registration depending on locale)."""
		if self.employer_tan:
			return
		if not self.company:
			return
		tan = frappe.db.get_value("Company", self.company, "tax_id")
		if tan:
			self.employer_tan = tan

	def _enforce_unique_filing(self):
		"""One non-cancelled return per (Company, FY, Quarter)."""
		if not (self.company and self.fiscal_year and self.quarter):
			return
		existing = frappe.db.exists(
			"TDS Return Form 24Q",
			{
				"company": self.company,
				"fiscal_year": self.fiscal_year,
				"quarter": self.quarter,
				"name": ("!=", self.name or ""),
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			frappe.throw(
				_(
					"A TDS Return already exists for {0} / {1} / {2}: {3}. Cancel it first."
				).format(self.company, self.fiscal_year, self.quarter, existing)
			)


def get_quarter_dates(fiscal_year, quarter):
	"""Resolve a quarter selector ('Q1'..'Q4') against a Fiscal Year and
	return (start_date, end_date). Computes from Fiscal Year.year_start_date
	so it works regardless of naming convention.

	Q1 = months 1-3 from FY start (Apr-Jun for std FY)
	Q2 = months 4-6 (Jul-Sep)
	Q3 = months 7-9 (Oct-Dec)
	Q4 = months 10-12 (Jan-Mar)
	"""
	from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate

	fy_start = getdate(frappe.db.get_value("Fiscal Year", fiscal_year, "year_start_date"))
	quarter_idx = int(quarter[1]) - 1  # 'Q1' -> 0
	q_start = get_first_day(add_months(fy_start, quarter_idx * 3))
	q_end = get_last_day(add_months(q_start, 2))
	return q_start, q_end
