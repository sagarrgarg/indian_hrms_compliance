# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Compliance Filing — Phase 6C.

One record per (Company x Return Type x Period). This is the unified
calendar entry HR sees in the List view; the actual filing payload
(challan rows, computed wages, etc.) lives on the underlying doctype
(e.g. PF ECR Filing) which back-links to this row via
linked_filing_doctype + linked_filing_name.

This controller is intentionally thin — heavy lifting (auto-populate,
penalty computation, scheduler reminders, doc_event back-linking) lives
in overrides/compliance_calendar.py.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ComplianceFiling(Document):
	def autoname(self):
		# Sanitise period_label / state for the autoname (slashes, spaces).
		if self.period_label:
			self.period_label = self._sanitised_period_label()

	def _sanitised_period_label(self):
		val = (self.period_label or "").strip()
		# Replace anything that breaks autoname.
		for bad, good in (("/", "-"), ("\\", "-"), ("#", ""), ("&", "and")):
			val = val.replace(bad, good)
		return val

	def validate(self):
		self._enforce_unique_per_period()
		self._validate_dates()

	def _enforce_unique_per_period(self):
		"""One Compliance Filing per (company, return_type, period_start,
		period_end, state)."""
		if not (self.company and self.return_type and self.period_start and self.period_end):
			return
		filters = {
			"company": self.company,
			"return_type": self.return_type,
			"period_start": self.period_start,
			"period_end": self.period_end,
			"name": ("!=", self.name or ""),
		}
		if self.state:
			filters["state"] = self.state
		existing = frappe.db.exists("Compliance Filing", filters)
		if existing:
			frappe.throw(
				_(
					"A Compliance Filing already exists for {0} / {1} / {2}: {3}"
				).format(self.company, self.return_type, self.period_label or "this period", existing)
			)

	def _validate_dates(self):
		if self.period_start and self.period_end:
			if getdate(self.period_end) < getdate(self.period_start):
				frappe.throw(_("Period End cannot be before Period Start."))
		if self.due_date and self.period_start:
			if getdate(self.due_date) < getdate(self.period_start):
				frappe.throw(_("Due Date cannot be before Period Start."))


@frappe.whitelist()
def mark_as_filed(name, acknowledgement_number=None, filed_on=None, amount_filed=None):
	"""HR action — flip status to Filed (or Late Filed if past due_date).

	Computes penalty if late. Idempotent: safe to call repeatedly."""
	from indian_hrms_compliance.overrides.compliance_calendar import _compute_penalty

	doc = frappe.get_doc("Compliance Filing", name)
	if doc.filing_status in ("Filed", "Late Filed", "Waived", "Not Applicable"):
		frappe.throw(
			_("Compliance Filing {0} is already {1}. Cannot re-mark.").format(
				doc.name, doc.filing_status
			)
		)
	from frappe.utils import nowdate

	filed_dt = getdate(filed_on or nowdate())
	doc.filed_on = filed_dt
	if acknowledgement_number:
		doc.acknowledgement_number = acknowledgement_number
	if amount_filed is not None:
		doc.amount_filed = amount_filed

	if doc.due_date and filed_dt > getdate(doc.due_date):
		doc.filing_status = "Late Filed"
		doc.days_late = (filed_dt - getdate(doc.due_date)).days
		amount, basis = _compute_penalty(doc)
		doc.penalty_amount = amount
		doc.penalty_basis = basis
	else:
		doc.filing_status = "Filed"
		doc.days_late = 0
		doc.penalty_amount = 0
		doc.penalty_basis = ""

	doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def waive(name, reason=None):
	"""Mark a Compliance Filing as Waived (Not applicable for this period)."""
	doc = frappe.get_doc("Compliance Filing", name)
	doc.filing_status = "Waived"
	if reason:
		existing = doc.notes or ""
		stamp = f"[WAIVED] {reason}"
		doc.notes = (existing + "\n" + stamp).strip()
	doc.save(ignore_permissions=True)
	return doc.name
