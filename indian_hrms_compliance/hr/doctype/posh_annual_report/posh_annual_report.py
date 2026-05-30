# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class POSHAnnualReport(Document):
	def validate(self):
		self._recompute_stats()

	def _recompute_stats(self):
		"""Aggregate POSH Complaint counts for the FY into the stats fields.
		Reads via direct SQL with bypass=True since the permission_query_
		conditions hook would otherwise filter complaints away from HR.
		(HR cannot see complaint *detail*; they can see *counts* via the
		Annual Report.)"""
		if not (self.company and self.fiscal_year):
			return
		fy = frappe.db.get_value(
			"Fiscal Year", self.fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy:
			return

		# Total complaints filed in the FY for this Company
		self.complaints_received = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabPOSH Complaint`
			WHERE company = %s AND filing_date BETWEEN %s AND %s
			""",
			(self.company, fy.year_start_date, fy.year_end_date),
		)[0][0]

		# Disposed = workflow_state=Closed within the FY
		self.complaints_disposed = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabPOSH Complaint`
			WHERE company = %s AND workflow_state = 'Closed'
			  AND closed_on BETWEEN %s AND %s
			""",
			(self.company, fy.year_start_date, fy.year_end_date),
		)[0][0]

		# Pending at year end = not Closed AND filed on or before year_end_date
		self.complaints_pending_at_year_end = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabPOSH Complaint`
			WHERE company = %s AND workflow_state != 'Closed'
			  AND filing_date <= %s
			""",
			(self.company, fy.year_end_date),
		)[0][0]

		# Pending > 90 days = not Closed AND filing_date older than 90 days from year_end_date
		from frappe.utils import add_days

		cutoff = add_days(fy.year_end_date, -90)
		self.complaints_pending_over_90_days = frappe.db.sql(
			"""
			SELECT COUNT(*) FROM `tabPOSH Complaint`
			WHERE company = %s AND workflow_state != 'Closed'
			  AND filing_date <= %s
			""",
			(self.company, cutoff),
		)[0][0]

		# Auto-link the IC + policy if not set
		if not self.internal_committee:
			ic = frappe.db.get_value(
				"POSH Internal Committee",
				{"company": self.company, "status": "Active"},
				"name",
				order_by="constitution_date desc",
			)
			if ic:
				self.internal_committee = ic
		if self.internal_committee and not self.linked_posh_policy:
			self.linked_posh_policy = frappe.db.get_value(
				"POSH Internal Committee", self.internal_committee, "linked_posh_policy"
			)
