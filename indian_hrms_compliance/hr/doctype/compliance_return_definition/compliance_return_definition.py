# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Compliance Return Definition — Phase 6C.

The applicability spec per Company x Return Type (x State). HR
configures: "We file PF ECR monthly", "PT state is KA so monthly",
"S&E is registered in DL so lifetime no annual return", etc.

The auto-populate flow in overrides/compliance_calendar reads these
rows to know which Compliance Filing entries to spawn for a given FY.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class ComplianceReturnDefinition(Document):
	def validate(self):
		self._validate_state_required_for_state_returns()
		self._enforce_unique_definition()
		self._sync_cadence_schedule()

	def _sync_cadence_schedule(self):
		"""Keep the 'use explicit schedule' flag honest and the rows sane.

		Adding rows auto-enables the schedule so a user doesn't have to remember
		the checkbox; occurrence labels must be distinct because they seed the
		Compliance Filing period label (and its unique name)."""
		rows = self.get("cadence_schedule") or []
		if rows and not self.use_cadence_schedule:
			self.use_cadence_schedule = 1

		seen = set()
		for row in rows:
			label = (row.occurrence_label or "").strip()
			if not label:
				continue
			key = label.lower()
			if key in seen:
				frappe.throw(
					_("Duplicate occurrence '{0}' in the Cadence Schedule — labels must be unique.").format(label)
				)
			seen.add(key)

	def _validate_state_required_for_state_returns(self):
		"""PT / LWF / S&E require a state. Federal returns must not have one."""
		state_required = {"Professional Tax", "LWF", "S&E Annual Return"}
		if self.return_type in state_required and not self.state:
			frappe.throw(
				_("State is required for {0}.").format(self.return_type)
			)

	def _enforce_unique_definition(self):
		"""One definition per (company, return_type, state) — state may be
		empty for federal returns."""
		filters = {
			"company": self.company,
			"return_type": self.return_type,
			"name": ("!=", self.name or ""),
		}
		if self.state:
			filters["state"] = self.state
		else:
			filters["state"] = ("in", ("", None))
		existing = frappe.db.exists("Compliance Return Definition", filters)
		if existing:
			frappe.throw(
				_("A definition already exists for {0} / {1} / {2}: {3}").format(
					self.company, self.return_type, self.state or "(federal)", existing
				)
			)
