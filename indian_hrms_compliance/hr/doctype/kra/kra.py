# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class KRA(Document):
	def validate(self):
		self._validate_dri()
		self._refresh_usage_counts()

	def _validate_dri(self):
		"""An Active KRA must name exactly one accountable person — its DRI.

		"Who's the DRI on that?" only works if the answer is a person, not a
		committee and not a vacancy. `owner_designation` says which ROLE owns
		the area; `dri` says who holds it today.

		Hard-enforced on new records so incoming data is always clean; existing
		records only warn, so adopting this never blocks edits to KRAs that
		predate the field.
		"""
		if self.status != "Active" or self.dri:
			return
		msg = _("An Active KRA needs a DRI — the single person accountable for it.")
		if self.is_new():
			frappe.throw(msg, title=_("DRI Required"))
		frappe.msgprint(msg, indicator="orange", alert=True)

	def on_update(self):
		self._warn_if_dri_inactive()

	def _warn_if_dri_inactive(self):
		"""Surface a DRI who has left, rather than silently keeping a dead owner.

		Step 1 only reports it (on save); the nightly Org Integrity Check in
		Step 2 is what will escalate to the DRI's reporting manager.
		"""
		if not self.dri or self.status != "Active":
			return
		if frappe.db.get_value("Employee", self.dri, "status") != "Active":
			frappe.msgprint(
				_("The DRI for this KRA is no longer an active employee — reassign it.")
				+ f" ({self.dri})",
				indicator="red",
				alert=True,
			)

	def _refresh_usage_counts(self):
		"""Compute the three Usage (Auto) counters from current data.
		Three indexed COUNTs — cheap on save."""
		self.task_count = frappe.db.count(
			"HRMS Task", {"kra": self.name, "status": "Active"}
		)
		self.active_smart_goal_count = frappe.db.count(
			"Goal",
			{
				"kra": self.name,
				"goal_type": "SMART",
				"status": ("in", ["Pending", "In Progress"]),
			},
		)
		self.open_task_instance_count = frappe.db.count(
			"Goal",
			{
				"kra": self.name,
				"goal_type": "Task Instance",
				"status": ("in", ["Pending", "In Progress"]),
			},
		)
