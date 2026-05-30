# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""PF ECR Filing — Phase 6B-1.

Per Company × Wage Month container for the monthly EPFO Electronic
Challan-cum-Return (ECR) file. Holds the per-employee rows + the
generated .txt file + audit metadata (status, generated_on, filed_on,
challan_number, exceptions).

Workflow:
  1. HR creates the doc (Draft) with company + wage_month.
  2. Clicks "Generate ECR" → ``generate_pf_ecr`` populates rows from
     submitted Salary Slips, computes totals, builds the pipe-delimited
     .txt file, attaches it, and flips status to Generated.
  3. HR uploads the .txt on the EPFO portal, pays the challan, then
     clicks "Mark as Filed" → captures challan_number + flips to Filed.

All wage-base / contribution math lives in
overrides/pf_ecr_generator.py — this class is intentionally thin.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate


class PFECRFiling(Document):
	def autoname(self):
		# Force wage_month_label population before autoname runs against the
		# format string, otherwise the auto-generated name will literally
		# contain "{wage_month_label}".
		self._compute_wage_month_label()

	def validate(self):
		self._compute_wage_month_label()
		self._fetch_establishment_code()
		self._enforce_unique_filing()

	def _compute_wage_month_label(self):
		if not self.wage_month:
			return
		try:
			dt = getdate(self.wage_month)
			# EPFO convention: "MMM-YYYY" e.g. May-2026
			self.wage_month_label = dt.strftime("%b-%Y")
		except Exception:
			pass

	def _fetch_establishment_code(self):
		"""Pull from Company custom field if present and the user hasn't
		overridden manually. Custom field name conventions tried in order:
		pf_establishment_code, pf_establishment_id."""
		if self.establishment_code:
			return
		if not self.company:
			return
		for fld in ("pf_establishment_code", "pf_establishment_id"):
			if frappe.get_meta("Company").get_field(fld):
				val = frappe.db.get_value("Company", self.company, fld)
				if val:
					self.establishment_code = val
					return

	def _enforce_unique_filing(self):
		"""One PF ECR Filing per (company, wage_month). Cancelled docs don't
		count."""
		if not (self.company and self.wage_month):
			return
		existing = frappe.db.exists(
			"PF ECR Filing",
			{
				"company": self.company,
				"wage_month": self.wage_month,
				"name": ("!=", self.name or ""),
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			frappe.throw(
				_(
					"A PF ECR Filing already exists for {0} / {1}: {2}. Cancel it first or edit the existing one."
				).format(self.company, formatdate(self.wage_month), existing)
			)


def get_total_remittance(doc):
	"""Pure helper — sum of EPF + EPS + EDLI + Admin. Used both by the
	generator and externally if anyone needs to reconcile."""
	return (
		flt(doc.total_epf_contribution)
		+ flt(doc.total_eps_contribution)
		+ flt(doc.total_edli_contribution)
		+ flt(doc.total_admin_charges)
	)
