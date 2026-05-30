# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class StandingOrders(Document):
	def validate(self):
		self._validate_version()
		self._validate_dates()
		self._auto_stamp_dates()
		self._sync_with_workflow_state()

	def on_submit(self):
		# When a new Standing Orders is submitted as Active, mark older active doc Superseded.
		if self.status == "Active":
			self._supersede_older_versions()

	def _validate_version(self):
		if not self.version:
			return
		# version must be unique per Company
		existing = frappe.db.get_value(
			"Standing Orders",
			{"company": self.company, "version": self.version, "name": ("!=", self.name or "")},
			"name",
		)
		if existing:
			frappe.throw(
				_("Version {0} already exists for Company {1} (record {2}).").format(
					self.version, self.company, existing
				)
			)

	def _validate_dates(self):
		if self.effective_from and self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))
		if self.certified_on and self.submitted_on and getdate(self.certified_on) < getdate(self.submitted_on):
			frappe.throw(_("Certified On cannot be before Submitted On."))

	def _auto_stamp_dates(self):
		"""Mirror workflow_state transitions into the dated fields."""
		ws = getattr(self, "workflow_state", None) or self.status
		if ws == "Submitted to Certifying Officer" and not self.submitted_on:
			self.submitted_on = today()
		if ws in ("Certified", "Active") and not self.certified_on:
			self.certified_on = today()
		if ws == "Active" and not self.effective_from:
			self.effective_from = today()

	def _sync_with_workflow_state(self):
		"""Mirror workflow_state into status (workflow_state may not exist for non-workflow saves)."""
		ws = getattr(self, "workflow_state", None)
		if ws and ws in (
			"Draft",
			"Submitted to Certifying Officer",
			"Certified",
			"Active",
			"Superseded",
		):
			self.status = ws

	def _supersede_older_versions(self):
		older = frappe.get_all(
			"Standing Orders",
			filters={
				"company": self.company,
				"status": "Active",
				"name": ("!=", self.name),
			},
			pluck="name",
		)
		for n in older:
			frappe.db.set_value("Standing Orders", n, "status", "Superseded")
			frappe.db.set_value("Standing Orders", n, "superseded_by", self.name)
			frappe.db.set_value("Standing Orders", n, "effective_to", today())
		if older and not self.supersedes:
			# pick most-recent previous as the "supersedes" reference
			most_recent = older[0]
			self.db_set("supersedes", most_recent)
